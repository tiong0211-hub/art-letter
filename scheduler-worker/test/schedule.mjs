// Offline tests: dispatch behaviour against a fake GitHub, and the cron table
// expanded over one week in KST.
import { readFileSync } from 'node:fs';
import { dispatch } from '../src/index.js';

let fails = 0;
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name} ${extra}`); if (!ok) fails++; };
const env = { GITHUB_REPOSITORY: 'o/r', WORKFLOW: 'publication.yml', GITHUB_TOKEN: 't' };
const fake = statuses => { const calls = []; return { calls, f: async (url, init) => { calls.push({ url, init }); const s = statuses.shift(); if (s instanceof Error) throw s; return new Response(s === 204 ? null : 'x', { status: s }); } }; };

let g = fake([204]); let r = await dispatch(env, g.f);
check('204 ok', r.ok && g.calls.length === 1);
check('request', g.calls[0].url === 'https://api.github.com/repos/o/r/actions/workflows/publication.yml/dispatches'
  && JSON.parse(g.calls[0].init.body).inputs.mode === 'tick' && JSON.parse(g.calls[0].init.body).ref === 'main'
  && g.calls[0].init.headers.Authorization === 'Bearer t');
g = fake([401]); r = await dispatch(env, g.f);
check('401 not retried', !r.ok && r.status === 401 && g.calls.length === 1);
g = fake([502, new Error('net'), 204]); r = await dispatch(env, g.f);
check('5xx/network retried', r.ok && g.calls.length === 3, JSON.stringify(r));

// --- cron table ---------------------------------------------------------
const toml = readFileSync(new URL('../wrangler.toml', import.meta.url), 'utf8');
const crons = [...toml.matchAll(/^\s*"([^"]+)",?\s*(#.*)?$/gm)].map(m => m[1]).filter(c => c.split(' ').length === 5);
const DOW = { SUN: 0, MON: 1, TUE: 2, WED: 3, THU: 4, FRI: 5, SAT: 6 };
const field = (spec, lo, hi, names) => {
  const out = new Set();
  for (const part of spec.split(',')) {
    let [range, step] = part.split('/'); step = +(step || 1);
    let [a, b] = range === '*' ? [lo, hi] : range.split('-').map(x => names && x in names ? names[x] : +x);
    if (b === undefined) b = range === '*' ? hi : a;
    for (let v = a; v <= b; v += step) out.add(v);
  }
  return out;
};
const fires = new Set();
for (const c of crons) {
  const [m, h, , , d] = c.split(' ');
  const M = field(m, 0, 59), H = field(h, 0, 23), D = field(d, 0, 6, DOW);
  for (const dd of D) for (const hh of H) for (const mm of M) {
    const k = (dd * 1440 + hh * 60 + mm + 9 * 60) % (7 * 1440); // UTC -> KST minute of week
    fires.add(k);
  }
}
const fmt = k => `${['일','월','화','수','목','금','토'][Math.floor(k / 1440)]} ${String(Math.floor(k % 1440 / 60)).padStart(2,'0')}:${String(k % 60).padStart(2,'0')}`;
const want = [];
for (const d of [1, 3]) { for (let h = 12; h <= 19; h++) want.push(d * 1440 + h * 60 + 15); for (const m of [0, 15, 30]) want.push(d * 1440 + 20 * 60 + m); }
for (const d of [2, 4]) for (let t = 8 * 60; t <= 10 * 60 + 15; t += 15) want.push(d * 1440 + t);
const got = [...fires].sort((a, b) => a - b);
const missing = want.filter(k => !fires.has(k));
const extra = got.filter(k => !want.includes(k));
check('every old GitHub slot is covered', missing.length === 0, missing.map(fmt).join(', '));
check('extra slots are only harmless late Tue/Thu ticks', extra.every(k => [2, 4].includes(Math.floor(k / 1440)) && k % 1440 > 10 * 60 + 15 && k % 1440 <= 10 * 60 + 45), extra.map(fmt).join(', '));
console.log('KST fires:', got.map(fmt).join(' | '));
console.log(fails ? `${fails} FAILED` : 'ALL PASSED');
process.exit(fails ? 1 : 0);
