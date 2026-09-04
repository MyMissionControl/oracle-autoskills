---
name: find-every-copy-of-a-rotated-secret
description: 'Use when a rotated key/token may still have stale copies on disk, or something auths with the wrong credential. Enumerates every store, compares by hash not value, classifies which copies self-heal.'
installer: auto-skill
created_at: 2026-09-04T18:02:18+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-opus-5'
category: 'security'
content_hash: 60ebf5ceeb8e4ac39d5905f9e04ae24baab3621adf2f89a41aad192a039df92f
---
# Find every on-disk copy of a rotated secret

Use when you rotated a key/token/password and need to prove the rotation is COMPLETE — or
when something authenticates with the wrong credential and you suspect a stale copy. A
secret almost never lives in one file: there is a store, a generated config, one or more
per-profile/per-env files, and a vendor's own config. Rotating one leaves the rest lying.

## Rules

- **Never print a secret value.** Compare by `len()` + `sha256(v)[:12]`. A length mismatch
  is usually the first visible signal (observed: 37 vs 40 chars ended a whole investigation).
- **Never send a guessed key to the live service to "test" it.** Many gateways ban the
  source IP after N failed auths and then reject the CORRECT key too. Decide from the
  config files; if you must probe, use a throwaway instance on a spare port.

## Steps

1. **Enumerate candidate stores before reading any of them.** Four kinds, and you need all four:
   - the source-of-truth store (`<app>/providers.json`, `.env`, a keyring)
   - the config you GENERATE for the consumer (`config.yaml` the daemon reads)
   - per-profile / per-launch files (`<profile>.settings.json`, `launch-*.json`)
   - the vendor's OWN config, which may hold a different key it invented itself
   `grep -rl` is not enough — also `find` the state dirs, because a copy can sit in a file
   whose name contains none of your keywords.

2. **Extract and hash them all in ONE script**, so the table is comparable at a glance:
   ```python
   def h(s): return hashlib.sha256(s.encode()).hexdigest()[:12]
   print('%-40s len=%3d sha=%s %s' % (where, len(v), h(v), '== source' if v==src else ''))
   ```
   ⛔ For YAML lists the value is on the **next line** (`api-keys:\n  - <value>`), so a
   naive `^key:\s*(.+)$` returns empty and you will report "no key set" — wrong.
   Sweep the whole file for any `key: <20+ chars>` value too, to catch stores you did not predict.

3. **Classify each copy** — only one class actually goes stale:
   - *source of truth* — the one you rotated
   - *derived, regenerated* — rebuilt from the source on some trigger ⇒ self-heals
   - *hand-pasted / written once* — ⇒ **this is what goes stale**
   To classify, find the WRITER, not the launcher. Read the function that serializes the
   file, not the one that sets env at spawn time. (Observed miss: reading `*-env.js`
   instead of `*-writer.js` nearly produced a false "the key is missing" report.)

4. **For each derived copy, find the trigger and the source it reads.** A copy regenerated
   from a *different* source than the one you rotated is a second bug, not a self-heal.

5. **Size the blast radius from CONSUMERS, not from the file.** Grep for who imports/reads
   the stale store. A stale file that nothing reads on the hot path is a footnote; one read
   at dispatch is an outage. Check specifically whether the consumer *strips* the credential
   (some readers use the file only for discovery and take the key from elsewhere).

6. **Fix by WRITING the current value — check what blanking would do first.** Emptying a
   credential often makes a downstream reader treat the whole entry as invalid and DELETE
   it (profile disappears from a picker, entry is pruned from a store). Write, don't blank.
   Preserve the original file mode; write via temp + `os.replace` so a crash cannot truncate.

7. **Re-verify every pair after the fix** — print the same table plus each cross-check as a
   boolean. And if a backup/restore bundle exists, confirm the rotated secret and anything
   derived from it (e.g. a bcrypt hash of it) travel **together**; restoring one without the
   other can latch a permanently-rejected credential.
