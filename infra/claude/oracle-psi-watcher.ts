/**
 * Oracle ψ → ~/.oracle auto-indexer.
 *
 * Watches every vault's ψ/memory/ tree and append-indexes that vault into the
 * live DB (~/.oracle) the moment a memory file changes — independent of /rrr,
 * git commits, or Claude's PostToolUse hook. Append mode → never wipes other
 * vaults.
 *
 * Primary trigger: fs.watch (near-instant). Backstop: a poll reconcile every
 * POLL_MS that catches anything fs.watch missed (new date dirs, new vaults,
 * platforms without recursive watch). Both paths debounce per vault.
 *
 * Run: bun ~/.claude/oracle-psi-watcher.ts   (managed by systemd --user)
 */
import { watch } from 'fs';
import { readdirSync, existsSync, statSync, readdirSync as rd } from 'fs';
import { join } from 'path';

const HOME = '/home/chillox-intern';
const BUN = `${HOME}/.bun/bin/bun`;
const WRAPPER = `${HOME}/.claude/oracle-reindex-append.ts`;
const DATA_DIR = `${HOME}/.oracle`;
const POLL_MS = 10_000;
const DEBOUNCE_MS = 2_000;

// Vector embeddings (semantic search). index-model now embeds only NEW/CHANGED
// docs (incremental via content-hash + ~/.oracle/embed-state-<model>.json), so a
// pass is cheap. Still debounce so a burst of FTS reindexes (commits / /rrr)
// coalesces into ONE incremental pass instead of spawning bun per file change.
// 2026-07-18: point at the FORK's index-model (read-only worktree of branch
// fix/audit-bugs) — the alpha global-install version leaks >3GB and gets
// memcg-killed before finishing, so vector embeds were stale since the 07-17
// migration (embed-state mtime proved it). Revert when upstream fixes the leak.
const INDEX_MODEL = `${HOME}/.arra-fork-indexer/src/scripts/index-model.ts`;
const EMBED_MODEL = 'nomic';            // nomic-embed-text via Ollama (pulled)
const EMBED_DEBOUNCE_MS = 20 * 60_000;  // 20 min (was 60s — 2026-07-06 CPU-storm fix)
const EMBED_TIMEOUT_MS = '600000';      // per-REQUEST cap. 2026-08-30: 120s could never
                                        // pass — one batch of real ψ docs measured >300s on
                                        // CPU-only nomic, so EVERY batch aborted, errors>0,
                                        // saveState() was skipped and the same docs re-embedded
                                        // every debounce forever (permanent CPU burn).
const EMBED_BATCH_SIZE = '4';           // smaller batches survive cold start + lower embed peak memory (OOM mitigation 2026-07-18)
                                        // 10 -> 4 on 2026-08-30: ~30s/doc measured, so a batch
                                        // now lands ~120s — well inside EMBED_TIMEOUT_MS.
// 2026-09-03: this was EMBED_HARD_KILL_MS = 30 min of WALL CLOCK, which killed passes
// that were working fine and only slow. Measured that day: a 796-doc backlog took 35.5 min
// (0.25-0.42 docs/s, rate set by CPU contention -- ollama itself answers a warm embed in
// 0.13s), so every pass died at minute 30, saveState() never ran, and the next pass redid
// the same work forever -- a livelock, not a slowdown. A wall-clock cap cannot tell
// "slow" from "stuck"; time since the last byte of output can.
// 15 min and not 10: ORACLE_EMBED_TIMEOUT_MS bounds ONE request at 10 min, so a single
// legitimately-slow batch must never read as a stall.
const EMBED_STALL_MS = 15 * 60_000;     // kill a pass only if it emits NOTHING for this long

// Base dirs whose immediate children may be oracle vaults.
const BASES = [`${HOME}/Desktop/soulbrew/github.com/fufu-2345`, HOME];
// Never index this stale orphan vault (live server does not read it).
const EXCLUDE = ['/.arra-oracle-v2'];

