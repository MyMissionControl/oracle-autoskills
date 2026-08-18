---
name: find-own-azure-rbac-without-graph
description: 'Use when az identity commands fail with AADSTS70043 / expired Graph token but you still must determine your own Azure RBAC roles and scopes — decode the oid from the ARM token and query…'
installer: auto-skill
created_at: 2026-08-18T10:45:39+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'claude-opus-5'
category: 'azure'
content_hash: c0245d559b5a762fae98eb9f080ba334477680543eb20721de3661f04925e21f
---
# Find your own Azure RBAC when the Graph token is dead

## When this fires

You need to answer "what am I actually allowed to do on this subscription?" and the obvious command dies:

```
$ az role assignment list --all --assignee <upn>
ERROR: AADSTS70043: The refresh token has expired or is invalid due to sign-in
frequency checks by conditional access. The token was issued on <date> ...
```

The trap: this error does **not** mean `az` is logged out. ARM and Microsoft Graph are separate token resources with separate refresh lifetimes. Conditional access commonly caps Graph at 14 days while the ARM token keeps refreshing fine — so `az group list` and `az webapp deploy` still work while every identity-resolving command fails. Do not tell the user "you need to log in again" before checking which half is broken, and do not re-login blindly if a long-running deploy session depends on the current token.

## Step 1 — establish which half still works

```bash
az group list -o table          # ARM: works?  -> resource commands are fine
az ad signed-in-user show       # Graph: works? -> nothing is broken, stop here
```

If ARM works and Graph does not, continue — you can get the full RBAC answer over ARM alone.

## Step 2 — get your own object id out of the ARM token

`--assignee <upn>` fails only because the CLI resolves the name through Graph. The object id is already inside the ARM access token as the `oid` claim. Extract it without ever printing the token:

```bash
OID=$(az account get-access-token --resource https://management.azure.com/ \
        --query accessToken -o tsv \
      | python3 -c "import sys,base64,json;t=sys.stdin.read().strip().split('.')[1];t+='='*(-len(t)%4);print(json.loads(base64.urlsafe_b64decode(t)).get('oid',''))")
echo "objectId=$OID"
```

Never `echo` the raw token or write it to a file — pipe it straight into the decoder. The `oid` is a plain GUID and is safe to show.

## Step 3 — query role assignments over ARM only

`az role assignment list` re-enters Graph even with `--assignee-object-id` (it enriches `principalName` for display), so go under it with `az rest`:

```bash
SUB=$(az account show --query id -o tsv)
az rest --method get \
  --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Authorization/roleAssignments?api-version=2022-04-01&\$filter=assignedTo('$OID')" \
  --query "value[].{scope:properties.scope,roleDefId:properties.roleDefinitionId}" -o json
```

Escape the `$` in `$filter` (`\$filter`) or the shell eats it and the API returns every assignment in the subscription. `assignedTo()` includes roles inherited from group membership, which is what you want.

## Step 4 — turn the role GUID into a name and its real limits

```bash
az rest --method get \
  --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Authorization/roleDefinitions/<roleDefGuid>?api-version=2022-04-01" \
  --query "{name:properties.roleName,actions:properties.permissions[0].actions,notActions:properties.permissions[0].notActions}"
```

Read `notActions`, not just the role name — that is where the answer usually lives. `Contributor` looks like full access (`actions: ["*"]`) but its notActions strip `Microsoft.Authorization/*/Write|Delete`, i.e. **it cannot grant anyone (including a new service principal) any role**. Any plan that needs a service connection, a CI service principal, or "give this app access to that resource" is blocked by that line alone.

## Step 5 — report scope, not just role

Two things decide the answer and both must be stated:

- **the role** (what verbs), from step 4
- **the scope each assignment is attached to** (where), from step 3 — subscription vs a handful of resource groups is a completely different answer

Also check `az account show --query user.name` and compare it to the human's own email. A CLI logged in as a shared/pool/service account answers a different question than "what can I do in the Portal", and that mismatch is easy to miss.

## Re-login, when you do need Graph

```bash
az login --tenant <tenantId> --scope "https://graph.microsoft.com//.default"
```

Only after you have finished the read-only audit above — a fresh interactive login can change which account is active.
