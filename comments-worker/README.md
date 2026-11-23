# ART LETTER 댓글 서버

Cloudflare Workers + D1으로 운영하는 댓글 API입니다. `index.html`의 댓글 코드가 쓰는
계약을 그대로 구현하므로, 사이트에서는 API 주소 한 줄만 바꾸면 됩니다.

- 닉네임과 감상만으로 로그인 없이 작성합니다. 답글은 한 단계까지 달 수 있습니다.
- 브라우저마다 생성되는 무작위 키를 쓰고, 서버에는 그 키의 SHA-256만 저장합니다.
  "내 댓글 삭제"를 할 때 이 키로 작성자를 확인합니다.
- IP는 소금값을 섞은 해시로만 저장하고, 속도 제한에만 씁니다(10분 5개, 하루 30개).
- 발행된 레터(`publication.json`의 `issues`)에만 댓글을 받습니다.
- 관리자는 `ADMIN_TOKEN`으로 어떤 댓글이든 삭제할 수 있습니다.

## 처음 배포 (한 번만)

```bash
cd comments-worker
npm install
npx wrangler login
npx wrangler d1 create art-letter-comments   # 출력된 database_id를 wrangler.toml에 붙여넣기
npm run db:init
npx wrangler secret put ADMIN_TOKEN          # 긴 임의 문자열 (예: openssl rand -hex 32)
npx wrangler secret put IP_SALT              # 긴 임의 문자열
npm run deploy                               # https://art-letter-comments.artletter-kr.workers.dev 출력
```

배포 후 저장소 루트에서 사이트를 새 주소로 바꿉니다.

```bash
python3 tools/publish.py set-comments-api https://art-letter-comments.artletter-kr.workers.dev/api/comments
python3 tools/publish.py verify
```

## 기존 댓글 옮기기

예전 서버가 살아 있는 동안 내 컴퓨터에서 실행합니다.

```bash
python3 export_old_comments.py > import.sql
npx wrangler d1 execute art-letter-comments --remote --file import.sql
```

옮긴 댓글은 원래 작성자의 삭제 키를 가져올 수 없어서, 관리자만 삭제할 수 있습니다.

## 관리자 삭제

```bash
curl -X DELETE -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"id":"<댓글 id>"}' "https://art-letter-comments.artletter-kr.workers.dev/api/comments?issue=<레터 id>"
```

## 로컬 테스트

```bash
npm run db:init:local
npx wrangler dev --local --var PUBLICATION_URL: --var ADMIN_TOKEN:testadmin
npm test     # 다른 터미널에서
```

## API

| 메서드 | 본문 | 응답 |
|---|---|---|
| `GET ?issue=ID` | — | `{comments:[{id,parentId,parentName,nickname,body,createdAt,deleted,canDelete}]}` (스레드 순) |
| `POST ?issue=ID` | `{id(uuid), nickname(≤24), body(≤1500), parentId}` | `{ok,id}` — 같은 id로 다시 보내도 한 번만 저장 |
| `DELETE ?issue=ID` | `{id}` | `{ok}` — 내용을 지우고 자리 표시만 남김 |

모든 요청에 `Authorization: Bearer <64자리 hex>`를 붙입니다. 오류 응답은 `{error:"한국어 메시지"}` 형식입니다.