function log(msg: string) {
  // Date.now via performance origin is fine here (not a workflow script).
  console.log(`[psi-watch ${new Date().toISOString()}] ${msg}`);
}

function discoverVaults(): string[] {
  const out = new Set<string>();
  for (const base of BASES) {
    let entries: string[] = [];
    try { entries = readdirSync(base); } catch { continue; }
    for (const e of entries) {
      const root = join(base, e);
      if (EXCLUDE.some((x) => root.includes(x))) continue;
      try {
        if (existsSync(join(root, 'ψ', 'memory'))) out.add(root);
      } catch { /* ignore */ }
    }
  }
  return [...out];
}

function maxMtimeMd(dir: string): number {
  let mx = 0;
  let stack = [dir];
  while (stack.length) {
    const d = stack.pop()!;
    let items: string[] = [];
    try { items = rd(d); } catch { continue; }
    for (const it of items) {
      const p = join(d, it);
      let st;
      try { st = statSync(p); } catch { continue; }
      if (st.isDirectory()) stack.push(p);
      else if (it.endsWith('.md')) mx = Math.max(mx, st.mtimeMs);
    }
  }
  return mx;
}

const lastSeen = new Map<string, number>();      // vault -> max mtime indexed
const debounce = new Map<string, ReturnType<typeof setTimeout>>();
const watched = new Set<string>();               // vaults with an fs.watch attached
let indexing = false;
const queue: string[] = [];
let embedTimer: ReturnType<typeof setTimeout> | null = null;
let embedding = false;
let embedPending = false;

function enqueue(vault: string) {
  if (!queue.includes(vault)) queue.push(vault);
  drain();
}

async function drain() {
  if (indexing) return;
  const vault = queue.shift();
  if (!vault) return;
  indexing = true;
  try {
    const proc = Bun.spawn([BUN, WRAPPER], {
      env: { ...process.env, ORACLE_REPO_ROOT: vault, ORACLE_DATA_DIR: DATA_DIR, ORACLE_BACKUP_KEEP: '20' },
      stdout: 'ignore', stderr: 'ignore',
    });
    await proc.exited;
    log(`indexed ${vault} (exit ${proc.exitCode})`);
    scheduleEmbed();
  } catch (e) {
    log(`index FAILED ${vault}: ${e}`);
  } finally {
    indexing = false;
    if (queue.length) drain();
  }
}

// Schedule a debounced global embed. Coalesces rapid FTS reindexes into one
// Ollama pass after activity settles.
function scheduleEmbed() {
  if (embedTimer) clearTimeout(embedTimer);
  embedTimer = setTimeout(() => { embedTimer = null; runEmbed(); }, EMBED_DEBOUNCE_MS);
}

