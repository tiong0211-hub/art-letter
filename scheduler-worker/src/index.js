// ART LETTER scheduler: on each Cloudflare cron, ask GitHub to run the
// publication controller now (workflow_dispatch runs immediately, unlike
// GitHub's own cron). The controller re-checks the real KST time and is
// idempotent, so an extra or late run is harmless.

export async function dispatch(env, fetchImpl = fetch) {
  const url = `https://api.github.com/repos/${env.GITHUB_REPOSITORY}/actions/workflows/${env.WORKFLOW}/dispatches`;
  const init = {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'art-letter-scheduler',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ref: 'main', inputs: { mode: 'tick' } }),
  };
  let last;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const res = await fetchImpl(url, init);
      if (res.status === 204) return { ok: true, status: 204, attempt };
      last = { ok: false, status: res.status, attempt, body: (await res.text()).slice(0, 300) };
      // 4xx (bad token, missing permission, wrong workflow) will not fix itself.
      if (res.status < 500 && res.status !== 429) break;
    } catch (error) {
      last = { ok: false, status: 0, attempt, body: String(error).slice(0, 300) };
    }
    await new Promise(r => setTimeout(r, 2000 * attempt));
  }
  return last;
}

export default {
  async scheduled(event, env, ctx) {
    if (!env.GITHUB_TOKEN) {
      console.error(JSON.stringify({ cron: event.cron, ok: false, error: 'GITHUB_TOKEN secret is not set' }));
      return;
    }
    const result = await dispatch(env);
    const line = JSON.stringify({ cron: event.cron, at: new Date(event.scheduledTime).toISOString(), ...result });
    result.ok ? console.log(line) : console.error(line);
  },
  async fetch() {
    return new Response('ART LETTER scheduler (cron only)\n', { status: 404 });
  },
};
