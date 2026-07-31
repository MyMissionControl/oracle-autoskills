---
name: scaffold-nextjs-prisma-bleeding-edge
description: Scaffold a fresh Next.js+Prisma+auth backend when npm resolves brand-new majors (Prisma 7 driver-adapters, moved config, Next/TS version mismatches) instead of the versions tutorials assume
installer: auto-skill
created_at: 2026-07-31T08:49:06+07:00
created_session: 
trigger: error-recovery
created_by: bob
category: backend
content_hash: 17f423a0abf4a3df08b26fd4b9d5e8484c911495a1e558a2022324657d10ba22
---
## When to use

Scaffolding a brand-new Next.js (App Router, TypeScript) + Prisma + cookie-session-auth backend from an empty repo, when npm resolves the latest major versions of `next`/`prisma`/`typescript` and those turn out to be much newer than commonly-documented examples (e.g. Prisma 7, TypeScript 7, Next 16). These majors changed conventions in ways that break the "classic" tutorials.

## Procedure

1. `npm init -y`, then install runtime deps (`next react react-dom @prisma/client bcrypt jose`) and dev deps (`typescript @types/node @types/react @types/react-dom prisma vitest tsx dotenv`). Check what actually resolved with `node -e "console.log(require('./package.json').dependencies)"` — don't assume version numbers.

2. `npx prisma init --datasource-provider sqlite`. Inspect the generated `prisma/schema.prisma` and `prisma.config.ts` before hand-writing anything — recent Prisma majors changed the generator block (`provider = "prisma-client"` with an explicit `output` path, replacing `prisma-client-js`) and moved the datasource URL out of the schema file into `prisma.config.ts`'s `datasource.url`. `prisma init` may also drop unrelated tool-skill directories (`.claude/skills/`, `.windsurf/skills/`, `.agents/skills/`, `skills-lock.json`) into the repo — delete those if they're out of scope for the task.

3. Write your actual `schema.prisma` models. Run `npx prisma generate` then `npx prisma db push` and check where the `.db` file actually landed (`find . -name "*.db" -not -path "./node_modules/*"`). In Prisma 7, a relative sqlite URL in `prisma.config.ts` resolves relative to the **project root / cwd**, not relative to `prisma/schema.prisma`'s directory like older Prisma did. If a contract/spec wants the db file inside `prisma/`, the `DATABASE_URL` must explicitly say `file:./prisma/dev.db`, not `file:./dev.db`.

4. Try instantiating `new PrismaClient()` in your own code and running it. If it throws `"Pass a driver adapter to the PrismaClient constructor"`, the installed Prisma major requires an explicit driver adapter package — the built-in query engine binary is gone. Install the provider-matching adapter (`@prisma/adapter-{sqlite-driver}`, e.g. `@prisma/adapter-better-sqlite3`) **pinned to the exact same version as `prisma`/`@prisma/client`** (check with `npm view @prisma/adapter-<name> version`), then construct `new PrismaClient({ adapter: new PrismaAdapter({ url: process.env.DATABASE_URL }) })`. Note native adapters (e.g. better-sqlite3) need a real compile step — run that install in the background since it can take 1-2 minutes.

5. For a seed script: check `npx prisma db seed` output before assuming `package.json`'s `"prisma": {"seed": ...}` field still works — recent Prisma majors moved this to `migrations.seed` inside `prisma.config.ts` (e.g. `seed: "tsx prisma/seed.ts"`).

6. Before trusting `npx tsc --noEmit` as your only typecheck signal, also try `npx next build` once. If it fails with something like `"TypeScript X.Y does not provide the compiler API required by Next.js"`, the Next major hasn't caught up to a very new TypeScript major yet. Prefer the documented escape hatch flag (e.g. `experimental.useTypeScriptCli: true` in `next.config.ts`) over downgrading TypeScript, unless the escape hatch doesn't exist for your version pair.

7. For testing App Router route handlers without a running server: import the exported `POST`/`GET` functions directly, build requests with `new NextRequest(new Request(url, {method, headers, body}))`, and read `res.headers.get('set-cookie')` to chain cookie-based auth flows (login → me) across calls in the same test file. Point tests at an isolated sqlite file (different `DATABASE_URL` than dev) via a vitest `globalSetup` that runs `prisma db push` with that env var overridden, and alias the same `@/*` path mapping in `vitest.config.ts`'s `resolve.alias` that `tsconfig.json` declares, since app code imports via `@/lib/...`.

## Why this matters

Tutorials and training data lag bleeding-edge major-version releases by months; when `npm install <pkg>@latest` resolves a version newer than what you've seen documented, do NOT pattern-match on remembered API shapes — read what actually got generated/installed (`prisma init` output, `npm view <pkg> version`, error messages) and adjust. Guessing wastes several failed-install/failed-run cycles; checking first costs one extra command.
