# hsi-paper-fetcher

Hyperspectral Imaging(HSI) 및 Remote Sensing 관련 논문 PDF 대용량 수집 도구 모음

---

## 목차

1. [프로젝트 구조](#프로젝트-구조)
2. [IEEE 대용량 크롤링 — 주요 변경 사항](#ieee-대용량-크롤링--주요-변경-사항)
   - 2.1 [전체 선택 실패 수정](#21-전체-선택-실패-수정)
   - 2.2 [다수 저널/학회 자동 순회](#22-다수-저널학회-자동-순회)
   - 2.3 [일별 통계 CSV 자동 저장](#23-일별-통계-csv-자동-저장)
   - 2.4 [기타 개선 사항](#24-기타-개선-사항)
3. [IEEE TGRS 크롤링 전체 흐름](#ieee-tgrs-크롤링-crawling_ieee_2023_2025py)
4. [빠른 시작](#빠른-시작)
5. [전체 옵션](#전체-옵션)
6. [기본 저장 경로](#기본-저장-경로)
7. [Linux 서버에서 screen으로 실행하기](#linux-서버에서-screen으로-실행하기)
8. [예상 출력](#예상-출력)
9. [예상 결과물](#예상-결과물)
10. [ScienceDirect 크롤링](#sciencedirect-크롤링)
11. [위키피디아 크롤링](#위키피디아-크롤링)
12. [토큰 수 계산](#토큰-수-계산)
13. [변경 이력](#변경-이력)

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

## IEEE 대용량 크롤링 — 주요 변경 사항

> **목표**: 6개월 내 최소 100만 PDF 수집을 위한 대용량 수집 체계 구축

---

### 2.1 전체 선택 실패 수정

**문제**: `전체 선택 3회 실패 (TimeoutException)` — IEEE Xplore의 Angular 렌더링이 완료되기 전에 체크박스를 탐색해 `TimeoutException` 발생.

**수정 내용**:

| 항목 | 기존 | 변경 후 |
|------|------|---------|
| CSS 셀렉터 | 1개 고정 | 10개 폴백 셀렉터 순차 탐색 |
| 최대 재시도 횟수 | 3회 | 5회 |
| 2번째 실패 시 | 10초 대기 | 페이지 새로고침 + 15초 대기 |
| 4번째 실패 시 | — | JavaScript로 checkbox 직접 탐색·클릭 |
| 탐색 전 동작 | — | 맨 위로 스크롤 후 렌더링 대기 |

추가된 CSS 셀렉터 목록:
```
input.results-actions-selectall-checkbox       ← 기존
input[type='checkbox'][class*='selectall']
input[type='checkbox'][class*='select-all']
input[type='checkbox'][aria-label*='Select all']
input[type='checkbox'][aria-label*='Select All']
.results-actions-selectall input[type='checkbox']
xpl-select-all input[type='checkbox']
div.results-actions input[type='checkbox']
input[type='checkbox'][id*='select-all']
```

---

### 2.2 다수 저널/학회 자동 순회

기존에는 **IEEE TGRS 1개** 저널만 다운로드했으나, 이제 `JOURNAL_TARGETS` 에 정의된 **30개 저널/학회**를 자동으로 순회합니다.

#### 대상 저널/학회 목록 (`JOURNAL_TARGETS`)

| 분야 | 저널/학회 |
|------|-----------|
| Remote Sensing 핵심 | IEEE TGRS, IEEE GRSL, IEEE JSTARS |
| 이미지 처리 / 비전 | IEEE TIP, IEEE TPAMI, IEEE TMM, IEEE TCSVT |
| 신호 처리 | IEEE TSP, IEEE SPL, IEEE JSTSP |
| 광학 / 센서 | IEEE Sensors Journal, IEEE Photonics Journal, IEEE PTL |
| 측정 / 항공우주 | IEEE TIM, IEEE TAES, IEEE Systems Journal |
| AI / 머신러닝 | IEEE TNNLS, IEEE TCYB, IEEE TAI, IEEE TETCI |
| 종합 저널 | IEEE Access, Proceedings of the IEEE |
| 학회 | IGARSS, ICIP, CVPR, ICCV, ICASSP |

**동작 방식**:
1. 각 연도별로 `JOURNAL_TARGETS` 의 저널을 순차 순회
2. 저널마다 Advanced Search → Publication Title 필터 → 전체 페이지 다운로드
3. PDF 파일명 기반 중복 제거 (이미 다운로드된 파일은 자동 건너뜀)
4. 저널별 완료 시 통계 CSV에 1행 추가

---

### 2.3 일별 통계 CSV 자동 저장

**저장 위치**: `/nas1/hyperspectral_literature_data_collected/01_IEEE_TGRS_1980_2025_logs/manage_files/`

**파일 명명**: `stats_YYYY_MM.csv` (월별 1개 파일, 실행 시 자동 append)

**CSV 컬럼**:

| 컬럼 | 설명 |
|------|------|
| `date` | 크롤링 날짜 (YYYY-MM-DD) |
| `start_time` | 시작 시각 (HH:MM:SS) |
| `end_time` | 종료 시각 (HH:MM:SS) |
| `elapsed_minutes` | 소요 시간 (분) |
| `year_crawled` | 크롤링 대상 연도 |
| `journal` | 저널/학회 이름 |
| `pages_processed` | 성공적으로 처리한 페이지 수 |
| `pages_skipped` | 연속 실패로 건너뜀 페이지 수 |
| `zip_downloads` | 완료된 zip 다운로드 건수 |
| `pdfs_extracted` | 실제 추출된 PDF 파일 수 |
| `duplicates_skipped` | 중복으로 건너뜀 PDF 수 |
| `select_all_failures` | 전체 선택 실패 횟수 |
| `download_failures` | 다운로드 타임아웃/실패 횟수 |
| `session_relogins` | 세션 만료로 인한 재로그인 횟수 |

**예시**:
```csv
date,start_time,end_time,elapsed_minutes,year_crawled,journal,pages_processed,pages_skipped,zip_downloads,pdfs_extracted,duplicates_skipped,select_all_failures,download_failures,session_relogins
2026-04-06,09:00:00,11:30:00,150.0,2025,IEEE Transactions on Geoscience and Remote Sensing,286,2,286,2854,8,0,2,1
2026-04-06,11:31:00,12:15:00,44.0,2025,IEEE Geoscience and Remote Sensing Letters,52,0,52,520,0,0,0,0
```

---

### 2.4 기타 개선 사항

| 항목 | 기존 | 변경 후 |
|------|------|---------|
| `MAX_PAGE_VISITS` | 100 페이지 제한 | 9999 (사실상 무제한) |
| 저널 필터 함수 | `apply_publication_filter(driver, journal_name)` — 검색어 하드코딩 | `apply_publication_filter(driver, search_term, label_match)` — 파라미터화 |
| 세션 재로그인 | 고정 저널로 복구 | 현재 순회 중인 저널로 필터 복구 |
| 통계 추적 | 없음 | `CrawlStats` 클래스로 저널별 세밀 추적 |

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

### Linux 서버에서 screen으로 실행하기

서버에서 장시간 실행할 때는 `screen`을 사용해 세션이 끊겨도 크롤링이 계속되도록 합니다.

```bash
# 1. screen 세션 생성
screen -S ieee_crawl

# 2. 가상환경 활성화 (사용 시)
source .venv/bin/activate

# 3. 크롤링 실행 (2023~2025년, headless 모드)
python crawling_ieee_2023_2025.py --headless --years 2023 2024 2025

# 4. 세션 분리 (SSH 연결을 끊어도 백그라운드에서 계속 실행됨)
#    키보드: Ctrl+A, 이후 D

# 5. 세션 재접속 (나중에 결과 확인 시)
screen -r ieee_crawl

# 6. 실행 중인 screen 목록 확인
screen -ls
```

---

### 예상 출력

실행하면 아래와 같은 로그가 출력됩니다.

```
============================================================
IEEE TGRS 논문 크롤러 시작
============================================================
  브라우저    : headless
  대상 연도   : [2023, 2024, 2025]
  저장 경로   : /nas1/hyperspectral_literature_data_collected/01_IEEE_TGRS_1980_2025
  로그인 ID   : <학번>
============================================================

[Chrome] 드라이버 초기화 완료 (headless)

1단계: 국민대 성곡도서관 로그인
[OK] ID 입력 / 비밀번호 입력 / 로그인 버튼 클릭
[OK] 로그인 완료

2단계: 학술정보DB → IEEE Xplore 접속
[OK] IEEE 링크 발견 → 새 창 전환 완료
[OK] 국민대 프록시 인증 확인됨

############################################################
# 2023년 크롤링 시작  [2026-03-06 12:00:00]
############################################################

[CDP] 다운로드 경로(Browser): .../2023

3단계: 2023년 논문 Advanced Search 설정 ...
4단계: 저널 필터 적용 - IEEE Transactions on Geoscience and Remote Sensing ...
5단계: 페이지당 10개 항목 설정

============================================================
페이지 1 처리
============================================================
[OK] Select All on Page 클릭
[OK] Download PDFs 클릭
[OK] 다운로드 확인 클릭
[대기] 다운로드 중... (최대 300초)
[진행] 다운로드 시작 감지: bulk_download_xxxxx.zip.crdownload
[OK] 다운로드 완료: bulk_download_xxxxx.zip  (페이지 1, 12480 KB)
  [압축해제] paper_001.pdf
  [압축해제] paper_002.pdf
  ...
[OK] PDF 추출: 10개  (중복 건너뜀: 0개)
[OK] zip 삭제: bulk_download_xxxxx.zip
→ 페이지 2 이동

... (이하 반복) ...

[완료] 2023년 모든 페이지 처리 완료!

[대기] 다음 연도 전 30초 대기...

############################################################
# 2024년 크롤링 시작  [2026-03-06 14:30:00]
############################################################
...

############################################################
# 모든 연도 크롤링 완료!  [2026-03-06 17:00:00]
############################################################
```

**실패/재시도 시 출력 예시:**

```
[경고] 다운로드 타임아웃
[정리] 미완료 임시파일 삭제: bulk_download_xxxxx.zip.crdownload
[경고] 페이지 3 실패 (1/3), 10분 대기 후 재시도
...
[경고] 페이지 3 3회 연속 실패 → 건너뜀   ← 3회 초과 시 해당 페이지 건너뛰고 진행
```

---

### 예상 결과물

크롤링이 완료되면 아래 구조로 파일이 저장됩니다.

```
/nas1/hyperspectral_literature_data_collected/01_IEEE_TGRS_1980_2025/
├── 2023/
│   ├── paper_001.pdf
│   ├── paper_002.pdf
│   └── ...  (약 수백~수천 개)
├── 2024/
│   └── ...
├── 2025/
│   └── ...
└── (저장경로)_logs/
    ├── 2023/
    │   └── crawl_2023_20260306_120000.log
    ├── 2024/
    │   └── crawl_2024_20260306_143000.log
    └── 2025/
        └── crawl_2025_20260306_161500.log
```

> 로그 파일에는 콘솔 출력 전체가 저장되므로, 실행 중이거나 종료 후 `tail -f` 로 확인할 수 있습니다.
>
> ```bash
> tail -f /nas1/hyperspectral_literature_data_collected/01_IEEE_TGRS_1980_2025_logs/2023/crawl_2023_*.log
> ```

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

## 변경 이력

### 대용량 수집 체계 구축 — 다수 저널 순회 + 전체 선택 수정 + 통계 CSV

- **전체 선택 실패 수정**: 기존 1개 CSS 셀렉터에서 10개 폴백 셀렉터 + 재시도 5회 + 페이지 새로고침 + JS 직접 클릭 방식으로 안정성 대폭 향상
- **다수 저널/학회 자동 순회**: `JOURNAL_TARGETS` 리스트에 30개 저널/학회 정의. 연도별로 모든 저널을 순차 다운로드
- **일별 통계 CSV 자동 저장**: `manage_files/stats_YYYY_MM.csv` 에 저널별 통계 (페이지 수, PDF 수, 중복 수, 실패 수 등) 자동 기록
- **MAX_PAGE_VISITS 제한 해제**: 100 → 9999 (전체 페이지 다운로드)
- **apply_publication_filter 파라미터화**: `journal_name` 하드코딩 제거 → `(search_term, label_match)` 파라미터로 모든 저널 지원
- **CrawlStats 클래스 추가**: 저널별 세밀한 통계 추적 (`pages_processed`, `pdfs_extracted`, `select_all_failures` 등)

---

### 다운로드 타임아웃 및 무한 루프 수정
- **`Browser.setDownloadBehavior` 적용**: `Page.setDownloadBehavior`는 Chrome 신버전 headless 모드에서 다운로드 경로가 반영되지 않는 문제가 있었음. `Browser.setDownloadBehavior`(실패 시 `Page` 버전으로 fallback)로 교체해 headless 환경에서도 지정 경로에 파일이 저장되도록 수정
- **페이지 무한 재시도 방지**: 페이지 다운로드 실패 시 동일 페이지를 영원히 재시도하던 문제 수정. `MAX_PAGE_RETRIES=3` 도입 — 3회 연속 실패 시 해당 페이지를 건너뛰고 다음 페이지로 진행
- **`.crdownload` 파일 감지 및 정리**: 다운로드 진행 중인 임시파일(`.crdownload`)을 감지해 로그에 표시. 타임아웃 시 미완료 임시파일을 자동 삭제해 다음 시도에 영향 없도록 수정

### 페이지네이션 수정 (`locate_next_arrow`)
- IEEE Xplore는 1–10페이지만 번호 버튼(`stats-Pagination_N`)을 표시하고, 11페이지부터는 `>` 화살표 버튼으로만 이동 가능
- 기존: 11페이지 버튼을 못 찾으면 크롤링 종료 → **최대 10페이지(약 100편)만 다운로드**
- 수정: `locate_next_arrow()` 추가. 번호 버튼이 없으면 `>` / `Next` 화살표 버튼을 클릭하여 다음 페이지 이동

### 세션 재사용 수정 (`_do_year_crawl`)
- 기존: 연도마다 Chrome 드라이버를 새로 만들고 도서관 로그인을 반복
- 수정: 드라이버와 로그인 세션을 1회만 생성하고, 연도 전환 시 CDP 명령으로 다운로드 경로만 변경
- 효과: 연도 간 전환이 빨라지고, 불필요한 로그인 트래픽 제거

### 기타 수정 이력
- 다운로드 후 zip 자동 압축 해제 및 PDF 추출 (`zipfile` 모듈)
- 복수 파일 동시 다운로드 팝업 차단 해제 (`automatic_downloads: 1`)
- 리눅스 서버 Headless 실행 시 연도별 로그 파일 생성 (`{저장경로}_logs/{연도}/crawl_*.log`)
- 저널 필터 DOM 경로 수정 (Publication Title 섹션 XPath 확정)
- NAS 파일시스템 Permission denied 우회 (파일 rename 제거)

---

## 참고사항

- `credentials.json`은 `.gitignore`에 포함 → 절대 커밋되지 않음
- IEEE Seat Limit 발생 시 스크립트가 자동으로 5분 대기 후 재시도
- `webdriver-manager` 설치 시 ChromeDriver 버전 자동 관리
- 리눅스 서버에 Chrome 145가 수동 설치된 경우 자동 감지 (`/data/khkim/chrome_local/...`)
