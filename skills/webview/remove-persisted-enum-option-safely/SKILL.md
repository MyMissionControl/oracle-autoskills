---
name: remove-persisted-enum-option-safely
description: 'Use when removing/merging a value from an enum/option list that is persisted to disk AND shown in an HTML <select>. Prevents silent mass-mutation from unmigrated stored values.'
installer: auto-skill
created_at: 2026-08-07T16:08:42+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-code'
category: 'webview'
content_hash: f1ea1fc6d2c9091fd89d6d6a794bd6d534c0c7c7fc8c27cf45ece29c35133d64
---
---
name: remove-persisted-enum-option-safely
description: Use when removing or merging a value from an enum/option list (a role, status, type) that is persisted to disk/config AND rendered in an HTML <select>. Prevents the silent mass-mutation an unmigrated stored value causes.
---

# Removing/merging a persisted enum option without silent data mutation

When you drop a value from an option list (e.g. `ROLE_OPTIONS`, a status enum) that
users have already stored, two non-obvious hazards bite:

## The core gotcha
An HTML `<select>` whose current stored value is **not** among its `<option>`s does
NOT stay blank — the browser silently selects the **FIRST option**. On the next
Save, the read-back value is that first option, so every legacy record is silently
rewritten to it. If the first option is a privileged value (e.g. `orchestrator`,
`admin`), you just mass-promoted everyone with no error and no diff shown.

## Procedure

1. **Audit every consumer of the value before editing.** grep the codebase (and any
   sibling repos it shares the field with — a CLI, a runtime) for the literal values.
   Classify each touchpoint: does it distinguish the values you're merging, or only
   special-case ONE value and treat the rest as a bucket? If the merge target is
   already the bucket's meaning, the change is a relabel and most code is unaffected.
2. **Check the cross-repo contract.** If another tool reads/writes the field (via a
   CLI flag, a shared JSON store), confirm it does NOT enum-validate — otherwise the
   new value gets rejected. Cite the file:line that stores/validates it.
3. **Normalize at the LOAD boundary, not on disk.** Add `normalizeValue(v)` that maps
   every legacy/blank/unknown value to the new vocabulary and passes the still-valid
   ones through. Apply it at the single function that reads the persisted record into
   memory (the funnel that feeds BOTH render AND the save-diff baseline). This makes
   the `<select>` receive an in-vocab value (renders correctly) and makes the diff
   compare normalized-old vs read-back-new as EQUAL → no spurious write/re-invite.
   Do NOT bulk-rewrite the disk file; leave legacy literals until a genuine edit
   touches that record — harmless once all consumers ignore the distinction.
4. **Keep the diff/compare function a RAW compare** (don't normalize inside it). Its
   unit tests that use the old literals act as a canary that normalization wasn't
   accidentally moved there. Only update the tests of the LOAD funnel's expected output.
5. **Belt-and-suspenders on the render:** make the `<select>` builder unshift an
   out-of-vocab stored value into its own options (slice first — never mutate the
   shared option array) so any future/bypassed value can never fall to option #1.
6. **Prove it end-to-end on a REAL legacy record**, not just unit tests: load →
   normalize → simulate an unedited Save → assert the diff shows zero changes and
   nobody was promoted to the privileged first option.
