/**
 * Contract for the session-capture extractor.
 *
 * Every case here is a measured failure of arra's Huginn miner on a real
 * transcript (2026-09-01): it kept 11 tool-output blobs and 0 human messages,
 * matched English keywords only, took the FIRST 12 matches, and slurped the
 * whole file (163 MB transcript -> 537 MB RSS).
 */
import { describe, expect, test } from 'bun:test';
import fs from 'fs';
import os from 'os';
import path from 'path';
import {
  extractTurnsFromRecords,
  formatCapture,
  readTranscriptRecords,
  extractTurns,
  parseHookInput,
  captureDecision,
} from './session_capture.ts';

/** A real human turn: type=user, content has a text block, no isMeta. */
function humanRecord(text: string, extra: Record<string, unknown> = {}) {
  return {
    type: 'user',
    isSidechain: false,
    message: { role: 'user', content: [{ type: 'text', text }] },
    ...extra,
  };
}

/** Bash/Read output comes back as type=user with a tool_result block. */
function toolResultRecord(toolUseId: string, content: string) {
  return {
    type: 'user',
    message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: toolUseId, content }] },
  };
}

function assistantRecord(blocks: unknown[]) {
  return { type: 'assistant', message: { role: 'assistant', content: blocks } };
}

describe('extractTurnsFromRecords', () => {
  test('keeps what the human typed', () => {
    const turns = extractTurnsFromRecords([
      humanRecord('เช็คหน่อยทำไม graphify หยุดทำ'),
    ]);
    expect(turns).toEqual([{ kind: 'human', text: 'เช็คหน่อยทำไม graphify หยุดทำ' }]);
  });

  test('keeps a human turn whose content is a bare string, not a block list', () => {
    // Headless (`claude -p`) and SDK sessions record the prompt this way;
    // the VS Code extension records a [{type:'text'}] list for the same thing.
    const turns = extractTurnsFromRecords([
      { type: 'user', isSidechain: false, promptSource: 'sdk', message: { role: 'user', content: 'ทำไมกราฟโค้ดไม่ช่วยค้นบทสนทนาเก่า' } },
    ]);
    expect(turns).toEqual([{ kind: 'human', text: 'ทำไมกราฟโค้ดไม่ช่วยค้นบทสนทนาเก่า' }]);
  });

  test('drops tool output — the blobs Huginn mistook for conversation', () => {
    const turns = extractTurnsFromRecords([
      assistantRecord([{ type: 'tool_use', id: 'tu_1', name: 'Bash', input: { command: 'crontab -l' } }]),
      toolResultRecord('tu_1', 'CRON_TZ=Asia/Bangkok\n0 18 * * * refresh-graphs.sh'),
    ]);
    expect(turns).toEqual([]);
  });

  test('drops isMeta records — skill text injected as a user turn', () => {
    const turns = extractTurnsFromRecords([
      humanRecord('# Systematic Debugging\n\nALWAYS find root cause', { isMeta: true }),
    ]);
    expect(turns).toEqual([]);
  });

  test('drops sidechain records — subagent chatter is not our session', () => {
    const turns = extractTurnsFromRecords([
      humanRecord('go audit the repo', { isSidechain: true }),
    ]);
    expect(turns).toEqual([]);
  });

  test('keeps a decision the human made in an AskUserQuestion box', () => {
    const turns = extractTurnsFromRecords([
      assistantRecord([{ type: 'tool_use', id: 'tu_9', name: 'AskUserQuestion', input: {} }]),
      toolResultRecord('tu_9', 'The user answered: "เอา graphify ยังไงต่อ?"="เขียนตัวจับเอง ไม่แตะ legacy".'),
    ]);
    expect(turns).toEqual([
      { kind: 'decision', text: 'The user answered: "เอา graphify ยังไงต่อ?"="เขียนตัวจับเอง ไม่แตะ legacy".' },
    ]);
  });

  test('drops the harness boilerplate that trails every AskUserQuestion result', () => {
    const turns = extractTurnsFromRecords([
      assistantRecord([{ type: 'tool_use', id: 'tu_a', name: 'AskUserQuestion', input: {} }]),
      toolResultRecord(
        'tu_a',
        'The user answered: "เอาไง?"="ลุยเลย". Read the answers carefully — they may request clarification, changes, or that you not proceed — and follow what they actually say.',
      ),
      assistantRecord([{ type: 'tool_use', id: 'tu_b', name: 'AskUserQuestion', input: {} }]),
      toolResultRecord(
        'tu_b',
        'Your questions have been answered: "ทางไหน?"="เขียนเอง". You can now continue with these answers in mind.',
      ),
    ]);
    expect(turns.map((t) => t.text)).toEqual([
      'The user answered: "เอาไง?"="ลุยเลย".',
      'Your questions have been answered: "ทางไหน?"="เขียนเอง".',
    ]);
  });

  test('keeps assistant prose and drops its tool_use and thinking blocks', () => {
    const turns = extractTurnsFromRecords([
      assistantRecord([
        { type: 'thinking', thinking: 'let me check the crontab' },
        { type: 'text', text: 'cron ยังวิ่งอยู่ ตัวที่ตายคือฝั่งเรียกใช้' },
        { type: 'tool_use', id: 'tu_2', name: 'Bash', input: { command: 'ls' } },
      ]),
    ]);
    expect(turns).toEqual([{ kind: 'assistant', text: 'cron ยังวิ่งอยู่ ตัวที่ตายคือฝั่งเรียกใช้' }]);
  });

  test('strips system-reminder blocks out of a human turn', () => {
    const turns = extractTurnsFromRecords([
      humanRecord('<system-reminder>\nremembered context\n</system-reminder>\nทำไม graphify หยุดทำ'),
    ]);
    expect(turns).toEqual([{ kind: 'human', text: 'ทำไม graphify หยุดทำ' }]);
  });

  test('a human turn that is only a system-reminder is not a turn', () => {
    const turns = extractTurnsFromRecords([
      humanRecord('<system-reminder>background context</system-reminder>'),
    ]);
    expect(turns).toEqual([]);
  });

  test('keeps every human turn but only the tail of the assistant prose', () => {
    const records = [
      humanRecord('คำถามแรก'),
      assistantRecord([{ type: 'text', text: 'ตอบ 1' }]),
      assistantRecord([{ type: 'text', text: 'ตอบ 2' }]),
      assistantRecord([{ type: 'text', text: 'ตอบ 3' }]),
      humanRecord('คำถามสุดท้าย'),
      assistantRecord([{ type: 'text', text: 'ตอบ 4' }]),
    ];
    const turns = extractTurnsFromRecords(records, { assistantTail: 2 });
    expect(turns.filter((t) => t.kind === 'human').map((t) => t.text)).toEqual([
      'คำถามแรก',
      'คำถามสุดท้าย',
    ]);
    // Huginn kept the FIRST matches and broke; the conclusion is at the END.
    expect(turns.filter((t) => t.kind === 'assistant').map((t) => t.text)).toEqual([
      'ตอบ 3',
      'ตอบ 4',
    ]);
  });

  test('clips one very long turn instead of carrying a whole file into the vault', () => {
    const turns = extractTurnsFromRecords([humanRecord('x'.repeat(5000))], { maxTurnChars: 100 });
    expect(turns[0].text.length).toBeLessThanOrEqual(100);
  });
});

