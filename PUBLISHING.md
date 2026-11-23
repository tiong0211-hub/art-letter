# ART LETTER 발행 규칙

이 문서와 `tools/publish.py`가 발행 규칙입니다. 사람이 하든 어떤 LLM이 하든,
이 규칙을 따르면 같은 결과가 나옵니다. 필요한 것은 Python 3 하나입니다(외부 패키지 없음).

## 구조

- `index.html` — 매거진 전체. 레터 데이터는 `window.ARTLETTER_DATA.letters`,
  이미지는 `const images={...}` 블록에 base64 data URI로 들어 있습니다.
- `publication.json` — 발행 매니페스트(`hash_spec: artletter-issue-v2`, `version: 2`).
  - `html_sha256`: `index.html` 파일 바이트의 SHA-256
  - `issues`: 레터 ID → 레터 해시

## 레터 해시 (artletter-issue-v2)

1. 레터 객체에서 `order`, `featured`를 제거합니다(새 레터가 추가될 때 바뀌는 위치 정보라서).
2. `image`, `artwork.image`, `artworks[].image`를 모두 `"sha256:<이미지 원본 바이트의 SHA-256>"`으로 바꿉니다.
3. 키 정렬, 공백 없음(`,` `:`), 유니코드 이스케이프 없음으로 JSON 직렬화 후 UTF-8 인코딩합니다.
4. 그 바이트의 SHA-256(소문자 hex)이 레터 해시입니다.

Python으로는 `json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")`.

## 새 레터 발행

1. 레터 JSON 작성 (`order`, `featured`, `image`, `artworks`는 스크립트가 채움):

   ```json
   {
     "id": "2026-11-22",
     "title": "…", "question": "…", "category": "…",
     "body": "문단\n\n문단\n", "summary": "…", "reflection": "…",
     "date": "2026-11-22",
     "artwork": {
       "title": "…", "artist": "…", "date": "…",
       "institution": "The Metropolitan Museum of Art",
       "sourceUrl": "https://www.metmuseum.org/art/collection/search/<id>",
       "apiUrl": "https://collectionapi.metmuseum.org/public/collection/v1/objects/<id>",
       "image": "assets/met-<id>.jpg",
       "originalImage": "https://images.metmuseum.org/…",
       "publicDomain": true,
       "credit": "…",
       "retrievedOn": "YYYY-MM-DD"
     }
   }
   ```

2. 실행:

   ```bash
   python3 tools/publish.py add letter.json met-<id>.jpg
   python3 tools/publish.py verify
   ```

   `add`는 레터를 날짜 최신순 맨 앞에 넣고, `order`를 1..n으로, `featured`를 최신 레터로
   맞추고, 이미지를 넣고, `editionLabel`과 `publication.json`을 갱신합니다.

3. 커밋 후 push. GitHub Actions가 `verify`를 다시 실행합니다.

## 정기 발행 절차 (매주 화·목 오전 7시 KST, 자동)

예약 작업이 이 절차를 그대로 따릅니다. 사람이 수동으로 발행할 때도 같습니다.

1. **준비**: `main`을 최신으로 받고, 오늘 날짜를 한국 시간으로 정합니다(`TZ=Asia/Seoul date +%F`).
   그 날짜를 `id`로 쓰는 레터가 이미 있으면 아무것도 하지 않고 끝냅니다.
2. **돌아보기**: 최근 레터 5편의 주제·카테고리·작가·질문을 읽고, 겹치지 않는 방향을 정합니다.
   같은 작가는 최근 5편 안에 다시 쓰지 않고, 카테고리는 직전 호와 다르게 합니다.
3. **작품 고르기**: 계절과 요즘의 하루에 어울리는 주제어로 후보를 찾습니다.
   ```bash
   python3 tools/met.py search "<영문 주제어>" 15
   ```
   회화·판화·드로잉 중 한 점을 골라 받습니다. 실패하면(공공 도메인 이미지 없음) 다음 후보로 넘어갑니다.
   ```bash
   python3 tools/met.py fetch <objectID> /tmp/issue
   ```
   `/tmp/issue/artwork.json`(그대로 사용), `facts.json`(사실 확인용), 이미지 파일이 생깁니다.
4. **원고 쓰기**: `/tmp/issue/letter.json`을 작성합니다. `artwork`에는 `artwork.json` 내용을 그대로 넣습니다.
   - `category`: 자연과 우주 · 철학과 인간 · 일상과 감정 · 시간과 기억 · 관계와 사회 중 하나
   - `title`: 질문이나 쉼표가 있는 짧은 한 문장 (예: "평범한 하루에도, 빛은 머물까요?")
   - `question` = `reflection`: 레터의 중심 질문 한 문장
   - `body`: 5문단, 문단 사이 빈 줄, 끝에 줄바꿈. ① 일상의 장면 ② 작가·작품 제목(한국어 《》, 필요하면 원제 병기)·연도·소장처 — `facts.json`에 있는 사실만 ③ 작품을 매개로 한 사유와 질문 ④ 오늘 해 볼 수 있는 작은 실천 ⑤ 독자에게 건네는 질문
   - `summary`: 본문 첫 문단 그대로
   - 존댓말, 차분한 문체. 그림에 무엇이 그려져 있는지 직접 보지 못했다면 묘사하지 말고 제목·기록에 기대어 씁니다. 해석·일화·전기적 사실을 지어내지 않습니다.
5. **발행**:
   ```bash
   python3 tools/publish.py add /tmp/issue/letter.json /tmp/issue/met-<objectID>.jpg
   python3 tools/publish.py verify
   ```
   `main`에 커밋(`Publish ART LETTER <날짜>`)하고 push합니다. GitHub Pages 반영과 텔레그램 알림은 자동입니다.
6. **실패 시**: 원인을 남기고 아무것도 push하지 않습니다. 반쯤 된 발행을 올리지 않습니다.

## 텔레그램 알림

`publication.json`이 `main`에 push되면 `.github/workflows/telegram.yml`이 새로 추가된 레터를
텔레그램으로 보냅니다. 저장소 Settings → Secrets and variables → Actions에 두 값을 등록해야 합니다.

- `TELEGRAM_BOT_TOKEN`: BotFather가 준 봇 토큰
- `TELEGRAM_CHAT_ID`: 받을 채팅/채널 ID (채널이면 `@채널이름`도 가능, 봇이 관리자여야 함)

미리보기: `python3 tools/notify_telegram.py <기준 커밋> --dry-run`

## 검사 항목 (`verify`)

- 매니페스트 해시가 현재 `index.html`과 일치
- 필수 필드 존재, 날짜 형식 `YYYY-MM-DD`, 작품은 `publicDomain: true`
- 최신순 정렬, `order` = 1..n, 첫 레터만 `featured`
- 참조된 이미지가 모두 들어 있고, 쓰이지 않는 이미지가 없음

`index.html`을 손으로 고친 경우에는 검토 후 `python3 tools/publish.py rehash`로 매니페스트를 다시 만듭니다.

## 원고 원칙

- 작품 정보는 소장처 기록(제목·작가·연도·소장처·크레딧) 범위 안에서만 씁니다. 해석을 사실처럼 지어내지 않습니다.
- 일상의 장면 → 작품 소개 → 사유 → 작은 실천 제안 → 질문으로 맺는 흐름.

## 댓글 서버

`comments-worker/` (Cloudflare Workers + D1). 배포·이전·관리 방법은 `comments-worker/README.md`.
사이트가 바라보는 댓글 API 주소는 `python3 tools/publish.py set-comments-api <URL>`로 바꿉니다.
