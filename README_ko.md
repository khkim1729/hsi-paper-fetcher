# hsi-paper-fetcher

Hyperspectral Imaging(HSI) 관련 논문 및 데이터 크롤링 도구 모음

---

## 프로젝트 구조

```
hsi-paper-fetcher/
├── crawling_ieee_2023_2025.py    # IEEE TGRS PDF 일괄 다운로드 (메인 스크립트)
├── Crawling_IEEE_year.ipynb      # IEEE 연도별 크롤링 (노트북 버전)
├── Crawling_ScienceDirect.ipynb  # ScienceDirect 크롤링
├── Crawling_wiki.py              # 위키피디아 API 크롤링
├── credentials.json              # 기관 로그인 정보 (gitignore 처리됨)
├── wiki_data.json                # 위키피디아 크롤링 결과
├── wiki_data.jsonl               # 벡터 DB용 (JSONL)
└── tiktoken/scripts/
    ├── pdf_token_counter.py
    └── json_token_counter.py
```

---

## IEEE TGRS 크롤링 (`crawling_ieee_2023_2025.py`)

### 전체 흐름

```
[1단계] 국민대 도서관 로그인
  URL  : https://lib.kookmin.ac.kr/login?returnUrl=%3F&queryParamsHandling=merge
  ID   : credentials.json → univ_id
  PW   : credentials.json → univ_pw
  버튼 : 로그인 버튼 클릭

      ↓

[2단계] IEEE 학술DB 페이지 이동 및 접속
  URL  : https://lib.kookmin.ac.kr/search/database?keyword=IEEE
  동작 : IEEE 링크 클릭 → 새 창으로 IEEE Xplore 프록시 열림
  전환 : 새 창(https://ieeexplore-ieee-org-ssl.proxy.kookmin.ac.kr)으로 자동 전환

      ↓

[3단계] IEEE Advanced Search
  - 연도(Start Year / End Year) 입력
  - 검색 실행

      ↓

[4단계] 저널 필터
  - Publication Titles → IEEE Transactions on Geoscience and Remote Sensing 선택

      ↓

[5단계] 페이지별 PDF 일괄 다운로드
  - Select All → Download → PDF 선택 → 확인
  - 다음 페이지 이동 반복
  - Seat Limit 감지 시 자동 대기 후 재시도
```

---

### 빠른 시작

**1. 의존성 설치**

```bash
pip install selenium webdriver-manager
```

**2. 로그인 정보 설정** (`credentials.json`)

```json
{
  "univ_id": "학번 또는 ID",
  "univ_pw": "비밀번호"
}
```

**3. 실행**

```bash
# GUI 모드 (브라우저 화면이 열려 진행 상황 직접 확인 가능)
python crawling_ieee_2023_2025.py --years 2023 2024 2025

# Headless 모드 (서버 환경, 화면 없이 백그라운드 실행)
python crawling_ieee_2023_2025.py --headless --years 2023 2024 2025

# 단일 연도
python crawling_ieee_2023_2025.py --year 2024

# 저장 경로 직접 지정
python crawling_ieee_2023_2025.py --year 2023 --save-path /my/papers

# 로그인 정보 직접 입력
python crawling_ieee_2023_2025.py --year 2023 --username myid --password mypw
```

### 전체 옵션

| 옵션 | 설명 |
|------|------|
| `--headless` | 브라우저를 화면 없이 실행 (서버용) |
| `--year INT` | 단일 연도 (예: `--year 2024`) |
| `--years INT...` | 복수 연도 (예: `--years 2023 2024 2025`) |
| `--save-path PATH` | PDF 저장 기본 경로 |
| `--username STR` | 도서관 로그인 ID |
| `--password STR` | 도서관 로그인 비밀번호 |

### 기본 저장 경로

| 환경 | 경로 |
|------|------|
| Linux | `/nas1/hyperspectral_literature_data_collected/01_IEEE_TGRS_1980_2025/<연도>/` |
| Windows | `C:\Users\<사용자명>\Downloads\IEEE_TGRS\<연도>\` |

---

## ScienceDirect 크롤링

**파일**: `Crawling_ScienceDirect.ipynb`

```python
TITLE = "Remote Sensing of Environment"
SET_YEAR = "2001"
START_PAGE = 1
MAX_PAGE_VISITS = 300
```

---

## 위키피디아 크롤링

```bash
python Crawling_wiki.py
```

출력: `wiki_data.json`, `wiki_data.jsonl`

---

## 토큰 수 계산

```bash
python tiktoken/scripts/pdf_token_counter.py "파일.pdf"
python tiktoken/scripts/json_token_counter.py "파일.json"
```

---

## 참고사항

- `credentials.json`은 `.gitignore`에 포함 → 절대 커밋되지 않음
- IEEE Seat Limit 발생 시 스크립트가 자동으로 5분 대기 후 재시도
- `webdriver-manager` 설치 시 ChromeDriver 버전 자동 관리
