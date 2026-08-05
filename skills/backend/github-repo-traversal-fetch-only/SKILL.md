---
name: github-repo-traversal-fetch-only
description: Scan/download a GitHub repo's files via REST tree API + raw.githubusercontent.com, no git clone or new deps
installer: auto-skill
created_at: 2026-07-16T10:13:23+00:00
created_session: 
trigger: reusable-workflow
created_by: jack
category: backend
content_hash: 002f91509f8796ba363307d601c3eec85cec4f1b37ad59459f5c4329e1783383
---
## Traverse a GitHub repo's files via REST API — no git clone, no new dependencies

Use when a task needs to scan every file/folder in a GitHub repo (e.g. find files
matching a pattern, or copy a specific subfolder's contents) from a Node/JS backend,
and you want to avoid shelling out to `git` or adding a tar/zip/clone npm dependency.

### Steps

1. Resolve `{owner, repo}` from the repo URL — strip a trailing `.git`, ignore any
   extra path segments (e.g. `/tree/<branch>`).
2. `GET https://api.github.com/repos/{owner}/{repo}` → read `default_branch`
   (skip if the caller already knows the ref to use).
3. `GET https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1`
   → this returns the **entire** file tree (every path, `blob`/`tree` type) in one
   call. This is the key trick — no incremental directory-by-directory listing needed.
4. Filter the returned `tree` array client-side for whatever you're looking for
   (e.g. `type === 'blob' && basename(path).toLowerCase() === 'target-file.ext'`).
5. To fetch a specific file's content: `GET https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}`
   — URL-encode each path segment individually (not the whole path) so `/` stays a
   separator. Plain `fetch`, no SDK.
6. If a `GITHUB_TOKEN`-style env var is present, add `Authorization: Bearer <token>`
   to all three calls — same header works on both `api.github.com` and
   `raw.githubusercontent.com`, and is required for private repos.
7. All of this runs on the global `fetch` (Node 18+) — zero new npm dependencies,
   no `git` binary requirement, no tar/zip parsing library.

### Gotcha

Unauthenticated GitHub API calls are rate-limited (~60/hr per IP) — fine for
occasional use or mocked tests, but flag to the user if this will run at real
volume in production (they'll want a `GITHUB_TOKEN` configured, which raises the
limit substantially).

### Testing

Mock the three fetch destinations by URL prefix (`api.github.com/repos/{o}/{r}`
exact match, `.../git/trees/` substring, `raw.githubusercontent.com/{o}/{r}/{branch}/`
prefix) via `vi.stubGlobal('fetch', ...)` — no real network needed, and it exercises
the exact same code path used against the real API.
