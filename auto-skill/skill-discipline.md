<!--
  Skill Discipline block — mechanism A of soulbrew's Hermes-style auto skill creation.
  This is meant to be pasted into an agent's CLAUDE.md (always-on context) so the
  agent self-judges the 4 triggers at the end of every task. It pairs with the
  non-blocking writer at .claude/skills/auto-skill/scripts/auto_skill.py.
  Adjust the script path if the auto-skill folder lives elsewhere.
-->

## Skill Discipline — auto-capture reusable procedures

At the END of a task, before you finish your turn, silently self-judge whether what you just did is worth saving as a reusable **skill**. Save one ONLY when it would genuinely help a future task — routine work saves NOTHING.

**Trigger on ANY of these** (judged from your own context this turn):

1. **Complex task** — you completed a non-trivial task over several distinct tool steps AND the sequence is worth repeating (not one-off).
2. **Error recovery** — you hit a real dead-end/error and found a working path that was not obvious. Capture the working path so it is never re-derived.
3. **User correction** — the user corrected *how* you did something. Capture the corrected approach as the canonical way.
4. **Reusable workflow** — you discovered a multi-step procedure that will recur.

Triggers 1 and 4 you can notice from tool-call volume; triggers 2 and 3 are semantic — only you can judge them from the conversation.

**Quality bar (avoid skill spam — most turns create nothing):**

- Would a *specific* future task actually load and follow this? If unsure, skip.
- It must be a **procedure** (steps/commands), not a fact or observation. Facts go to `/rrr` or `oracle_learn`, never here.
- One skill per distinct procedure. Never save near-duplicates.

**How to save (NON-BLOCKING — never stop to ask "should I save this?"):**

Write the skill body to a temp file, then call the writer:

```bash
python3 .claude/skills/auto-skill/scripts/auto_skill.py create \
  --name <kebab-case-name> \
  --desc "one line: what it does + when to use it" \
  --trigger <complex-task|error-recovery|user-correction|reusable-workflow> \
  --source <your-oracle-id> \
  --body-file /tmp/<name>.SKILL.md
```

`--source` (WHO made it) is **mandatory** — it is stamped into the skill as
`created_by:`. If your environment already sets `AUTO_SKILL_SOURCE` you can omit
`--source`; otherwise the writer refuses rather than save an anonymous skill.

- Lands in `$AUTO_SKILL_DIR` if set (your oracle's own skills home — set this per oracle so the target is stable), otherwise the **current project's** `.claude/skills/`. Never the shared global dir — so parallel oracles don't collide. Pass `--dir <path>` to override.
- A name clash with *different* content is **refused** (pick a new name); identical content is a silent no-op. Never pass `--force` to overwrite a skill you did not create.
- If you are running **unattended** (an orches worker with no human watching your pane), add `--stage` so it parks in `.pending-skills/` for review instead of going live.

Then note in one line that you saved (or staged) a skill, and finish. Do not block the turn on it.
