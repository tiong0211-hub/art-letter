# ART LETTER 정시 실행기 (Cloudflare Cron)

GitHub Actions 의 예약 실행(cron)은 몇 시간씩 늦거나 빠집니다. 이 Worker 는 정해진 시각에
`tiong0211-hub/art-newsletter` 의 `publication.yml` 을 **workflow_dispatch 로 즉시 실행**시킵니다.
컨트롤러가 실제 한국 시각을 다시 확인하고 같은 일을 두 번 하지 않으므로, 추가로 실행돼도 안전합니다.

| 한국 시간 | 하는 일 |
|---|---|
| 월·수 12:15–19:15 매시 | Gemini 검증 |
| 월·수 20:00, 20:15, 20:30 | 선정·동결·웹 게시 |
| 화·목 08:00–09:45 15분마다 | 텔레그램 발송·재시도 |
| 화·목 10:00–10:45 15분마다 | 회차 종료 처리 |

## 처음 배포 (한 번만)

1. GitHub 토큰 만들기: Settings → Developer settings → Fine-grained tokens → Generate new token
   - Repository access: **Only select repositories → `art-newsletter`**
   - Repository permissions → **Actions: Read and write** (다른 권한은 필요 없음)
2. 배포:

```bash
cd scheduler-worker
npm install
npx wrangler secret put GITHUB_TOKEN
npm run deploy
```

`secret put` 에서 Worker 를 새로 만들지 물으면 `Y` 입니다.

## 확인

- Cloudflare 대시보드 → Workers & Pages → `art-letter-scheduler` → **Logs**: 실행마다 `"ok":true,"status":204` 가 찍힙니다.
- GitHub → art-newsletter → Actions: 정각 직후 `workflow_dispatch` 실행이 생깁니다.
- `"status":401` 또는 `403` 이면 토큰 만료·권한 문제입니다. 토큰을 새로 만들어 `secret put` 을 다시 하면 됩니다.

## 테스트

```bash
npm test
```
