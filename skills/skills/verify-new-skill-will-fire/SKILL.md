---
name: verify-new-skill-will-fire
description: Use after adding/editing an agent SKILL.md to prove it will actually fire: eager-vs-lazy dir, sweeper-cron filters, config-dir overrides, trigger-language match.
installer: auto-skill
created_at: 2026-07-30T01:35:18+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-opus-5
category: skills
content_hash: 9782ae060a4b016057d7129f7a608272e31643452ddcb2b1aa497614085cf935
---
# Verify a new agent skill will actually be invoked

Adding a `SKILL.md` is not the same as it being reachable. Four things silently prevent it from ever firing. Check all four before calling the work done.

## 1. Eager vs lazy directory
Skills in the eagerly-loaded dir put name+description in context every session; skills in a lazy/librarian dir are only reachable if the agent thinks to ask.
```bash
for d in skills skills-lib skills-disabled; do
  printf "%-16s %s\n" "$d" "$([ -e ~/.claude/$d/<name> ] && echo FOUND || echo -)"
done
```
Proof it registered: the skill's description shows up in the session's available-skills listing. Nothing else counts — a file on disk is not registration.

## 2. Sweeper crons that may demote or publish it
List crons touching the skills dir, then read the filter each one applies:
```bash
crontab -l | grep -iE 'skill|janitor|collect'
grep -nE 'installer|continue|min-age|shutil|move' <janitor script>
```
Typical rule: sweepers act only on skills carrying a marker like `installer: auto-skill`, and skip everything else. Establish which side of that filter your skill sits on — it decides both whether it gets demoted after N idle days **and** whether it gets auto-committed/pushed to a remote.

## 3. A different config dir for other agent roles
If workers/subagents launch with `CLAUDE_CONFIG_DIR` pointed elsewhere, a skill in your own config dir is invisible to them:
```bash
grep -rl 'CLAUDE_CONFIG_DIR' ~/.claude/settings.json <project>/.claude/ <launcher scripts>
```

## 4. The description must match how the user actually asks
The description is the only thing that decides pick-up. Two failure modes:
- **Wrong language.** A description written only in English will not match a user who always asks in their own language. Put the real phrasings, in their language, inside the description.
- **Missing paraphrases.** Enumerate the ways the same request gets worded ("can I delete this?", "who else uses this?", "what does this affect?") rather than one canonical phrasing.
Also state the anti-triggers ("do NOT use for <cheaper alternative>") or it gets pulled into tasks it loses at. Re-check the description length against the platform cap, and note the added always-loaded token cost — an unused skill is a per-session tax paid for nothing.

## Trap: "read-only" inspection scripts that write
Before running a repo-collector or sync script "just to look", grep it for a dry-run flag. Some commit unconditionally and only gate the `push` behind a flag, so an inspection run silently creates a commit.
```bash
grep -nE 'dry.?run|--apply|commit\(|_git\(.*commit' <script>
```
If there is no dry-run path, read the code instead of running it.
