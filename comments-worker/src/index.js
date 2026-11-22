// ART LETTER comments API — Cloudflare Worker + D1.
// Implements the contract used by index.html:
//   GET    /api/comments?issue=ID                        -> {comments:[...]}
//   POST   /api/comments?issue=ID  {id,nickname,body,parentId}
//   DELETE /api/comments?issue=ID  {id}
// Every request carries "Authorization: Bearer <64 hex>", a random key kept in
// the reader's browser. Only its SHA-256 is stored; it proves "my comment".

const NICK_MAX = 24;
const BODY_MAX = 1500;
const RATE = [{ minutes: 10, max: 5 }, { minutes: 24 * 60, max: 30 }];
const ISSUE_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const KEY_RE = /^[a-f0-9]{64}$/;

class HttpError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin');
    const allowed = (env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean);
    const originOk = origin !== null && allowed.includes(origin);
    const cors = originOk ? {
      'Access-Control-Allow-Origin': origin,
      'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type',
      'Access-Control-Max-Age': '86400',
      'Vary': 'Origin',
    } : { 'Vary': 'Origin' };

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: originOk ? 204 : 403, headers: cors });
    }
    try {
      const url = new URL(request.url);
      if (url.pathname !== '/api/comments') throw new HttpError(404, '찾을 수 없는 주소입니다.');
      const key = bearer(request);
      const admin = !!env.ADMIN_TOKEN && key === env.ADMIN_TOKEN;
      // Browsers from other sites may not write; scripts without Origin need the admin token.
      if (request.method !== 'GET' && !originOk && !admin) throw new HttpError(403, '허용되지 않은 사이트입니다.');
      if (!admin && !KEY_RE.test(key || '')) throw new HttpError(401, '브라우저 식별 키가 올바르지 않습니다.');
      const ownerHash = admin ? null : await sha256(key);
      const issue = url.searchParams.get('issue') || '';
      await checkIssue(issue, env);

      let result;
      if (request.method === 'GET') result = await list(env.DB, issue, ownerHash, admin);
      else if (request.method === 'POST') result = await create(env, request, issue, ownerHash, await readJson(request));
      else if (request.method === 'DELETE') result = await remove(env.DB, issue, ownerHash, admin, await readJson(request));
      else throw new HttpError(405, '지원하지 않는 요청입니다.');
      return json(result, 200, cors);
    } catch (error) {
      const status = error instanceof HttpError ? error.status : 500;
      if (status === 500) console.error(error);
      return json({ error: status === 500 ? '댓글 서버에 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.' : error.message }, status, cors);
    }
  },
};

function json(data, status, headers) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...headers, 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}

function bearer(request) {
  const m = /^Bearer (.+)$/.exec(request.headers.get('Authorization') || '');
  return m ? m[1].trim() : null;
}

async function sha256(text) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}

async function readJson(request) {
  if (Number(request.headers.get('Content-Length') || 0) > 16384) throw new HttpError(413, '내용이 너무 깁니다.');
  try { return await request.json(); } catch { throw new HttpError(400, '요청 형식이 올바르지 않습니다.'); }
}

let publication = { at: 0, ids: null };
async function checkIssue(issue, env) {
  if (!ISSUE_RE.test(issue)) throw new HttpError(400, '레터를 찾을 수 없습니다.');
  if (!env.PUBLICATION_URL) return;
  if (!publication.ids || Date.now() - publication.at > 5 * 60 * 1000) {
    try {
      const res = await fetch(env.PUBLICATION_URL, { cf: { cacheTtl: 300 } });
      if (res.ok) publication = { at: Date.now(), ids: new Set(Object.keys((await res.json()).issues || {})) };
    } catch (e) { console.error('publication fetch failed', e); }
  }
  // If the manifest could never be loaded, fall back to the format check only.
  if (publication.ids && !publication.ids.has(issue)) throw new HttpError(404, '레터를 찾을 수 없습니다.');
}

