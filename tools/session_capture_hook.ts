#!/usr/bin/env bun
/**
 * SessionEnd hook: file one Oracle learning per human conversation.
 *
 * Wire it in ~/.claude/settings.json:
 *   "SessionEnd": [{ "hooks": [{ "type": "command",
 *     "command": "<bun> <this file>" }] }]
 *
 * SessionEnd (not Stop) is deliberate: Stop fires at the end of EVERY turn, so
 * it would file a fresh, ever-growing entry per turn. Verified live on claude
 * 2.1.252 that SessionEnd fires once and carries transcript_path/session_id/cwd.
 *
 * Persistence reuses arra's handleLearn unchanged (import only — arra is
 * read-only legacy), so entries land in ~/.oracle/ψ/memory/learnings/ AND in the
 * oracle_documents index exactly like a hand-written oracle_learn.
 *
 * Never blocks the session: every failure path prints JSON and exits 0.
 */
import fs from 'fs';
import os from 'os';
import path from 'path';
import { captureDecision, extractTurns, formatCapture, parseHookInput } from './session_capture.ts';

const ARRA_ROOT =
  process.env.ARRA_ORACLE_ROOT ||
  path.join(os.homedir(), 'Desktop/soulbrew/github.com/Soul-Brews-Studio/arra-oracle-v3');
const DATA_DIR = process.env.ORACLE_DATA_DIR || path.join(os.homedir(), '.oracle');
const STATE_PATH = process.env.SESSION_CAPTURE_STATE || path.join(DATA_DIR, 'session-captures.json');

type State = Record<string, { hash: string; capturedAt: string; learningId?: string }>;

const LOG_PATH = process.env.SESSION_CAPTURE_LOG || path.join(DATA_DIR, 'session-capture.log');

/**
 * Every invocation leaves one line, skips included. Without it a hook that
 * silently stops firing is indistinguishable from a run of quiet sessions —
 * which is exactly how the Huginn capture went unnoticed for five months.
 */
function logLine(payload: Record<string, unknown>): void {
  try {
    fs.mkdirSync(path.dirname(LOG_PATH), { recursive: true });
    const summary = [
      new Date().toISOString(),
      String(payload.sessionId ?? '-'),
      payload.ok === false ? `error:${payload.error}` : String(payload.skipped ?? 'captured'),
      payload.turns !== undefined ? `turns=${payload.turns}` : '',
      payload.file ? String(payload.file) : '',
    ]
      .filter(Boolean)
      .join('  ');
    fs.appendFileSync(LOG_PATH, `${summary}\n`);
  } catch {
    // logging must never break session end
  }
}

function done(payload: Record<string, unknown>): never {
  logLine(payload);
  console.log(JSON.stringify(payload));
  process.exit(0);
}

function readState(): State {
  try {
    const parsed = JSON.parse(fs.readFileSync(STATE_PATH, 'utf-8'));
    return parsed && typeof parsed === 'object' ? (parsed as State) : {};
  } catch {
    return {};
  }
}

function writeState(state: State): void {
  fs.mkdirSync(path.dirname(STATE_PATH), { recursive: true });
  const tmp = `${STATE_PATH}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(state, null, 2));
  fs.renameSync(tmp, STATE_PATH);
}

async function main(): Promise<void> {
  if (['1', 'true', 'yes', 'on'].includes(String(process.env.SESSION_CAPTURE_DISABLE ?? '').toLowerCase())) {
    done({ ok: true, skipped: 'disabled' });
  }

  const raw = await new Response(Bun.stdin.stream()).text();
  const input = parseHookInput(raw);
  const transcriptPath = input.transcriptPath || Bun.argv[2];
  if (!transcriptPath) done({ ok: true, skipped: 'no-transcript-path' });
  if (!fs.existsSync(transcriptPath)) done({ ok: true, skipped: 'missing-transcript' });

  const sessionId = input.sessionId || path.basename(transcriptPath).replace(/\.jsonl$/i, '');
  const cwd = input.cwd || process.cwd();

  const turns = await extractTurns(transcriptPath);
  const decision = captureDecision(turns);
  if (!decision.capture) done({ ok: true, skipped: decision.reason, sessionId });

  const capturedAt = new Date();
  const pattern = formatCapture({ sessionId, cwd, transcriptPath, capturedAt, turns });
  const hash = new Bun.CryptoHasher('sha256').update(pattern).digest('hex').slice(0, 32);

  const state = readState();
  if (state[sessionId]?.hash === hash) done({ ok: true, skipped: 'duplicate', sessionId });

  const { handleLearn } = await import(path.join(ARRA_ROOT, 'src/server/handlers.ts'));
  const result: any = handleLearn(
    pattern,
    `session-capture:${sessionId}`,
    ['session-capture', 'conversation', `session-${sessionId}`],
    'session-capture',
    undefined,
    cwd,
  );

  state[sessionId] = { hash, capturedAt: capturedAt.toISOString(), learningId: result?.id };
  writeState(state);

  done({
    ok: true,
    sessionId,
    learningId: result?.id,
    file: result?.file,
    turns: turns.length,
  });
}

main().catch((error: any) => {
  done({ ok: false, error: error?.message ?? String(error) });
});
