/**
 * Mine a Claude Code session transcript for the CONVERSATION — what the human
 * asked, what they decided, what was concluded — and nothing else.
 *
 * Written because arra's Huginn miner (src/huginn/capture.ts, read-only legacy)
 * answers a different question: measured on a real session it kept 11 blobs of
 * bash output and 0 human messages, gated on English-only keywords so Thai never
 * matched, kept the FIRST 12 hits and stopped, and slurped the file whole
 * (163 MB transcript -> 537 MB RSS). Same destination, different extractor.
 */
import crypto from 'crypto';
import fs from 'fs';
import readline from 'readline';

export type TurnKind = 'human' | 'decision' | 'assistant';

export interface Turn {
  kind: TurnKind;
  text: string;
}

export interface ExtractOptions {
  /** How many trailing assistant messages to keep. The conclusion is at the end. */
  assistantTail?: number;
  /** Per-turn clip, so one pasted file cannot become the whole memory. */
  maxTurnChars?: number;
  /** Total budget for the human turns; the middle is dropped when exceeded. */
  maxHumanChars?: number;
  /** Total budget for the recorded decisions. */
  maxDecisionChars?: number;
}

const DEFAULT_ASSISTANT_TAIL = 6;
const DEFAULT_MAX_TURN_CHARS = 1200;
const DEFAULT_MAX_HUMAN_CHARS = 12_000;
const DEFAULT_MAX_DECISION_CHARS = 8_000;

/**
 * Wrappers the harness records as user turns but that no human typed as
 * conversation. Measured in the first live capture of a long session: 479
 * task-notifications, 82 slash-command names and 72 command stdout blocks were
 * filed as things "the user said".
 */
const HARNESS_TAGS = [
  'system-reminder',
  'command-name',
  'command-message',
  'command-args',
  'local-command-stdout',
  'local-command-stderr',
  'task-notification',
];

const HARNESS_TAG_PATTERNS = HARNESS_TAGS.map(
  (tag) => new RegExp(`<${tag}>[\\s\\S]*?</${tag}>`, 'g'),
);

/** Removes harness wrappers; what is left is what a person actually wrote. */
function stripHarnessTags(text: string): string {
  let out = text;
  for (const pattern of HARNESS_TAG_PATTERNS) out = out.replace(pattern, '');
  return out.trim();
}

/**
 * Boilerplate the harness appends to every AskUserQuestion result. It says
 * nothing about what was decided, and repeated across a vault it is the loudest
 * text in the corpus.
 */
const ASK_BOILERPLATE = [
  /\s*Read the answers carefully[\s\S]*$/,
  /\s*You can now continue with these answers in mind\.?\s*$/,
];

function stripAskBoilerplate(text: string): string {
  let out = text;
  for (const pattern of ASK_BOILERPLATE) out = out.replace(pattern, '');
  return out.trim();
}

/**
 * Text our own tooling types into a pane. tmux send-keys is indistinguishable
 * from a person at the harness level — the orchestrator's dispatches arrive with
 * promptSource "typed" and origin.kind "human" — so the separator has to be the
 * generated text itself. Every entry here was counted in the live corpus:
 * dispatches 97, orches nags 50, orchestrator boot prompts 24, team handoffs 5.
 */
const AUTOMATION_PREFIXES = [
  '[งานจาก orchestrator',
  'เตือน:',
  'คุณคือ orchestrator',
];

/** `[<agent>] Team handoff — …` from the team runtime. */
const AUTOMATION_PATTERNS = [/^\[[^\]\n]{1,60}\]\s*\S*\s*Team handoff\b/];

/** Turns that are pure flow control and carry nothing worth remembering. */
const CONTROL_WORDS = new Set(['continue', 'yes', 'no', 'ok', 'okay', 'go', 'y', 'n']);

function isAutomationText(text: string): boolean {
  const t = text.trim();
  if (!t) return true;
  if (CONTROL_WORDS.has(t.toLowerCase())) return true;
  if (AUTOMATION_PREFIXES.some((p) => t.startsWith(p))) return true;
  return AUTOMATION_PATTERNS.some((p) => p.test(t));
}

