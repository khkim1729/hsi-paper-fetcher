# Wikipedia 연관 키워드 꼬리물기 크롤러

초기 핵심 키워드(HSI, 원격탐사 등)를 바탕으로 위키백과의 **연관 검색어(OpenSearch API)**를 자동으로 탐색하고, 파도타기(꼬리물기) 방식으로 관련 학술/개념 문서를 대량으로 수집하는 도구입니다.

---

## 📂 파일 구성

```text
crawler_wiki/
├── README_WIKI.md             # 본 설명서 파일
├── wiki_v1/                   # 버전 1: 지정된 키워드 리스트만 1:1로 수집하는 기본 스크립트
└── wiki_v2/                   # 버전 2: 꼬리물기 심화 크롤러 (현재 메인)
    ├── Crawling_wiki_v2.py    # 메인 크롤러 (연관 검색어 자동 확장 및 우선순위 탐색)
    ├── wiki_data.jsonl        # 수집된 위키백과 본문 데이터셋 (JSON Lines 형식)
    └── wiki_texts/            # 실시간 진행 상황 로깅 폴더
        └── wiki_keywords.txt  # 크롤링이 완료된 키워드 목록이 실시간으로 추가되는 파일
```

---

## ⚙️ 크롤러 흐름 (꼬리물기 로직)

본 크롤러는 단순 반복(for-loop)이 아닌 **대기열(Queue)**과 **새치기(Insert at 0)** 방식을 사용하여 연관성이 높은 문서들을 깊이 있게 탐색합니다.

```
[Step 1] 초기 대기열 설정
  - initial_words 리스트에 명시된 키워드(예: 'hyperspectral')를 Queue에 넣음

       ↓

[Step 2] 문서 데이터 수집 (Wikipedia API)
  - Queue의 맨 앞 단어를 꺼내어 위키백과 문서 존재 여부 확인
  - 문서가 존재하면 제목, 요약, 본문(최대 1만자), URL 등을 `wiki_data.jsonl`에 한 줄씩 즉시 저장
  - `wiki_texts/wiki_keywords.txt`에 완료된 단어 기록 (실시간 확인용)

       ↓

[Step 3] 연관 검색어 탐색 (OpenSearch API)
  - 방금 검색한 단어를 위키백과 검색창에 쳤을 때 나오는 연관/자동완성 단어 최대 N개 추출
  - 봇 차단 방지를 위해 User-Agent 헤더 적용

       ↓

[Step 4] 대기열 새치기 및 중복 제거
  - 이미 수집했거나 방문 기록(visited set)에 있는 단어는 스킵 (무한 루프 방지)
  - 새롭게 발견된 연관 단어들을 Queue의 **맨 앞(0번 인덱스)**에 삽입
  - 곧바로 가장 깊은 연관 단어부터 다음 [Step 2] 반복 진행
```

---

## 🚀 빠른 시작

### 1. 의존성 설치
스크립트 실행을 위해 위키백과 API 전용 라이브러리와 HTTP 요청 라이브러리가 필요합니다.
```bash
pip install wikipedia-api requests
```

### 2. 크롤러 실행
`wiki_v2` 폴더로 이동하여 파이썬 스크립트를 실행합니다.
```bash
cd wiki_v2
python Crawling_wiki_v2.py
```

### 3. 실시간 진행 상황 모니터링
크롤러가 도는 동안 다른 터미널 창을 열고 아래 명령어를 입력하면, 실시간으로 어떤 단어들이 수집되고 있는지 모니터링할 수 있습니다.
```bash
# 실시간으로 추가되는 키워드 로그 확인
tail -f wiki_texts/wiki_keywords.txt
```

---

## 💾 수집되는 데이터 내역

크롤링이 진행되면 `wiki_data.jsonl` 파일에 다음과 같은 구조의 JSON 데이터가 한 줄(Line)에 하나씩 누적 저장됩니다. 프로그램이 중간에 중단되어도 그때까지 수집된 데이터는 안전하게 보존됩니다.

* `id`: 문서 고유 ID (예: wiki_hyperspectral)
* `query_word`: 검색에 사용된 쿼리 키워드
* `title`: 실제 위키백과 문서 제목
* `summary`: 문서 최상단 요약본 (각주 번호 등 노이즈 제거됨)
* `text`: 문서 전체 본문 (최대 10,000자로 제한됨)
* `canonical_url`: 위키백과 웹페이지 원본 주소
* `source`: 'wikipedia'
* `collected_at`: 수집된 시간 (ISO 포맷 타임스탬프)

---

## 🛠 주요 설정 (스크립트 내부 변수)

`Crawling_wiki_v2.py` 스크립트 상단에서 다음 변수들을 수정하여 크롤링 규모를 조절할 수 있습니다.

| 변수명 | 기본값 | 설명 |
|---|---|---|
| `initial_words` | `['hyperspectral', ...]` | 꼬리물기를 시작할 최초의 '씨앗(Seed)' 키워드 리스트 |
| `MAX_PAGES` | `1000` | 수집할 최대 문서 개수. 너무 많으면 IP가 차단될 수 있으므로 안전망 역할 |
| `SUGGESTION_LIMIT` | `10` | 한 단어당 탐색할 연관 검색어(Sub-keyword)의 개수 |
| `txt_save_dir` | `'wiki_texts'` | 실시간 로그 파일이 저장될 디렉토리 이름 |

---

## ⚠️ 주의사항

1. **위키백과 API 정책:**
   위키백과 API는 짧은 시간에 과도한 요청(예: 초당 수십 건)을 보내거나, `User-Agent`가 불분명할 경우 해당 IP를 영구 차단(403 Error)할 수 있습니다. v2 코드에는 정상적인 브라우저로 위장하는 `User-Agent`가 적용되어 있으나, `MAX_PAGES`를 너무 크게(1만 개 이상) 잡을 때는 주의가 필요합니다.
2. **대소문자 처리:**
   스크립트는 무한 루프를 방지하기 위해 내부적으로 대소문자를 무시(`lower()`)하여 중복을 필터링합니다. (예: `Hyperspectral`과 `hyperspectral`은 같은 문서로 취급하여 중복 다운로드하지 않음)