describe('readTranscriptRecords', () => {
  test('yields records line by line and survives a malformed line', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sc-'));
    const file = path.join(dir, 'session.jsonl');
    fs.writeFileSync(
      file,
      [JSON.stringify(humanRecord('หนึ่ง')), '{not json', JSON.stringify(humanRecord('สอง')), ''].join('\n'),
    );
    const seen: unknown[] = [];
    for await (const rec of readTranscriptRecords(file)) seen.push(rec);
    expect(seen.length).toBe(2);
    fs.rmSync(dir, { recursive: true, force: true });
  });

  test('does not load the whole transcript into memory', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sc-big-'));
    const file = path.join(dir, 'big.jsonl');
    // ~120 MB of transcript: readFileSync would show up as >120 MB of RSS.
    const filler = JSON.stringify(toolResultRecord('tu_x', 'y'.repeat(60_000)));
    const out = fs.createWriteStream(file);
    for (let i = 0; i < 2000; i++) out.write(filler + '\n');
    out.write(JSON.stringify(humanRecord('คำถามท้ายไฟล์')) + '\n');
    await new Promise((r) => out.end(r));
    expect(fs.statSync(file).size).toBeGreaterThan(100 * 1024 * 1024);

    Bun.gc(true);
    const before = process.memoryUsage().rss;
    const turns = await extractTurns(file);
    const grewMB = (process.memoryUsage().rss - before) / 1048576;

    expect(turns).toEqual([{ kind: 'human', text: 'คำถามท้ายไฟล์' }]);
    expect(grewMB).toBeLessThan(80);
    fs.rmSync(dir, { recursive: true, force: true });
  }, 60_000);
});

