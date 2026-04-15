# ScienceDirect(Elsevier) 논문 크롤러

국민대학교 성곡도서관 → ScienceDirect 프록시를 통해  
HSI/원격탐사 관련 Elsevier 저널 PDF를 대량으로 수집하는 도구입니다.

> **[English README (상위 폴더)](../README.md)**

---

## 파일 구성

| 파일 | 설명 |
|------|------|
| `crawling_km_ScienceDirect.py` | 메인 크롤러 (PDF 대용량 다운로드, 저널+키워드) |
| `count_ScienceDirect.py` | 저널별 논문 수 / 페이지 수 사전 조회 |
| `count_results_ScienceDirect.txt` | `count_ScienceDirect.py` 실행 결과 |
| `Crawling_ScienceDirect.ipynb` | 참고용 프로토타입 노트북 (가천대 프록시 기반) |

---

## 대상 저널 (15개)

### Tier 1 — 핵심 원격탐사 저널

| # | 저널명 |
|---|--------|
| 1 | Remote Sensing of Environment |
| 2 | ISPRS Journal of Photogrammetry and Remote Sensing |
| 3 | International Journal of Applied Earth Observation and Geoinformation (JAG) |
| 4 | Advances in Space Research |

### Tier 2 — 영상처리 · 딥러닝

| # | 저널명 |
|---|--------|
| 5 | Information Fusion |
| 6 | Pattern Recognition |
| 7 | Neural Networks |
| 8 | Signal Processing |

### Tier 3 — 컴퓨터과학 응용

| # | 저널명 |
|---|--------|
| 9  | Neurocomputing |
| 10 | Expert Systems with Applications |
| 11 | Knowledge-Based Systems |
| 12 | Computers & Geosciences |
| 13 | Computer Vision and Image Understanding |
| 14 | Image and Vision Computing |
| 15 | The Egyptian Journal of Remote Sensing and Space Sciences |

---

## 크롤러 흐름

```
[Step 1] 국민대 도서관 로그인
  URL : https://lib.kookmin.ac.kr/login?...
  ID/PW : credentials.json 에서 로드

       ↓

[Step 2] 학술정보DB → ScienceDirect 링크 클릭
  URL : https://lib.kookmin.ac.kr/search/database?keyword=ScienceDirect
  Action : ScienceDirect/Elsevier 링크 클릭 → 새 창
           (자동으로 프록시 베이스 URL 발견)

       ↓

[Step 3-A] 저널별 검색 URL 이동 (기본 모드)
  형식 : {SD_PROXY_BASE}/search?pub={저널명}&articleTypes=FLA[&date={연도}]
  필터 : Full Length Article (FLA)

[Step 3-B] 키워드 검색 URL 이동 (--num-keywords 지정 시)
  형식 : {SD_PROXY_BASE}/search?qs={키워드}&articleTypes=FLA[&date={연도}]
  출처 : lists/list_words/word_list.txt 에서 상위 N개

       ↓

[Step 4] 페이지별 PDF 일괄 다운로드
  - #select-all-results 체크박스 → 전체 선택
  - 다운로드 버튼(.download-all-link-text) 클릭 → ZIP 저장
  - ZIP 압축 해제 후 PDF 이동 (이미 존재하는 파일은 자동 건너뜀)
  - 다음 페이지(a[data-aa-name='srp-next-page']) 이동 → 반복
```

---

## 빠른 시작

### 1. 의존성 설치

```bash
pip install selenium
```

### 2. 크리덴셜 설정 (`credentials.json`)

```json
{
  "univ_id": "학번",
  "univ_pw": "비밀번호"
}
```

### 3. 실행

```bash
# 헤드리스 모드, 2023년, 전체 저널
python crawling_km_ScienceDirect.py --headless --years 2023 --journal-option all

# 여러 연도
python crawling_km_ScienceDirect.py --headless --years 2022 2023 2024

# 연도 필터 없음 (전체)
python crawling_km_ScienceDirect.py --headless --years all

# Tier1 저널만 (4개)
python crawling_km_ScienceDirect.py --headless --years 2023 --journal-option 2

# 키워드 크롤링 — word_list.txt 상위 20개
python crawling_km_ScienceDirect.py --headless --years 2023 --num-keywords 20

# 키워드 크롤링 — 전체 키워드 (word_list.txt 전체)
python crawling_km_ScienceDirect.py --headless --years 2023 --num-keywords all

# 저널 + 키워드 함께 크롤링
python crawling_km_ScienceDirect.py --headless --years 2023 --journal-option 2 --num-keywords 50

# 키워드만 크롤링 (저널 건너뜀)
python crawling_km_ScienceDirect.py --headless --years 2023 --keywords-only --num-keywords 30

# 진행 상황 확인
python crawling_km_ScienceDirect.py --status --years 2023
```