function clean(text, max, label) {
  const value = String(text ?? '')
    .replace(/\r\n?/g, '\n')
    .replace(/[\u0000-\u0009\u000B-\u001F\u007F​-‏‪-‮⁦-⁩]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  if (!value) throw new HttpError(400, `${label}을(를) 입력해 주세요.`);
  if ([...value].length > max) throw new HttpError(400, `${label}은(는) ${max}자 이내로 써 주세요.`);
  return value;
}

async function list(db, issue, ownerHash, admin) {
  const { results } = await db.prepare(
    'SELECT id, parent_id, nickname, body, owner_hash, created_at, deleted_at FROM comments WHERE issue = ? ORDER BY created_at, id'
  ).bind(issue).all();
  const byId = new Map(results.map(r => [r.id, r]));
  const replies = new Map();
  for (const r of results) if (r.parent_id) {
    if (!replies.has(r.parent_id)) replies.set(r.parent_id, []);
    replies.get(r.parent_id).push(r);
  }
  const view = r => {
    const parent = r.parent_id ? byId.get(r.parent_id) : null;
    const deleted = !!r.deleted_at;
    return {
      id: r.id,
      parentId: r.parent_id,
      parentName: parent && !parent.deleted_at ? parent.nickname : null,
      nickname: deleted ? null : r.nickname,
      body: deleted ? null : r.body,
      createdAt: r.created_at,
      deleted,
      canDelete: !deleted && (admin || (!!ownerHash && r.owner_hash === ownerHash)),
    };
  };
  const out = [];
  for (const r of results) {
    if (r.parent_id) continue;
    const kids = (replies.get(r.id) || []).filter(k => !k.deleted_at);
    if (r.deleted_at && kids.length === 0) continue; // nothing left to show in this thread
    out.push(view(r), ...kids.map(view));
  }
  return { comments: out };
}

async function create(env, request, issue, ownerHash, input) {
  const db = env.DB;
  const id = String(input.id || '').toLowerCase();
  if (!UUID_RE.test(id)) throw new HttpError(400, '요청 형식이 올바르지 않습니다.');
  const nickname = clean(input.nickname, NICK_MAX, '닉네임');
  const body = clean(input.body, BODY_MAX, '감상');
  const parentId = input.parentId ? String(input.parentId) : null;

  const existing = await db.prepare('SELECT owner_hash, issue FROM comments WHERE id = ?').bind(id).first();
  if (existing) {
    // Same browser retrying the same submission: treat as success (idempotent).
    if (existing.owner_hash === ownerHash && existing.issue === issue) return { ok: true, id };
    throw new HttpError(409, '이미 사용된 요청입니다. 다시 시도해 주세요.');
  }
  if (parentId) {
    const parent = await db.prepare('SELECT parent_id, deleted_at FROM comments WHERE id = ? AND issue = ?').bind(parentId, issue).first();
    if (!parent || parent.deleted_at) throw new HttpError(400, '답글을 달 댓글을 찾을 수 없습니다.');
    if (parent.parent_id) throw new HttpError(400, '답글에는 다시 답글을 달 수 없습니다.');
  }

  const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
  const ipHash = await sha256((env.IP_SALT || '') + '|' + ip);
  const now = Date.now();
  for (const { minutes, max } of RATE) {
    const since = new Date(now - minutes * 60000).toISOString();
    const row = await db.prepare('SELECT COUNT(*) AS n FROM comments WHERE ip_hash = ? AND created_at > ?').bind(ipHash, since).first();
    if (row.n >= max) throw new HttpError(429, '잠시 쉬었다가 다시 남겨 주세요.');
  }

  await db.prepare(
    'INSERT INTO comments (id, issue, parent_id, nickname, body, owner_hash, ip_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
  ).bind(id, issue, parentId, nickname, body, ownerHash, ipHash, new Date(now).toISOString()).run();
  return { ok: true, id };
}

async function remove(db, issue, ownerHash, admin, input) {
  const id = String(input.id || '');
  const row = await db.prepare('SELECT owner_hash, deleted_at FROM comments WHERE id = ? AND issue = ?').bind(id, issue).first();
  if (!row) throw new HttpError(404, '댓글을 찾을 수 없습니다.');
  if (!admin && (!ownerHash || row.owner_hash !== ownerHash)) throw new HttpError(403, '작성한 브라우저에서만 삭제할 수 있어요.');
  if (!row.deleted_at) {
    await db.prepare('UPDATE comments SET deleted_at = ? WHERE id = ?').bind(new Date().toISOString(), id).run();
  }
  return { ok: true };
}