describe('formatCapture', () => {
  test('leads with the human question so the vault filename is searchable', () => {
    const doc = formatCapture({
      sessionId: 'abc-123',
      cwd: '/home/u/Desktop/soulbrew',
      transcriptPath: '/tmp/abc-123.jsonl',
      capturedAt: new Date('2026-09-01T14:00:00Z'),
      turns: [
        { kind: 'human', text: 'ทำไม graphify หยุดทำ' },
        { kind: 'decision', text: 'The user answered: "..."="เขียนตัวจับเอง"' },
        { kind: 'assistant', text: 'cron ยังวิ่ง ตัวที่ตายคือฝั่งเรียกใช้' },
      ],
    });
    expect(doc.split('\n')[0]).toContain('ทำไม graphify หยุดทำ');
    expect(doc).toContain('เขียนตัวจับเอง');
    expect(doc).toContain('/tmp/abc-123.jsonl');
  });

  test('marks a session that reached no decision', () => {
    const doc = formatCapture({
      sessionId: 'abc',
      cwd: '/x',
      transcriptPath: '/tmp/abc.jsonl',
      capturedAt: new Date('2026-09-01T14:00:00Z'),
      turns: [{ kind: 'human', text: 'แค่ถามเฉยๆ' }],
    });
    expect(doc).not.toContain('## Decisions');
  });
});

describe('parseHookInput', () => {
  test('reads the SessionEnd payload Claude Code actually sends', () => {
    // Verbatim shape from a live probe (claude 2.1.252, SessionEnd hook).
    const raw = JSON.stringify({
      session_id: '37099376-c4d9-4694-9ff9-bb946d57302f',
      transcript_path: '/home/u/.claude/projects/-tmp/37099376.jsonl',
      cwd: '/home/u/Desktop/soulbrew',
      hook_event_name: 'SessionEnd',
      reason: 'other',
    });
    expect(parseHookInput(raw)).toEqual({
      sessionId: '37099376-c4d9-4694-9ff9-bb946d57302f',
      transcriptPath: '/home/u/.claude/projects/-tmp/37099376.jsonl',
      cwd: '/home/u/Desktop/soulbrew',
    });
  });

  test('garbage on stdin yields nothing instead of throwing', () => {
    expect(parseHookInput('not json')).toEqual({});
  });
});

describe('captureDecision', () => {
  test('captures a session where the human said something', () => {
    expect(captureDecision([{ kind: 'human', text: 'ทำไม graphify หยุดทำ' }]).capture).toBe(true);
  });

  test('skips a session with no human turn — automation, probes, empty starts', () => {
    const decision = captureDecision([{ kind: 'assistant', text: 'OK' }]);
    expect(decision.capture).toBe(false);
    expect(decision.reason).toBe('no-human-turn');
  });

  test('skips a session whose only human turn is too short to be worth a memory', () => {
    expect(captureDecision([{ kind: 'human', text: 'ok' }]).capture).toBe(false);
  });
});
