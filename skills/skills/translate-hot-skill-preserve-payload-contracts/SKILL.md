---
name: translate-hot-skill-preserve-payload-contracts
description: 'Use when translating/rewriting a hot SKILL.md whose strings are contracts other components grep for: classify prose vs payload vs trigger, pin payloads byte-identical from git HEAD, verify.'
installer: auto-skill
created_at: 2026-08-05T08:13:04+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-code'
category: 'skills'
content_hash: 3bc3d125854a4db8d1c2a35ade0a84613685aa8de0ed5047466c7bdc8666323c
---
# Translate a hot SKILL.md without breaking its payload contracts

Use when a always-loaded instruction file (`SKILL.md`, `CLAUDE.md`, a prompt template) must switch language or be rewritten wholesale, and some of its strings are **contracts** other components match on. A naive translation silently breaks cross-component triggers and unit tests that assert literal words.

## 1. Classify every string BEFORE editing

Three classes; only class A gets translated.

- **A. prose** — headings, bullets, comments, guardrails. Translate.
- **B. payload** — text the file *sends* (a kickoff/prompt injected into another agent, `send-keys` text, heredocs written to files a human reads) or *shows* (echo/error lines, the sentence you speak to the user). Keep verbatim.
- **C. trigger literal** — a word another component greps for. Keep verbatim, in every occurrence.

Find class C empirically, never by memory — grep the sibling repos and their tests for the literal:

```bash
rtk proxy grep -rn "<literal>" --include="*.sh" --include="*.ts" --include="*.md" <repo> <sibling-repo>/src | head -25
```

A hit inside a **test** (`expect(p).toContain("<literal>")`) or a comment saying *"keep this word or the skill will not detect it"* is proof it is a contract. A sibling implementation of the same payload in the original language is proof class B must not change either.

## 2. Assemble from a skeleton + placeholders pulled from git

Do not retype class B/C strings — substitute them from the committed version so they are byte-identical:

```python
head = subprocess.check_output(['git','show','HEAD:<path>'],text=True).split('\n')
payload = head[N-1]                        # 0-indexed; assert a known prefix first
code    = payload[:payload.rindex('  # ')] # keep code, drop the comment you WILL translate
t = open(SKELETON).read().replace('@@P1@@', payload)
assert '@@' not in t, 'placeholder left'
open('<path>','w').write(t)
```

Put `assert head[N-1].startswith('<known prefix>')` before every index — line numbers drift.

## 3. Verify mechanically, not by reading

```python
print(ok(head[41] in new))                 # payload present byte-identical
print(new.count('<trigger literal>'))      # trigger count >= expected
yaml.safe_load(re.match(r'^---\n(.*?)\n---\n', new, re.S).group(1))   # frontmatter still parses
print(len([l for l in nl if l.startswith('#')]) == len(hs(head)))     # heading parity
print(new.count('```') % 2 == 0)                                      # fences balanced
stray = [(i+1,l) for i,l in enumerate(nl)
         if re.search(r'[<source-script-range>]', l) and not l.startswith(ALLOWED_PREFIXES)]
```

The **stray-source-language scan with an allow-list of payload line prefixes** is the check that earns its keep: it flags both a missed translation and a mangled payload line. On a real run it caught a duplicated markdown `- -` bullet that reading the diff had missed.

## 4. Two follow-ups people forget

- **The implicit language signal dies.** If the file used to be written in the language you speak to the user, that *was* the instruction. Once translated, state it explicitly (`**Talk to the user in <lang>.**`) or the agent will answer in the file's new language.
- **Update the doc that describes the language split** (`CLAUDE.md`, README). If it lists this file as the other language, it now lies to the next agent.

## Gotchas

- Quote the frontmatter `description` if your new text contains `": "`; inside a single-quoted YAML scalar avoid apostrophes.
- A byte-ceiling guard test may exist for a *different* file — check before "fixing" a red test you did not cause, and ask before ratcheting it.
- If the file is reached through a symlink into `~/.claude/skills/`, the edit is live immediately — no install step, and any running agent picks it up on next load.