// Rebuild the vector collection. Best-effort: a failure (e.g. Ollama down)
// is logged and never crashes the watcher; keyword search is unaffected. If
// changes arrive mid-embed, a follow-up pass is scheduled.
async function runEmbed() {
  if (embedding) { embedPending = true; return; }
  embedding = true;
  try {
    const proc = Bun.spawn([BUN, INDEX_MODEL, EMBED_MODEL], {
      env: {
        ...process.env,
        ORACLE_DATA_DIR: DATA_DIR,
        ORACLE_EMBED_TIMEOUT_MS: EMBED_TIMEOUT_MS,
        ORACLE_EMBED_BATCH_SIZE: EMBED_BATCH_SIZE,
      },
      // 2026-08-30: capture output. It used to be discarded, so a pass that
      // failed every batch for hours left no trace anywhere.
      stdout: 'pipe', stderr: 'pipe',
    });
    // Kill only a pass that has gone SILENT, never one that is merely slow.
    // The output must be STREAMED: `new Response(stream).text()` resolves only at exit,
    // so the old code could not observe progress even in principle.
    let killed = false;
    let lastOutputAt = Date.now();
    let outBuf = '';
    let errBuf = '';
    const drain = async (stream: ReadableStream<Uint8Array> | null, sink: (t: string) => void): Promise<void> => {
      if (!stream) return;
      const decoder = new TextDecoder();
      try {
        for await (const chunk of stream as unknown as AsyncIterable<Uint8Array>) {
          lastOutputAt = Date.now();
          sink(decoder.decode(chunk, { stream: true }));
        }
      } catch { /* stream torn down by kill() -- keep whatever we already read */ }
    };
    const watchdog = setInterval(() => {
      if (Date.now() - lastOutputAt <= EMBED_STALL_MS) return;
      // Second strike escalates. SIGTERM is not always fatal (proved 2026-09-03: a shell
      // waiting on a child ran 7s past its kill), and a pass that survives it would hold
      // `embedding = true` forever and block every later pass -- the exact silent wedge
      // this watchdog exists to prevent.
      if (killed) { proc.kill(9); return; }
      killed = true;
      proc.kill();
    }, 30_000);
    const streams = Promise.all([drain(proc.stdout as any, (t) => { outBuf += t; }), drain(proc.stderr as any, (t) => { errBuf += t; })]);
    // Never wait on the pipes ALONE. A pipe stays open until every process holding its
    // write end exits, so one orphaned grandchild keeps this await pending forever and
    // `embedding` never clears -- the same silent wedge, one level down. Proved
    // 2026-09-03: a killed bash whose `sleep` child held stdout blocked the read for the
    // child's full lifetime. Whichever finishes first wins; partial output is kept.
    await Promise.race([streams, proc.exited.then(() => Bun.sleep(5_000))]);
    clearInterval(watchdog);
    const out = outBuf, err = errBuf;
    const tail = `${out}${err}`.trim().split('\n').slice(-4).join(' | ');
    log(`embedded (model ${EMBED_MODEL}) exit ${proc.exitCode}${killed ? ` [KILLED: no output for ${EMBED_STALL_MS / 60_000} min]` : ''}${tail ? ` :: ${tail}` : ''}`);
  } catch (e) {
    log(`embed FAILED: ${e}`);
  } finally {
    embedding = false;
    if (embedPending) { embedPending = false; scheduleEmbed(); }
  }
}

function scheduleIndex(vault: string) {
  const t = debounce.get(vault);
  if (t) clearTimeout(t);
  debounce.set(vault, setTimeout(() => { debounce.delete(vault); enqueue(vault); }, DEBOUNCE_MS));
}

function attachWatch(vault: string) {
  if (watched.has(vault)) return;
  const memDir = join(vault, 'ψ', 'memory');
  try {
    watch(memDir, { recursive: true }, (_evt, file) => {
      if (file && String(file).endsWith('.md')) scheduleIndex(vault);
    });
    watched.add(vault);
    log(`watching ${memDir}`);
  } catch (e) {
    // recursive watch unsupported — poll reconcile still covers this vault.
    log(`watch attach failed for ${memDir} (poll will cover): ${e}`);
  }
}

function reconcile(initial = false) {
  for (const vault of discoverVaults()) {
    attachWatch(vault);
    const mx = maxMtimeMd(join(vault, 'ψ', 'memory'));
    const prev = lastSeen.get(vault);
    if (prev === undefined) {
      // First sight: trust the existing index, set baseline, don't reindex.
      lastSeen.set(vault, mx);
      if (initial) log(`baseline ${vault} @ ${mx}`);
    } else if (mx > prev) {
      lastSeen.set(vault, mx);
      log(`change detected (poll) ${vault}`);
      scheduleIndex(vault);
    }
  }
}

log('starting Oracle ψ watcher');
reconcile(true);
setInterval(() => reconcile(false), POLL_MS);
// Keep alive.
process.on('SIGTERM', () => { log('SIGTERM — exiting'); process.exit(0); });