function clip(text: string, max: number): string {
  const flat = text.trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

function humanText(blocks: unknown[]): string {
  const parts = blocks
    .filter((b): b is { type: string; text?: string } => Boolean(b) && typeof b === 'object')
    .filter((b) => b.type === 'text' && typeof b.text === 'string')
    .map((b) => b.text as string);
  return stripHarnessTags(parts.join('\n'));
}

function resultText(content: unknown): string {
  if (typeof content === 'string') return content.trim();
  if (Array.isArray(content)) {
    return content
      .map((p: any) => (typeof p === 'string' ? p : typeof p?.text === 'string' ? p.text : ''))
      .filter(Boolean)
      .join('\n')
      .trim();
  }
  return '';
}

/**
 * Keeps a run of turns inside a character budget by dropping the MIDDLE: the
 * opening ask and the latest state of a marathon session are both worth more
 * than what happened in hour three.
 */
function budget(turns: Turn[], maxChars: number, kind: TurnKind): Turn[] {
  const total = turns.reduce((n, t) => n + t.text.length, 0);
  if (total <= maxChars) return turns;

  const half = Math.floor(maxChars / 2);
  const head: Turn[] = [];
  const tail: Turn[] = [];
  let headChars = 0;
  let tailChars = 0;

  for (const turn of turns) {
    if (headChars + turn.text.length > half) break;
    head.push(turn);
    headChars += turn.text.length;
  }
  for (let i = turns.length - 1; i >= head.length; i--) {
    if (tailChars + turns[i].text.length > half) break;
    tail.unshift(turns[i]);
    tailChars += turns[i].text.length;
  }

  const dropped = turns.length - head.length - tail.length;
  if (dropped <= 0) return turns;
  return [...head, { kind, text: `… ${dropped} turns omitted (session over budget) …` }, ...tail];
}

/**
 * Accumulates turns while records stream past, so the transcript is never held
 * in memory all at once.
 */
class TurnCollector {
  private readonly assistantTail: number;
  private readonly maxTurnChars: number;
  private readonly humans: Turn[] = [];
  private readonly decisions: Turn[] = [];
  private readonly assistants: Turn[] = [];
  /** tool_use ids belonging to AskUserQuestion — their results are the human's choice. */
  private readonly askIds = new Set<string>();

  private readonly maxHumanChars: number;
  private readonly maxDecisionChars: number;

  constructor(options: ExtractOptions = {}) {
    this.assistantTail = options.assistantTail ?? DEFAULT_ASSISTANT_TAIL;
    this.maxTurnChars = options.maxTurnChars ?? DEFAULT_MAX_TURN_CHARS;
    this.maxHumanChars = options.maxHumanChars ?? DEFAULT_MAX_HUMAN_CHARS;
    this.maxDecisionChars = options.maxDecisionChars ?? DEFAULT_MAX_DECISION_CHARS;
  }

  /**
   * A user record only counts as speech when the harness stamped it as typed by
   * a person. Automation drives worker panes with tmux send-keys, and those
   * turns are indistinguishable from a human turn except for this field.
   */
  private static typedByHuman(record: any): boolean {
    return record?.origin?.kind === 'human';
  }

  add(record: any): void {
    if (!record || typeof record !== 'object') return;
    if (record.isMeta || record.isSidechain) return;

    const blocks = record?.message?.content;

    // Headless / SDK sessions record a human turn as a bare string; the VS Code
    // extension records the same turn as a [{type:'text'}] list.
    if (record.type === 'user' && typeof blocks === 'string') {
      if (!TurnCollector.typedByHuman(record)) return;
      const bare = stripHarnessTags(blocks);
      if (bare && !isAutomationText(bare)) {
        this.humans.push({ kind: 'human', text: clip(bare, this.maxTurnChars) });
      }
      return;
    }

    if (!Array.isArray(blocks)) return;

    if (record.type === 'assistant') {
      for (const block of blocks) {
        if (!block || typeof block !== 'object') continue;
        if (block.type === 'tool_use' && block.name === 'AskUserQuestion' && block.id) {
          this.askIds.add(block.id);
        }
        if (block.type === 'text' && typeof block.text === 'string' && block.text.trim()) {
          this.assistants.push({ kind: 'assistant', text: clip(block.text, this.maxTurnChars) });
          if (this.assistants.length > this.assistantTail) this.assistants.shift();
        }
      }
      return;
    }

    if (record.type !== 'user') return;

    for (const block of blocks) {
      if (!block || typeof block !== 'object') continue;
      if (block.type === 'tool_result' && this.askIds.has(block.tool_use_id)) {
        const text = stripAskBoilerplate(resultText(block.content));
        if (text) this.decisions.push({ kind: 'decision', text: clip(text, this.maxTurnChars) });
      }
    }

    if (!TurnCollector.typedByHuman(record)) return;
    const text = humanText(blocks);
    if (text && !isAutomationText(text)) {
      this.humans.push({ kind: 'human', text: clip(text, this.maxTurnChars) });
    }
  }

  turns(): Turn[] {
    return [
      ...budget(this.humans, this.maxHumanChars, 'human'),
      ...budget(this.decisions, this.maxDecisionChars, 'decision'),
      ...this.assistants,
    ];
  }
}

export function extractTurnsFromRecords(records: Iterable<unknown>, options: ExtractOptions = {}): Turn[] {
  const collector = new TurnCollector(options);
  for (const record of records) collector.add(record);
  return collector.turns();
}

/** Streams one JSON record per line; a malformed line is skipped, not fatal. */
export async function* readTranscriptRecords(filePath: string): AsyncGenerator<unknown> {
  const stream = fs.createReadStream(filePath, { encoding: 'utf-8' });
  const lines = readline.createInterface({ input: stream, crlfDelay: Infinity });
  try {
    for await (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        yield JSON.parse(trimmed);
      } catch {
        continue;
      }
    }
  } finally {
    lines.close();
    stream.destroy();
  }
}

