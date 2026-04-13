# hsi-paper-fetcher

Hyperspectral Imaging(HSI) 및 Remote Sensing 관련 논문 PDF 대용량 수집 도구 모음

---

## 목차

1. [프로젝트 구조](#프로젝트-구조)
2. [IEEE 대용량 크롤링 — 1차 개선](#ieee-대용량-크롤링--주요-변경-사항)
   - 2.1 [전체 선택 실패 수정](#21-전체-선택-실패-수정)
   - 2.2 [다수 저널/학회 자동 순회](#22-다수-저널학회-자동-순회)
   - 2.3 [일별 통계 CSV 자동 저장](#23-일별-통계-csv-자동-저장)
   - 2.4 [기타 개선 사항](#24-기타-개선-사항)
3. [IEEE 대용량 크롤링 — 2차 개선](#ieee-대용량-크롤링--2차-개선)
   - 3.1 [빈 페이지 감지 (전체 선택 루프 개선)](#31-빈-페이지-감지-전체-선택-루프-개선)
   - 3.2 [통계 CSV 실시간 업데이트](#32-통계-csv-실시간-업데이트)
   - 3.3 [진행 상황 추적 파일 (progress JSON)](#33-진행-상황-추적-파일-progress-json)
   - 3.4 [--resume 재개 기능](#34---resume-재개-기능)
   - 3.5 [--status 진행 상황 확인](#35---status-진행-상황-확인)
4. [IEEE 대용량 크롤링 — 3차 개선](#ieee-대용량-크롤링--3차-개선)
   - 4.1 [재로그인 후 전체 선택 실패 근본 원인 수정](#41-재로그인-후-전체-선택-실패-근본-원인-수정)
   - 4.2 [Select All 대기 시간 및 스크롤 트리거 개선](#42-select-all-대기-시간-및-스크롤-트리거-개선)
5. [IEEE 대용량 크롤링 — 4차 개선](#ieee-대용량-크롤링--4차-개선)
   - 5.1 [연속 페이지 실패 감지 — 무한 루프 완전 차단](#51-연속-페이지-실패-감지--무한-루프-완전-차단)
   - 5.2 [50개 저널 순위 목록 + --num-journals 옵션](#52-50개-저널-순위-목록----num-journals-옵션)
   - 5.3 [키워드 기반 크롤링 + --with-keywords / --keywords-only 옵션](#53-키워드-기반-크롤링----with-keywords----keywords-only-옵션)
6. [IEEE 대용량 크롤링 — 5차 개선](#ieee-대용량-크롤링--5차-개선)
   - 6.1 [--journal-option: Publication Title 다중 선택 일괄 크롤](#61---journal-option-publication-title-다중-선택-일괄-크롤)
7. [IEEE TGRS 크롤링 전체 흐름](#ieee-tgrs-크롤링-crawling_ieee_2023_2025py)
6. [빠른 시작](#빠른-시작)
7. [전체 옵션](#전체-옵션)
7. [기본 저장 경로](#기본-저장-경로)
8. [Linux 서버에서 screen으로 실행하기](#linux-서버에서-screen으로-실행하기)
9. [예상 출력](#예상-출력)
10. [예상 결과물](#예상-결과물)
11. [ScienceDirect 크롤링](#sciencedirect-크롤링)
12. [위키피디아 크롤링](#위키피디아-크롤링)
13. [토큰 수 계산](#토큰-수-계산)
14. [변경 이력](#변경-이력)

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

## IEEE 대용량 크롤링 — 2차 개선

---

### 3.1 빈 페이지 감지 (전체 선택 루프 개선)

#### 문제
IEEE GRSL 2023년 크롤링 시 **44페이지가 마지막 페이지**인데, URL을 직접 `pageNumber=45`로 이동하면 결과가 0건인 **빈 페이지**가 로드됩니다.  
빈 페이지에는 "전체 선택" 체크박스 자체가 존재하지 않아 `TimeoutException` 이 발생하고, 3회 실패 → 46페이지 이동 → 역시 빈 페이지 → **무한 반복** 상태가 됩니다.

```
[오류] 전체 선택 5회 실패  현재 URL: ...pageNumber=45
[경고] 페이지 45 3회 연속 실패 → 건너뜀
→ 페이지 46 이동 (URL 직접)    ← 46도 빈 페이지 → 루프 지속
```

#### 해결책: `has_search_results()` 함수 추가

페이지 처리 전에 검색 결과가 실제로 존재하는지 먼저 확인합니다.  
결과가 없으면 **해당 저널 크롤링을 즉시 종료**하고 다음 저널로 넘어갑니다.

```
감지 방법 (순서대로):
  1. xpl-result-item, .result-item 등 결과 아이템 요소 탐색 → 있으면 True
  2. "no results found", "0 results" 등 문자열 패턴 감지 → False
  3. 결과 헤더(Dashboard-header 등)에서 "0" 숫자 감지 → False
  4. 위 모두 실패 시 → 빈 페이지로 간주, False
```

---

### 3.2 통계 CSV 실시간 업데이트

기존에는 **저널 1개 완료 후** CSV에 1행을 추가(append)했습니다.  
이제는 **zip 파일 1개 처리 후마다** CSV의 해당 세션 행을 즉시 업데이트합니다.

#### 동작 방식

`CrawlStats.checkpoint()` 메서드가 아래 로직으로 CSV를 갱신합니다:

```
1. stats_YYYY_MM.csv 전체 읽기
2. (date, start_time, year_crawled, journal) 으로 현재 세션 행 탐색
   - 찾으면: 해당 행을 최신 수치로 덮어쓰기 (upsert)
   - 없으면: 새 행 추가 (insert)
3. 전체 파일 다시 쓰기
```

덕분에 크롤링 중 언제든 CSV를 열면 **진행 중인 저널의 최신 통계**를 볼 수 있습니다.

```bash
# 실시간 모니터링 예시
watch -n 30 'tail -5 /nas1/.../manage_files/stats_2026_04.csv | column -t -s,'
```

---

### 3.3 진행 상황 추적 파일 (progress JSON)

크롤링 중 **어느 저널의 몇 페이지까지 완료했는지**를 JSON 파일로 기록합니다.

**파일 위치**: `/nas1/.../01_IEEE_TGRS_1980_2025_logs/manage_files/progress_{year}.json`

**파일 예시**:
```json
{
  "IEEE Transactions on Geoscience and Remote Sensing": {
    "search_term": "Transactions on Geoscience and Remote Sensing",
    "status": "completed",
    "last_page_completed": 204,
    "total_pages_found": 204,
    "pdfs_downloaded": 2036,
    "started_at": "2026-04-06 11:27:03",
    "completed_at": "2026-04-06 14:12:45",
    "last_updated": "2026-04-06 14:12:45"
  },
  "IEEE Geoscience and Remote Sensing Letters": {
    "search_term": "Geoscience and Remote Sensing Letters",
    "status": "in_progress",
    "last_page_completed": 32,
    "pdfs_downloaded": 320,
    "started_at": "2026-04-06 14:13:02",
    "last_updated": "2026-04-06 16:30:11"
  }
}
```

**`status` 값 의미**:

| 값 | 설명 |
|---|---|
| `in_progress` | 크롤링 진행 중 (중단됐을 수도 있음) |
| `completed` | 해당 연도의 모든 페이지 다운로드 완료 |

---

### 3.4 `--resume` 재개 기능

크롤링이 중단됐을 때 처음부터 다시 시작하지 않고, **이전에 완료한 지점부터 이어서** 실행합니다.

```bash
# 중단 후 재개
python crawling_ieee_2023_2025.py --headless --resume --years 2023 2024 2025
```

#### 재개 동작 방식

| 저널 상태 | `--resume` 없을 때 | `--resume` 있을 때 |
|---|---|---|
| 미기록 (처음 실행) | p.1 부터 시작 | p.1 부터 시작 |
| `in_progress` (중단됨) | p.1 부터 **재다운로드** | 마지막 완료 페이지 + 1 부터 이어서 |
| `completed` (완료됨) | p.1 부터 **재다운로드** | 마지막 페이지 + 1 부터 **신규 논문만 체크** |

> **💡 신규 논문 자동 수집**: `completed` 저널도 완전히 건너뛰지 않고 마지막 페이지 + 1 부터 체크합니다.  
> 만약 해당 페이지가 빈 페이지면 바로 종료(신규 없음), 결과가 있으면 계속 다운로드합니다.  
> IEEE에서 새로 발행된 논문이 있어도 자동으로 수집됩니다.

#### 중복 다운로드 방지

`--resume` 없이 재실행해도 **이미 다운로드된 PDF는 자동으로 건너뜁니다**.  
`unzip_and_cleanup()` 에서 같은 파일명이 이미 존재하면 `duplicates_skipped` 카운트만 올리고 넘어갑니다.  
단, 이미 완료된 저널의 페이지를 처음부터 다시 방문하므로 **불필요한 페이지 이동이 발생**합니다.  
시간을 절약하려면 `--resume` 을 사용하세요.

---

### 3.5 `--status` 진행 상황 확인

크롤링을 실행하지 않고 **현재까지의 진행 상황만 출력**합니다.

```bash
python crawling_ieee_2023_2025.py --status --years 2023 2024 2025
```

출력 예시:
```
[진행 상황] progress_2023.json
  전체 저널 30개 | 완료 5 | 진행중 1 | 미시작 24
  completed    | p. 204 |   2036 PDFs | 2026-04-06 14:12 | IEEE Transactions on Geoscience...
  completed    | p.  44 |    440 PDFs | 2026-04-06 15:30 | IEEE Geoscience and Remote Sen...
  in_progress  | p.  32 |    320 PDFs | 2026-04-06 16:30 | IEEE Journal of Selected Topics...
  ...
```

---

## IEEE 대용량 크롤링 — 3차 개선

---

### 4.1 재로그인 후 전체 선택 실패 근본 원인 수정

#### 문제 상황

크롤링 도중 세션이 만료되면 자동으로 재로그인한 뒤 중단됐던 페이지(예: 21페이지)부터 다시 이어갑니다.  
이때 코드는 `pageNumber=21`이 포함된 URL로 바로 이동하고 8초 대기한 후 "전체 선택" 체크박스를 찾았는데, 아래 오류가 반복됐습니다.

```
[세션 만료] 감지 → 재로그인 시도
[OK] 재로그인 성공
→ 페이지 21 이동 (URL 직접)
[오류] 전체 선택 실패 (TimeoutException: 모든 셀렉터에서 체크박스 미발견)
[오류] 전체 선택 실패 ...  ← 계속 반복
```

#### 근본 원인: Angular SPA 의 "콜드 스타트" 문제

IEEE Xplore는 **Angular** 기반의 SPA(Single Page Application)입니다.  
Angular 앱은 처음 로드될 때 내부 컴포넌트들을 순서대로 초기화합니다.  
이때 **"전체 선택" 체크박스가 들어있는 `results-actions` 컴포넌트**는 **1페이지를 정상 경로로 거쳐야만 제대로 초기화**됩니다.

재로그인 직후에는 브라우저가 Angular 앱을 처음 띄운 상태(콜드 스타트)이므로, 21페이지 URL로 바로 이동하면:

| 항목 | 상태 |
|------|------|
| 검색 결과 아이템 | ✅ 정상 표시됨 (`has_search_results()` → True 반환) |
| `results-actions` 컴포넌트 | ❌ 초기화 안 됨 → 체크박스 없음 |

즉, **결과 목록은 보이지만 "전체 선택" 버튼만 없는** 상태가 됩니다.

#### 해결책: `_navigate_with_warmup()` 워밍업 함수

중간 페이지로 바로 이동하는 대신, **반드시 1페이지를 먼저 방문**한 후 목표 페이지로 이동합니다.  
이렇게 하면 Angular가 1페이지에서 `results-actions` 컴포넌트를 완전히 초기화하고, 이후 21페이지로 이동해도 체크박스가 정상적으로 존재합니다.

```
기존 방식:
  재로그인 → pageNumber=21 바로 이동 (8초 대기) → 체크박스 없음 → 실패

새 방식 (_navigate_with_warmup):
  재로그인 → pageNumber=1 이동 (15초 대기 + 스크롤) → pageNumber=21 이동 (15초 대기 + 스크롤) → 체크박스 정상 발견
```

**코드 흐름**:

```python
def _navigate_with_warmup(driver, base_search_url, target_page):
    # 1단계: 1페이지 먼저 방문 → Angular 전체 초기화
    driver.get(base_search_url + "&pageNumber=1")
    time.sleep(15)                        # Angular 컴포넌트 초기화 대기
    driver.execute_script('window.scrollTo(0, 400);')   # 스크롤로 lazy 컴포넌트 강제 렌더링
    time.sleep(2)
    driver.execute_script('window.scrollTo(0, 0);')
    time.sleep(3)

    # 2단계: 목표 페이지 이동 (1페이지가 아닌 경우)
    if target_page > 1:
        driver.get(base_search_url + f"&pageNumber={target_page}")
        time.sleep(15)
        driver.execute_script('window.scrollTo(0, 400);')
        time.sleep(2)
        driver.execute_script('window.scrollTo(0, 0);')
        time.sleep(3)
```

이 함수는 다음 두 곳에서 사용됩니다:
- **재로그인 후 복귀**: 중단된 페이지로 돌아갈 때
- **`--resume` 중간 페이지 시작**: 이전 실행에서 중단된 페이지부터 재개할 때

---

### 4.2 Select All 대기 시간 및 스크롤 트리거 개선

#### 문제

Angular SPA는 스크롤 이벤트가 발생해야 화면 밖에 있는 컴포넌트를 렌더링합니다("lazy rendering").  
페이지 이동 직후 스크롤 없이 체크박스를 바로 탐색하면 아직 렌더링이 안 된 경우가 있습니다.

#### 개선 내용

| 항목 | 기존 | 변경 후 |
|------|------|---------|
| 체크박스 탐색 전 동작 | 없음 | 400px 스크롤 다운 → 다시 최상단 복귀 (lazy 렌더링 강제 트리거) |
| 첫 번째 시도 대기 시간 | 5초 | **25초** (Angular 초기화를 충분히 기다림) |
| 2~5번째 시도 대기 시간 | 5초 | 5초 (유지) |
| 2번째 실패 시 | 페이지 새로고침 | 페이지 새로고침 후 800px 스크롤 |

**스크롤 트리거 동작 설명**:

```
체크박스 탐색 시작
  ↓
400px 아래로 스크롤 → results-actions 컴포넌트 화면에 진입 → Angular lazy 렌더링 시작
  ↓
2초 대기
  ↓
최상단으로 복귀 스크롤
  ↓
3초 대기
  ↓
체크박스 탐색 (최대 25초 대기)
```

이 개선으로 Angular가 초기화되지 않은 직후에도 스크롤 트리거를 통해 렌더링을 강제 실행해 체크박스를 안정적으로 찾을 수 있습니다.

---

## IEEE 대용량 크롤링 — 4차 개선

---

### 5.1 연속 페이지 실패 감지 — 무한 루프 완전 차단

#### 문제

2024년 GRSL(IEEE Geoscience and Remote Sensing Letters) 크롤링 중 **p.45부터 모든 페이지에서 "전체 선택 실패"** 가 반복됐습니다.

```
[재시도 1/5] 전체 선택 실패 (TimeoutException: 모든 셀렉터에서 체크박스 미발견)
[재시도 2/5] 전체 선택 실패 ...
[재시도 3/5] 전체 선택 실패 ...
...
[경고] 페이지 45 3회 연속 실패 → 건너뜀
→ 페이지 46 이동  ← 46도 동일 실패
→ 페이지 47 이동  ← 47도 동일 실패
... (무한 반복)
```

#### 근본 원인

`has_search_results()` 는 **결과 아이템이 있어서 True 를 반환**했지만, 검색 결과는 보이면서도 "전체 선택" 버튼이 화면에서 사라지는 상황이었습니다.

이는 IEEE Xplore 프록시의 **세션 내 다운로드 할당량 소진** 또는 **일시적 다운로드 UI 비활성화**로 추정됩니다. 이 상태에서는:
- 논문 목록 보기: ✅ 정상
- "Select All" / "Download PDFs" 버튼: ❌ UI에서 제거됨

기존 코드는 단일 페이지의 실패만 감지했기 때문에, 이 상태가 되면 **모든 페이지를 건너뛰는 무한 루프**에 빠졌습니다.

#### 해결책: 연속 페이지 실패 감지 (`MAX_CONSECUTIVE_PAGE_FAILS`)

```
기존 동작:
  페이지 45 실패 3회 → 건너뜀 → 페이지 46 → 실패 3회 → 건너뜀 → ... (무한)

새 동작:
  페이지 45 실패 3회 → 건너뜀 (연속 1페이지 실패)
  페이지 46 실패 3회 → 건너뜀 (연속 2페이지 실패)
  페이지 47 실패 3회 → 건너뜀 (연속 3페이지 실패)
  → MAX_CONSECUTIVE_PAGE_FAILS(3) 도달 → "[중단] 저널 크롤링 중단" → 다음 저널로!
```

| 설정값 | 위치 | 기본값 | 설명 |
|--------|------|--------|------|
| `MAX_CONSECUTIVE_PAGE_FAILS` | `CrawlConfig` | 3 | 연속 N페이지 완전 실패 시 저널/키워드 중단 |

성공한 페이지가 하나라도 나오면 연속 실패 카운터는 0으로 리셋됩니다.

---

### 5.2 50개 저널 순위 목록 + `--num-journals` 옵션

#### `JOURNAL_TARGETS_ALL` — 초분광 관련도 기준 50개 저널 순위

기존 30개 저널에서 **50개로 확장**했으며, 초분광(HSI) 및 원격탐사(RS) 관련도 순으로 정렬했습니다.

| Tier | 번호 | 분야 | 대표 저널 |
|------|------|------|-----------|
| Tier 1 | 1~10 | 초분광·원격탐사 핵심 | TGRS, GRSL, JSTARS, Sensors, IEEE Access, IGARSS, TIP, TPAMI, TNNLS, RS Magazine |
| Tier 2 | 11~15 | 신호 처리·계산 영상 | JSTSP, TSP, Trans. Comp. Imaging, Photonics J., ICIP |
| Tier 3 | 16~20 | 항공우주·측정·CV 학회 | TAES, TMM, CVPR, ICCV, TIM |
| Tier 4 | 21~25 | 영상 처리·의료·산업 | TCSVT, Proc. IEEE, SPL, Trans. Med. Imaging, TIE |
| Tier 5 | 26~30 | AI·로보틱스·광학 | Cybernetics, TAI, TETCI, PTL, RAL |
| Tier 6 | 31~35 | 학회·오픈 저널 | ICASSP, Intl Geoscience, Big Data, WACV, Systems J. |
| Tier 7 | 36~40 | 해양·지속가능·광통신 | Oceanic Eng., Sustainable Energy, Lightwave, Ind. Informatics, Open J. Signal |
| Tier 8 | 41~45 | 방송·메카트로닉스 등 | SP Magazine, Aerospace Conf., Broadcasting, Mechatronics, MLSP |
| Tier 9 | 46~50 | 확장 커버리지 | Radiation & Plasma, Smart Grid, Antennas, Microwave, Latin America |

#### `--num-journals` 옵션 사용법

```bash
# Tier 1만 (10개, 초분광·원격탐사 핵심 저널)
python crawling_ieee_2023_2025.py --headless --num-journals 10 --years 2024 2025

# Tier 1~2 (15개)
python crawling_ieee_2023_2025.py --headless --num-journals 15 --years 2024 2025

# Tier 1~5 (30개, 기본값)
python crawling_ieee_2023_2025.py --headless --years 2024 2025

# 전체 50개
python crawling_ieee_2023_2025.py --headless --num-journals 50 --years 2024 2025
```

> **💡 권장**: 처음 실행 시 `--num-journals 10`으로 핵심 저널부터 다운로드하고,  
> 이후 `--resume --num-journals 30`, `--resume --num-journals 50` 순으로 확장하세요.

---

### 5.3 키워드 기반 크롤링 + `--with-keywords` / `--keywords-only` 옵션

#### 왜 키워드 기반 크롤링이 필요한가?

저널 기반 크롤링은 **지정한 50개 저널 안에서만** 논문을 수집합니다.  
키워드 기반 크롤링은 **IEEE Xplore 전체**에서 키워드로 검색해, 50개 목록에 없는 저널의 관련 논문까지 수집합니다.  
두 방법을 결합하면 PDF 수집량이 대폭 늘어납니다.

#### `KEYWORD_SEARCH_TERMS` — 54개 검색 키워드

| 분야 | 키워드 예시 |
|------|-----------|
| 초분광 핵심 | hyperspectral imaging, hyperspectral remote sensing, spectral unmixing, hyperspectral anomaly detection |
| 다분광·스펙트럼 | multispectral imaging, spectral imaging, spectral analysis |
| 위성·항공·드론 | remote sensing image classification, satellite image analysis, UAV remote sensing |
| SAR/레이더 | SAR image processing, synthetic aperture radar, PolSAR, InSAR |
| LiDAR/3D | LiDAR remote sensing, point cloud classification |
| 딥러닝 방법론 | deep learning remote sensing, transformer remote sensing, GAN remote sensing |
| 토지·환경 응용 | land cover classification, vegetation mapping, precision agriculture |
| 도시·재해 응용 | urban remote sensing, flood detection, wildfire detection satellite |
| 해양·빙설 | ocean remote sensing, sea ice remote sensing, soil moisture estimation |
| 의료·광학 | medical hyperspectral imaging, mineral mapping, pansharpening |

#### 사용법

```bash
# 저널(30개) + 키워드(54개) 동시 크롤링 — 가장 많은 PDF 수집
python crawling_ieee_2023_2025.py --headless --with-keywords --years 2024 2025

# 저널 수 확대 + 키워드 동시 크롤링
python crawling_ieee_2023_2025.py --headless --num-journals 50 --with-keywords --years 2024 2025

# 키워드 기반 크롤링만 (저널 건너뜀)
python crawling_ieee_2023_2025.py --headless --keywords-only --years 2024 2025

# 재개 모드 + 키워드 포함
python crawling_ieee_2023_2025.py --headless --resume --with-keywords --years 2024 2025
```

#### 동작 순서

```
[연도별 실행]
  1단계: 저널 기반 크롤링 (--num-journals N개 저널 순회)
      ↓
  2단계: 키워드 기반 크롤링 (54개 키워드 순차 검색, --with-keywords 시)
      - 각 키워드로 IEEE Xplore 전체 검색 (저널 필터 없음)
      - 연도 필터만 적용: ranges=YYYY_YYYY_Year&queryText=<keyword>
      - 기존과 동일한 페이지별 다운로드 루프
      - 파일명 기반 중복 제거 자동 처리
```

---

## IEEE 대용량 크롤링 — 5차 개선

---

### 6.1 `--journal-option`: Publication Title 다중 선택 일괄 크롤

#### 배경

기존 방식(`--num-journals`)은 `JOURNAL_TARGETS_ALL` 리스트에서 저널을 **하나씩 순서대로** 선택·크롤했습니다.  
실제 IEEE Xplore에 없는 저널이 포함될 수 있고, 리스트 기반이라 실제 IEEE 사이드바 상황과 다를 수 있는 문제가 있었습니다.

**5차 개선**에서는 IEEE Xplore 검색 결과 왼쪽 사이드바의 **Publication Title 필터**를 직접 조작하는 4가지 옵션을 추가했습니다.

#### 옵션별 동작

| 옵션 | 동작 | 적합한 상황 |
|------|------|------------|
| `--journal-option all` | **Publication Title 필터 미적용** → 연도 필터만 걸고 전체 다운로드 | IEEE 전체를 연도별로 수집 |
| `--journal-option 1` | Publication Title 검색창에 **"Remote Sensing"** 입력 → 나오는 항목 **전체 체크** → 일괄 크롤 | Remote Sensing 관련 저널 전부 수집 |
| `--journal-option 2` | **4개 고정 저널** 선택 (IEEE Access / Sensors Journal / IGARSS `{year}` / TGRS) → 일괄 크롤 | 핵심 저널만 빠르게 수집 |
| `--journal-option 3` | 검색 없이 기본 목록 **상위 5개** 체크 → 일괄 크롤 | IEEE가 보여주는 상위 게재 저널 |
| `--journal-option 4` | 검색 없이 기본 목록 **상위 10개** 체크 → 일괄 크롤 | 상위 10개 넓은 커버리지 |

> `--journal-option 2`의 IGARSS는 크롤링 연도에 맞게 자동 치환됩니다.  
> 예: `--years 2024` → `"IGARSS 2024"` 검색

#### `--years all` 옵션

`--years all`을 지정하면 **연도 필터를 적용하지 않고** IEEE Xplore 전체를 대상으로 크롤링합니다.

```bash
# 연도 필터 없이 IEEE 전체 (필터도 없음)
python crawling_ieee_2023_2025.py --headless --journal-option all --years all

# 연도 필터 없이 저널 기반 크롤
python crawling_ieee_2023_2025.py --headless --num-journals 10 --years all
```

> **주의**: `--years all`은 방대한 양의 논문을 대상으로 하므로 실행 전 저장 공간을 확인하세요.

#### 기존 방식과의 차이

| 항목 | 기존 (`--num-journals`) | 신규 (`--journal-option`) |
|------|------------------------|--------------------------|
| 저널 선택 기준 | 코드 내 고정 리스트 순위 | IEEE 사이드바 실시간 상태 |
| 크롤 단위 | 저널 1개씩 순차 실행 | 선택 전체를 1번에 묶어 실행 |
| 존재하지 않는 저널 | 필터 실패 → 건너뜀 | 처음부터 선택하지 않음 |
| 통계 기록 | 저널별 별도 행 | `[OPT{N}]` 태그 1개 행 |

#### 사용법

```bash
# option all: 필터 없이 전체 (연도 필터만 적용)
python crawling_ieee_2023_2025.py --headless --journal-option all --years 2024 2025

# option all + 전체 연도: 연도·저널 모두 필터 없이 IEEE 전체 다운로드
python crawling_ieee_2023_2025.py --headless --journal-option all --years all

# option1: "Remote Sensing" 검색 → 모든 관련 저널 일괄 크롤
python crawling_ieee_2023_2025.py --headless --journal-option 1 --years 2024 2025

# option2: 4개 고정 저널 (IEEE Access / Sensors / IGARSS / TGRS)
python crawling_ieee_2023_2025.py --headless --journal-option 2 --years 2024 2025

# option3: 상위 5개 저널 (검색 없이 기본 목록)
python crawling_ieee_2023_2025.py --headless --journal-option 3 --years 2023 2024 2025

# option4: 상위 10개 저널 (검색 없이 기본 목록)
python crawling_ieee_2023_2025.py --headless --journal-option 4 --years 2023 2024 2025

# resume 가능
python crawling_ieee_2023_2025.py --headless --resume --journal-option 2 --years 2024 2025
```

> **참고**: `--journal-option` 은 `--num-journals`, `--with-keywords`, `--keywords-only` 와 함께 사용할 수 없습니다.

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

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--headless` | — | 브라우저를 화면 없이 실행 (서버용) |
| `--resume` | — | 이전 중단 지점부터 재개 (`progress_YEAR.json` 참조) |
| `--status` | — | 진행 상황만 출력하고 종료 (크롤링 안 함) |
| `--num-journals N` | `30` | 크롤링할 저널 수 (10/15/20/25/30/35/40/45/50 중 택1, 초분광 관련도 순위 상위 N개) |
| `--with-keywords` | — | 저널 크롤링 후 54개 키워드 기반 추가 크롤링 실행 |
| `--keywords-only` | — | 키워드 기반 크롤링만 실행 (저널 크롤링 건너뜀) |
| `--year INT` | — | 단일 연도 (예: `--year 2024`) |
| `--years INT...` | — | 복수 연도 (예: `--years 2023 2024 2025`) |
| `--save-path PATH` | Linux/Windows 기본값 | PDF 저장 기본 경로 |
| `--username STR` | — | 도서관 로그인 ID |
| `--password STR` | — | 도서관 로그인 비밀번호 |

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

### KIST 차단 페이지 근본 원인 수정 — Chrome 프로필 초기화 및 재시도 전략 개선

- **근본 원인 파악**: KIST 차단(`웹서비스 차단 안내`)은 버튼 없는 서버 사이드 일시 차단. 이전 실행에서 누적된 Chrome 프로필 쿠키·히스토리가 재차 차단을 유발
- **`setup_driver()` 수정**: Chrome 프로필을 NAS 경로(`/nas1/.chrome_profile`) 대신 **로컬 경로**(`/data/khkim/chrome_tmp/.chrome_profile`)에 생성. 매 실행 시 `shutil.rmtree`로 완전 초기화. NAS `rmtree` 실패 시 `SingletonLock` 만 제거하는 폴백 유지
- **`access_ieee_via_library()` 전면 재작성**: KIST 감지 시 KIST 창 닫기 → 라이브러리 창 복귀 → 대기(2분·5분) → IEEE 링크 재클릭 전략 적용. 버튼 클릭 시도 코드 제거. 최종 실패 시 `False` 반환
- **`login_kookmin_library()` 수정**: 로그인 버튼 클릭 시 Angular Material 오버레이(`cdk-overlay-backdrop`) 닫기 후 JS 폴백 클릭 적용
- **`_relogin_and_setup()` 수정**: `access_ieee_via_library()` 실패 시 쿠키 삭제 루프 제거 (프로필 초기화로 대체)

---

### `--journal-option all` 및 `--years all` 추가 (5차 개선 보완)

- **`--journal-option all` 추가**: Publication Title 필터를 전혀 적용하지 않고 연도 필터만으로 IEEE 전체 크롤. `_crawl_with_journal_option`, `_relogin_and_setup`, `_do_year_crawl` 에 `option == 'all'` 분기 추가
- **`--years all` 추가**: `--years` 인수 타입을 `str` 로 변경하여 숫자 목록 또는 `all` 허용. `setup_ieee_advanced_search` 에 `year == 'all'` 분기 추가 — 연도 필터 없이 검색 버튼만 클릭
- **폴백 URL 수정**: 연도 파라미터 없는 `searchresult.jsp` URL 사용 (`--years all` 시 `ranges=` 파라미터 제거)
- **CLI 변경**: `--journal-option` choices에 `'all'` 추가 (`{1,2,3,4,all}`), `--year`/`--years` `type=str` 변경
- **시작 요약 출력**: `years == ['all']` 이면 `전체 연도 (필터 없음)` 표시

---

### `--years all` 실행 시 `CrawlStats` 크래시 수정

- **버그**: `CrawlStats.__init__` 에서 `int(year)` 호출 시 `year='all'` 이면 `ValueError` 발생하여 크롤링 즉시 종료
- **수정**: `year_crawled = int(year)` → `year_crawled = str(year)` 로 변경 (CSV에 `all` 문자열로 저장)
- **`_year_label(year)` 헬퍼 함수 추가**: `year='all'` 이면 `전체 연도`, 아니면 `{year}년` 반환. 로그 출력 `{year}년` → `{_year_label(year)}` 일괄 교체 (`_do_year_crawl`, `_crawl_one_journal`, `_crawl_by_keyword`, `_crawl_with_journal_option`, main 루프 포함)

---

### `--journal-option` Publication Title 다중 선택 일괄 크롤 추가 (5차 개선)

- **`JOURNAL_OPTION2_FIXED` 상수 추가**: `--journal-option 2` 용 4개 고정 저널 정의 (IEEE Access, Sensors Journal, IGARSS `{year}`, TGRS). `{year}` 는 크롤링 연도로 자동 치환
- **`apply_publication_filter_multi()` 함수 추가**: Publication Title 필터 다중 선택 후 Apply 한 번에 처리. option 1~4 분기 처리
- **`_crawl_with_journal_option()` 함수 추가**: 다중 필터 적용 후 단일 크롤 단위로 전 페이지 다운로드. 재로그인·resume·연속실패감지 모두 지원
- **`_relogin_and_setup()` 수정**: `journal_option` 파라미터 추가. 재로그인 후 `apply_publication_filter_multi` 또는 기존 `apply_publication_filter` 분기 적용
- **`_do_year_crawl()` 수정**: `journal_option` 파라미터 추가. 값이 있으면 `_crawl_with_journal_option` 단일 호출, 없으면 기존 저널별 순회
- **`--journal-option {1,2,3,4}` CLI 인수 추가**: `parse_args()` 및 `main()` 업데이트, 크롤링 모드 요약 출력에 반영
- **README_ko.md 5차 개선 내용 추가** (6.1 섹션)

---

### 연속 페이지 실패 감지 + 50개 저널 순위 목록 + 키워드 기반 크롤링 추가

- **연속 페이지 실패 감지 추가** (`MAX_CONSECUTIVE_PAGE_FAILS=3`): GRSL 2024 p.45+ 에서 발생한 "전체 선택 실패 무한 루프" 수정. 결과는 있지만 Select All UI가 사라진 상태(다운로드 할당량 소진 추정)에서 3페이지 연속 완전 실패 시 저널 크롤링을 자동 종료하고 다음 저널로 이동
- **`JOURNAL_TARGETS_ALL` 50개 저널** 추가: 기존 31개 → 50개로 확장, 초분광·원격탐사 관련도 기준 Tier 1~9 순위 정렬 (Tier 1: TGRS·GRSL·JSTARS·Sensors·Access·IGARSS·TIP·TPAMI·TNNLS·RS Magazine)
- **`--num-journals` 옵션 추가**: 10/15/20/25/30/35/40/45/50 중 택1. 초분광 관련도 순위 상위 N개 저널만 크롤링 (기본값 30)
- **`KEYWORD_SEARCH_TERMS` 54개 키워드** 추가: IEEE Xplore queryText 기반 키워드 검색으로 50개 저널 외 전체 IEEE 출판물 대상 관련 논문 수집
- **`setup_keyword_search()` 함수 추가**: 키워드 + 연도 파라미터를 URL로 조합해 저널 필터 없는 전체 IEEE 검색 설정
- **`_crawl_by_keyword()` 함수 추가**: 키워드 기반 페이지 루프 (연속 실패 감지·재로그인·resume 모두 지원)
- **`--with-keywords` / `--keywords-only` 옵션 추가**: 저널+키워드 병행 또는 키워드만 실행 선택
- **README_ko.md 4차 개선 내용 추가** (5.1~5.3 섹션)

---

### 재로그인 후 Angular 콜드스타트 문제 해결 — 워밍업 네비게이션 + Select All 안정성 강화

- **`_navigate_with_warmup()` 추가**: 재로그인 또는 `--resume` 중간 페이지 시작 시 반드시 1페이지를 먼저 방문해 Angular `results-actions` 컴포넌트를 완전히 초기화한 뒤 목표 페이지로 이동. 재로그인 후 "전체 선택" 체크박스 미발견 오류의 근본 원인(Angular SPA 콜드스타트) 해결
- **`select_all_results()` 스크롤 트리거 추가**: 탐색 전 400px 스크롤 다운 → 최상단 복귀로 Angular lazy 렌더링을 강제 실행. 첫 번째 시도 대기 시간을 5초 → 25초로 늘려 초기화 지연 허용
- **`_crawl_one_journal` 재로그인 블록 개선**: 기존 URL 직접 이동 + `time.sleep(8)` 을 `_navigate_with_warmup()` 호출로 교체
- **`--resume` 중간 페이지 시작 개선**: `start_page > 1` 케이스도 `_navigate_with_warmup()` 사용
- **README_ko.md 3차 개선 내용 추가** (4.1~4.2 섹션)

---

### 빈 페이지 감지 + 통계 실시간 업데이트 + resume 재개 기능

- **`has_search_results()` 추가**: 결과 0건 빈 페이지에서 "전체 선택" 무한 실패하던 문제 해결. 빈 페이지 감지 즉시 저널 루프 종료
- **`CrawlStats.checkpoint()` 추가**: zip 1건 처리 후마다 `stats_YYYY_MM.csv` 를 upsert (세션 행 in-place 업데이트). 실시간 모니터링 가능
- **`ProgressTracker` 클래스 추가**: 저널별 진행 상황을 `manage_files/progress_{year}.json` 에 실시간 기록
- **`--resume` 플래그 추가**: 이전 실행에서 중단된 지점부터 재개. 완료 저널은 신규 논문만 체크
- **`--status` 플래그 추가**: 진행 상황만 출력하고 종료 (크롤링 실행 안 함)
- **README_ko.md 2차 개선 내용 추가** (3.1~3.5 섹션)

---

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
