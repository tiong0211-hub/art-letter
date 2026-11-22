// Smoke test against a running `wrangler dev` (default http://localhost:8787).
const BASE = process.env.BASE || 'http://localhost:8787';
const ORIGIN = 'https://tiong0211-hub.github.io';
const ISSUE = process.env.ISSUE || '2026-11-19';
const hex = () => [...crypto.getRandomValues(new Uint8Array(32))].map(b => b.toString(16).padStart(2, '0')).join('');
const alice = hex(), bob = hex();
let fails = 0;
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name} ${extra}`); if (!ok) fails++; };

async function call(method, key, body, { origin = ORIGIN, issue = ISSUE } = {}) {
  const headers = { Authorization: 'Bearer ' + key };
  if (origin) headers.Origin = origin;
  if (body) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${BASE}/api/comments?issue=${issue}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  return { status: res.status, data: await res.json().catch(() => null), headers: res.headers };
}

const pre = await fetch(`${BASE}/api/comments?issue=${ISSUE}`, { method: 'OPTIONS', headers: { Origin: ORIGIN, 'Access-Control-Request-Method': 'POST' } });
check('preflight allowed', pre.status === 204 && pre.headers.get('access-control-allow-origin') === ORIGIN);
const bad = await fetch(`${BASE}/api/comments?issue=${ISSUE}`, { method: 'OPTIONS', headers: { Origin: 'https://evil.example' } });
check('preflight other origin rejected', bad.status === 403);

const a1 = crypto.randomUUID();
let r = await call('POST', alice, { id: a1, nickname: '  앨리스 ', body: '파도 앞에서\r\n\n\n\n멈췄어요', parentId: null });
check('post', r.status === 200, JSON.stringify(r.data));
r = await call('POST', alice, { id: a1, nickname: '앨리스', body: '파도 앞에서\n\n멈췄어요', parentId: null });
check('post retry is idempotent', r.status === 200);
r = await call('POST', bob, { id: a1, nickname: '밥', body: 'x', parentId: null });
check('reused id from other browser rejected', r.status === 409);

const b1 = crypto.randomUUID();
r = await call('POST', bob, { id: b1, nickname: '밥', body: '저도요', parentId: a1 });
check('reply', r.status === 200);
r = await call('POST', bob, { id: crypto.randomUUID(), nickname: '밥', body: '중첩', parentId: b1 });
check('nested reply rejected', r.status === 400);
r = await call('POST', bob, { id: crypto.randomUUID(), nickname: 'x'.repeat(25), body: 'y', parentId: null });
check('long nickname rejected', r.status === 400, r.data?.error);
r = await call('POST', bob, { id: crypto.randomUUID(), nickname: '밥', body: 'y', parentId: null }, { origin: 'https://evil.example' });
check('post from other origin rejected', r.status === 403);
r = await call('POST', 'nothex', { id: crypto.randomUUID(), nickname: '밥', body: 'y', parentId: null });
check('bad key rejected', r.status === 401);
r = await call('GET', alice, null, { issue: 'Bad Issue' });
check('bad issue rejected', r.status === 400);

r = await call('GET', alice);
const mine = r.data.comments.find(c => c.id === a1), reply = r.data.comments.find(c => c.id === b1);
check('list shape', r.status === 200 && mine && reply && mine.body === '파도 앞에서\n\n멈췄어요' && mine.nickname === '앨리스');
check('thread order', r.data.comments.indexOf(reply) === r.data.comments.indexOf(mine) + 1);
check('canDelete own only', mine.canDelete === true && reply.canDelete === false);
check('parentName', reply.parentName === '앨리스');

r = await call('DELETE', alice, { id: b1 });
check('cannot delete others', r.status === 403);
r = await call('DELETE', alice, { id: a1 });
check('delete own', r.status === 200);
r = await call('GET', bob);
const gone = r.data.comments.find(c => c.id === a1);
check('deleted parent with reply stays as placeholder', gone && gone.deleted && gone.body === null && gone.nickname === null);
r = await call('DELETE', bob, { id: b1 });
r = await call('GET', bob);
check('fully deleted thread hidden', !r.data.comments.some(c => c.id === a1 || c.id === b1));

for (let i = 0; i < 6; i++) r = await call('POST', bob, { id: crypto.randomUUID(), nickname: '밥', body: '연속 ' + i, parentId: null });
check('rate limit', r.status === 429, r.data?.error);

console.log(fails ? `${fails} FAILED` : 'ALL PASSED');
process.exit(fails ? 1 : 0);