export async function extractTurns(filePath: string, options: ExtractOptions = {}): Promise<Turn[]> {
  const collector = new TurnCollector(options);
  for await (const record of readTranscriptRecords(filePath)) collector.add(record);
  return collector.turns();
}

export interface FormatOptions {
  sessionId: string;
  cwd: string;
  transcriptPath: string;
  capturedAt: Date;
  turns: Turn[];
}

export function formatCapture(options: FormatOptions): string {
  const { sessionId, cwd, transcriptPath, capturedAt, turns } = options;
  const of = (kind: TurnKind) => turns.filter((t) => t.kind === kind);
  const humans = of('human');
  const decisions = of('decision');
  const assistants = of('assistant');

  const where = cwd.split('/').filter(Boolean).pop() ?? 'session';
  const headline = humans[0]?.text ?? '(no human turn)';
  const lines: string[] = [
    `Session ${capturedAt.toISOString().slice(0, 10)} · ${where} · ${clip(headline, 90)}`,
    '',
  ];

  if (humans.length) {
    lines.push('## Asked', ...humans.map((t) => `- ${t.text}`), '');
  }
  if (decisions.length) {
    lines.push('## Decisions', ...decisions.map((t) => `- ${t.text}`), '');
  }
  if (assistants.length) {
    lines.push('## Concluded', ...assistants.map((t) => `- ${t.text}`), '');
  }

  lines.push(
    '---',
    `Session: ${sessionId}`,
    `Transcript: ${transcriptPath}`,
    `Captured: ${capturedAt.toISOString()} by the SessionEnd capture hook.`,
  );
  return lines.join('\n');
}

export interface HookInput {
  transcriptPath?: string;
  sessionId?: string;
  cwd?: string;
  /** Why the session ended — the only clue available when a capture is skipped. */
  reason?: string;
}

/** SessionEnd hook stdin. Verified live against claude 2.1.252. */
export function parseHookInput(raw: string): HookInput {
  let parsed: any = null;
  try {
    parsed = JSON.parse(raw.trim());
  } catch {
    return {};
  }
  if (!parsed || typeof parsed !== 'object') return {};
  const out: HookInput = {};
  if (typeof parsed.transcript_path === 'string') out.transcriptPath = parsed.transcript_path;
  if (typeof parsed.session_id === 'string') out.sessionId = parsed.session_id;
  if (typeof parsed.cwd === 'string') out.cwd = parsed.cwd;
  if (typeof parsed.reason === 'string') out.reason = parsed.reason;
  return out;
}

/** Minimum human text before a session is worth a memory entry. */
const MIN_HUMAN_CHARS = 8;

export function captureDecision(turns: Turn[]): { capture: boolean; reason?: string } {
  const humans = turns.filter((t) => t.kind === 'human');
  if (humans.length === 0) return { capture: false, reason: 'no-human-turn' };
  const total = humans.reduce((n, t) => n + t.text.length, 0);
  if (total < MIN_HUMAN_CHARS) return { capture: false, reason: 'too-short' };
  return { capture: true };
}

export interface CaptureRecord {
  hash: string;
  capturedAt: string;
  learningId?: string;
}

export type RecaptureAction =
  | { action: 'write' }
  | { action: 'skip' }
  | { action: 'replace'; replaces: string };

/**
 * SessionEnd fires again when a session is resumed (--continue/--resume), with a
 * fuller transcript and therefore a different hash. Writing that as a new entry
 * leaves the vault holding several near-identical memories of one conversation,
 * so the newer capture replaces the older one.
 */
export function recaptureDecision(
  state: Record<string, CaptureRecord>,
  sessionId: string,
  hash: string,
): RecaptureAction {
  const previous = state[sessionId];
  if (!previous) return { action: 'write' };
  if (previous.hash === hash) return { action: 'skip' };
  if (!previous.learningId) return { action: 'write' };
  return { action: 'replace', replaces: previous.learningId };
}

/**
 * Identity of a conversation, for dedup across re-runs of the hook. Hashes the
 * TURNS only — hashing the rendered document made every re-run look like new
 * content, because the document carries its own capture timestamp.
 */
export function contentHash(turns: Turn[]): string {
  const canonical = turns.map((t) => `${t.kind}:${t.text}`).join('\n');
  return crypto.createHash('sha256').update(canonical).digest('hex').slice(0, 32);
}
