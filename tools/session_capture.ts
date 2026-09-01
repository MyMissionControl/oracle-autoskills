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
}

const DEFAULT_ASSISTANT_TAIL = 6;
const DEFAULT_MAX_TURN_CHARS = 1200;

const SYSTEM_REMINDER = /<system-reminder>[\s\S]*?<\/system-reminder>/g;

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

function clip(text: string, max: number): string {
  const flat = text.trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

function humanText(blocks: unknown[]): string {
  const parts = blocks
    .filter((b): b is { type: string; text?: string } => Boolean(b) && typeof b === 'object')
    .filter((b) => b.type === 'text' && typeof b.text === 'string')
    .map((b) => b.text as string);
  return parts.join('\n').replace(SYSTEM_REMINDER, '').trim();
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

  constructor(options: ExtractOptions = {}) {
    this.assistantTail = options.assistantTail ?? DEFAULT_ASSISTANT_TAIL;
    this.maxTurnChars = options.maxTurnChars ?? DEFAULT_MAX_TURN_CHARS;
  }

  add(record: any): void {
    if (!record || typeof record !== 'object') return;
    if (record.isMeta || record.isSidechain) return;

    const blocks = record?.message?.content;

    // Headless / SDK sessions record a human turn as a bare string; the VS Code
    // extension records the same turn as a [{type:'text'}] list.
    if (record.type === 'user' && typeof blocks === 'string') {
      const bare = blocks.replace(SYSTEM_REMINDER, '').trim();
      if (bare) this.humans.push({ kind: 'human', text: clip(bare, this.maxTurnChars) });
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

    const text = humanText(blocks);
    if (text) this.humans.push({ kind: 'human', text: clip(text, this.maxTurnChars) });
  }

  turns(): Turn[] {
    return [...this.humans, ...this.decisions, ...this.assistants];
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
