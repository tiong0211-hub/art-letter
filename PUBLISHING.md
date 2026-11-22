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
