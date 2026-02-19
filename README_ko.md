# hsi-paper-fetcher

Hyperspectral Imaging(HSI) 관련 논문 및 데이터 크롤링 도구 모음

---

## 프로젝트 구조

```
hsi-paper-fetcher/
├── crawling_ieee_2023_2025.py    # IEEE TGRS PDF 일괄 다운로드 (Linux & Windows)
├── Crawling_IEEE_year.ipynb      # IEEE 연도별 크롤링 (노트북)
├── Crawling_ScienceDirect.ipynb  # ScienceDirect 크롤링
├── Crawling_wiki.py              # 위키피디아 API 크롤링
├── credentials.json              # 기관 로그인 정보 (gitignore 처리)
├── wiki_data.json                # 위키피디아 크롤링 결과
├── wiki_data.jsonl               # 벡터 데이터베이스용 (JSONL)
└── tiktoken/
    └── scripts/
        ├── pdf_token_counter.py
        └── json_token_counter.py
```

---

## IEEE TGRS 크롤링 스크립트

**파일**: `crawling_ieee_2023_2025.py`

국민대학교 도서관 프록시를 통해 IEEE Xplore(TGRS 저널)에서 PDF 논문을 일괄 다운로드합니다.

### 실행 모드

| 모드 | 설명 |
|------|------|
| `linux` | **Headless** – 원격 서버용. Chrome이 백그라운드에서 실행됩니다. |
| `windows` | **GUI** – Windows 로컬 PC용. 브라우저 창이 열려 있어 각 단계를 눈으로 직접 확인하고 문제가 생겼을 때 즉시 파악할 수 있습니다. |

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
# Linux 서버 (Headless)
python crawling_ieee_2023_2025.py --mode linux --years 2023 2024 2025

# Windows 로컬 PC (브라우저 화면 표시)
python crawling_ieee_2023_2025.py --mode windows --years 2023 2024 2025

# 단일 연도만 크롤링
python crawling_ieee_2023_2025.py --mode linux --year 2024

# 저장 경로 직접 지정
python crawling_ieee_2023_2025.py --mode windows --year 2023 --save-path D:\MyPapers

# 로그인 정보 직접 입력 (credentials.json 불필요)
python crawling_ieee_2023_2025.py --mode windows --year 2023 --username myid --password mypw
```

### 전체 옵션

```
--mode {linux,windows}    실행 모드 (미지정 시 OS 자동 감지)
--year  INT               단일 연도 (예: 2024)
--years INT [INT ...]     복수 연도 (예: --years 2023 2024 2025)
--save-path PATH          PDF 저장 기본 경로
--username STR            도서관 로그인 ID
--password STR            도서관 로그인 비밀번호
```

### 기본 저장 경로

| 모드    | 기본 경로 |
|---------|----------|
| linux   | `/nas1/hyperspectral_literature_data_collected/01_IEEE_TGRS_1980_2025` |
| windows | `C:\Users\<USERNAME>\Downloads\IEEE_TGRS` |

다운로드된 PDF는 `<기본경로>/<연도>/` 하위에 저장됩니다.

### Windows 사용 시 참고사항

- 브라우저 창이 자동으로 열립니다. 스크립트가 어느 단계에 있는지 직접 확인 가능합니다.
- 로그인이나 페이지 이동에서 막히는 경우, 브라우저를 보며 원인을 바로 파악할 수 있습니다.
- `webdriver-manager`가 설치되어 있으면 ChromeDriver를 자동으로 설치/관리합니다.
- Chrome 브라우저가 사전에 설치되어 있어야 합니다.

---

## ScienceDirect 크롤링

**파일**: `Crawling_ScienceDirect.ipynb`

Elsevier ScienceDirect에서 논문 PDF를 다운로드합니다.

**설정**:
```python
TITLE = "Remote Sensing of Environment"  # 저널명
SET_YEAR = "2001"                        # 크롤링 연도
START_PAGE = 1
MAX_PAGE_VISITS = 300
```

---

## 위키피디아 크롤링

**파일**: `Crawling_wiki.py`

Wikipedia API를 통해 HSI 관련 용어 문서를 수집합니다.

```bash
python Crawling_wiki.py
```

**출력**:
- `wiki_data.json`: 전체 데이터 (메타데이터 포함)
- `wiki_data.jsonl`: 한 줄에 한 문서 (벡터 DB용)

---

## 토큰 수 계산 도구

```bash
# PDF 토큰 계산
python tiktoken/scripts/pdf_token_counter.py "파일.pdf"
python tiktoken/scripts/pdf_token_counter.py "경로/폴더"

# JSON/JSONL 토큰 계산
python tiktoken/scripts/json_token_counter.py "파일.json"
python tiktoken/scripts/json_token_counter.py "파일.json" --field "documents[].text"
```

---

## 의존성 패키지

```bash
# 크롤링
pip install selenium webdriver-manager
pip install pandas openpyxl tqdm

# 위키피디아
pip install wikipedia-api

# 토큰 계산
pip install tiktoken pymupdf4llm pymupdf
```

---

## 참고사항

- 크롤링은 국민대학교 도서관 프록시(`proxy.kookmin.ac.kr`)를 통해 접속합니다.
- 대량 다운로드 시 IEEE Seat Limit이 발생할 수 있으며, 스크립트가 자동으로 대기 후 재시도합니다.
- `credentials.json`은 `.gitignore`에 포함되어 있습니다. 실제 로그인 정보를 절대 커밋하지 마세요.
