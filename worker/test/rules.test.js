// The Worker's alert rules must match radar/alerts.py. tests/test_pipeline.py
// writes fixtures/alerts_cases.json from the Python side; this replays them.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { evaluate, pnl } from '../src/index.js';

const cases = JSON.parse(readFileSync(new URL('./alerts_cases.json', import.meta.url)));
for (const c of cases) {
  test(c.name, () => {
    const got = evaluate(c.issue, c.positions, c.today).map(a => [a.kind, a.key, a.text]);
    assert.deepEqual(got, c.expected);
    const p = pnl(c.issue, c.positions);
    assert.deepEqual(p && { positions: p.positions, pnl: Math.round(p.pnl * 100) / 100 }, c.pnl);
  });
}