---

## 옵션

| 옵션 | 설명 |
|------|------|
| `--headless` | 브라우저 창 없이 실행 (서버 환경) |
| `--years YEAR...` | 조회 연도 (예: `2022 2023 2024` 또는 `all`) |
| `--journal-option` | `1`=RSE만, `2`=Tier1(4개), `3`=Tier1+2(8개), `all`=전체(15개) |
| `--num-keywords N\|all` | 키워드 크롤링 활성화: `word_list.txt` 상위 N개 또는 `all` |
| `--word-list PATH` | 키워드 목록 파일 경로 (기본: `lists/list_words/word_list.txt`) |
| `--keywords-only` | 키워드 크롤링만 실행 (저널 크롤링 건너뜀) |
| `--resume` | 이전 중단 지점부터 재개 (저널·키워드 모두 적용) |
| `--status` | 현재 진행 현황 출력 후 종료 |
| `--save-path PATH` | PDF 저장 경로 (기본: `/nas1/.../02_ScienceDirect`) |
| `--username STR` | 도서관 로그인 ID |
| `--password STR` | 도서관 로그인 PW |

---

## 저장 경로

```
/nas1/hyperspectral_literature_data_collected/02_ScienceDirect/
└── {저널명}/
    └── {연도}/
        └── {논문}.pdf
```

로그 파일:
```
/nas1/hyperspectral_literature_data_collected/02_ScienceDirect_logs/
└── {연도}/
    └── crawl_sd_{연도}_{타임스탬프}.log
```

통계 CSV:
```
/nas1/hyperspectral_literature_data_collected/02_ScienceDirect_logs/manage_files/
└── stats_sd_{YYYY_MM}.csv
```

---

## 키워드 크롤링

`--num-keywords` 옵션을 사용하면 저널 필터 대신 **전문 키워드 검색**으로 PDF를 수집합니다.

```
{SD_PROXY_BASE}/search?qs={키워드}&articleTypes=FLA[&date={연도}]
```

### 키워드 목록 파일

```
lists/list_words/word_list.txt
```

한 줄에 키워드 하나, 179개 수록. `--num-keywords N`을 지정하면 **위에서부터 N개**만 사용합니다.

### 중복 제거

저널 크롤링과 키워드 크롤링 결과는 같은 `{year}/` 디렉토리에 저장됩니다.  
ZIP 내 PDF를 풀 때 이미 존재하는 파일명은 자동으로 건너뛰므로 중복 수집이 발생하지 않습니다.

### resume 지원

키워드 크롤링도 progress JSON에 기록됩니다 (키: `[KW] {키워드}`).  
`--resume` 플래그를 사용하면 중단된 키워드의 마지막 완료 페이지 다음부터 이어서 재개합니다.

---

## 사전 조회 스크립트 (`count_ScienceDirect.py`)

본격 크롤링 전에 각 저널의 총 논문 수와 페이지 수를 확인할 수 있습니다.

```bash
# 2023, 2024년 조회 (기본)
python count_ScienceDirect.py --headless

# 특정 연도
python count_ScienceDirect.py --headless --years 2023

# 전체 연도 합산
python count_ScienceDirect.py --headless --years all
```

결과는 `count_results_ScienceDirect.txt` 에 자동 저장됩니다.

---

## KIST 차단 페이지 처리

국민대 프록시 접속 시 간헐적으로 KIST 보안 경고 페이지  
(`kist.kookmin.ac.kr/kist_new/security/warning.do`) 가 나타날 수 있습니다.

크롤러는 이를 자동으로 감지하여:
1. 차단 창 닫기
2. 도서관 페이지로 복귀
3. 지정 시간 대기 (2분 → 5분) 후 재시도

재시도 후에도 차단이 해제되지 않으면 오류를 출력하고 종료합니다.  
이 경우 약 15–30분 후 다시 실행하거나,  
Chrome 프로필(`/data/khkim/chrome_tmp/.chrome_profile_sd`)을 수동으로 삭제하세요.

---

## 주의사항

- `credentials.json`은 `.gitignore`에 포함되어 있으며 커밋되지 않습니다.
- ScienceDirect는 페이지당 최대 20개 PDF를 ZIP으로 제공합니다.
- 다운로드 대기 시간은 기본 300초이며 네트워크 상태에 따라 조정하세요.
- 크롤링 중 세션 만료 시 자동으로 재로그인합니다.
