#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IEEE TGRS 논문 크롤링 (2023-2025)
국민대학교 성곡도서관 → 학술정보DB → IEEE Xplore

흐름:
  1. 도서관 로그인  https://lib.kookmin.ac.kr/login?...
  2. IEEE DB 페이지 이동  https://lib.kookmin.ac.kr/search/database?keyword=IEEE
  3. IEEE 링크 클릭 → 새 창으로 IEEE Xplore 프록시 열림
  4. IEEE Advanced Search → 연도·저널 필터 → 페이지별 PDF 다운로드

실행 예시:
  # GUI 모드 (브라우저 화면 표시, Windows/Linux 동일)
  python crawling_ieee_2023_2025.py --years 2023 2024 2025

  # Headless 모드 (서버 환경)
  python crawling_ieee_2023_2025.py --headless --years 2023 2024 2025

  # 단일 연도 + 저장 경로 지정
  python crawling_ieee_2023_2025.py --year 2024 --save-path /my/save/dir

  # credentials.json 대신 직접 입력
  python crawling_ieee_2023_2025.py --year 2023 --username myid --password mypw
"""

import os
import re
import sys
import json
import time
import random
import platform
import argparse
import warnings
import traceback
import zipfile
import csv
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

warnings.filterwarnings('ignore')


# ==================== 로거 (headless 전용) ====================
class TeeLogger:
    """stdout 출력을 콘솔과 로그 파일에 동시에 기록"""

    def __init__(self, log_path):
        self.terminal = sys.stdout
        self.log_file = open(log_path, 'a', encoding='utf-8', buffering=1)

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

    def close(self):
        self.log_file.close()


def setup_file_logger(save_base_path, year):
    """headless 실행 시 로그 디렉토리/파일 생성, TeeLogger 반환"""
    log_dir = Path(str(save_base_path) + '_logs') / str(year)
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = log_dir / f'crawl_{year}_{ts}.log'
    logger = TeeLogger(str(log_path))
    print(f'[LOG] 로그 파일: {log_path}')
    return logger


# ==================== 크롤링 통계 ====================
class CrawlStats:
    """저널별 크롤링 통계 추적 (CSV 저장용)"""
    CSV_COLUMNS = [
        'date', 'start_time', 'end_time', 'elapsed_minutes',
        'year_crawled', 'journal',
        'pages_processed', 'pages_skipped',
        'zip_downloads', 'pdfs_extracted', 'duplicates_skipped',
        'select_all_failures', 'download_failures', 'session_relogins',
    ]

    def __init__(self, year, journal):
        now = datetime.now()
        self.date            = now.strftime('%Y-%m-%d')
        self.start_time      = now.strftime('%H:%M:%S')
        self.end_time        = ''
        self.elapsed_minutes = 0.0
        self._start_dt       = now
        self.year_crawled    = int(year)
        self.journal         = journal
        self.pages_processed    = 0
        self.pages_skipped      = 0
        self.zip_downloads      = 0
        self.pdfs_extracted     = 0
        self.duplicates_skipped = 0
        self.select_all_failures  = 0
        self.download_failures    = 0
        self.session_relogins     = 0

    def finalize(self):
        now = datetime.now()
        self.end_time        = now.strftime('%H:%M:%S')
        self.elapsed_minutes = round((now - self._start_dt).total_seconds() / 60, 2)

    def as_row(self):
        # 실시간 호출 시 현재 시각 기준으로 경과 시간 계산
        now = datetime.now()
        end_t   = self.end_time or now.strftime('%H:%M:%S')
        elapsed = self.elapsed_minutes if self.elapsed_minutes else \
                  round((now - self._start_dt).total_seconds() / 60, 2)
        return {
            'date':               self.date,
            'start_time':         self.start_time,
            'end_time':           end_t,
            'elapsed_minutes':    elapsed,
            'year_crawled':       self.year_crawled,
            'journal':            self.journal,
            'pages_processed':    self.pages_processed,
            'pages_skipped':      self.pages_skipped,
            'zip_downloads':      self.zip_downloads,
            'pdfs_extracted':     self.pdfs_extracted,
            'duplicates_skipped': self.duplicates_skipped,
            'select_all_failures':  self.select_all_failures,
            'download_failures':    self.download_failures,
            'session_relogins':     self.session_relogins,
        }

    def checkpoint(self):
        """현재 통계를 CSV에 즉시 반영 (upsert).

        (date, start_time, year_crawled, journal) 으로 행을 식별해
        이미 있으면 업데이트, 없으면 추가한다.
        zip 1건 처리 후마다 호출해 실시간으로 파일을 갱신할 수 있다.
        """
        try:
            MANAGE_FILES_PATH.mkdir(parents=True, exist_ok=True)
            ym = datetime.now().strftime('%Y_%m')
            csv_path = MANAGE_FILES_PATH / f'stats_{ym}.csv'

            session_key = (self.date, self.start_time,
                           str(self.year_crawled), self.journal)
            rows = []
            found = False

            if csv_path.exists():
                with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        key = (row.get('date', ''), row.get('start_time', ''),
                               row.get('year_crawled', ''), row.get('journal', ''))
                        if key == session_key:
                            rows.append(self.as_row())
                            found = True
                        else:
                            rows.append(row)

            if not found:
                rows.append(self.as_row())

            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=CrawlStats.CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)

        except Exception as e:
            print(f'[경고] 통계 CSV 업데이트 실패: {e}')


def write_stats_row(stats: CrawlStats):
    """저널 완료 시 최종 통계를 CSV에 반영 (checkpoint 의 alias)."""
    stats.checkpoint()
    print(f'[STATS] stats_{datetime.now().strftime("%Y_%m")}.csv 최종 저장 완료')


# ==================== 진행 상황 추적 (resume 지원) ====================
class ProgressTracker:
    """크롤링 진행 상황을 JSON 파일로 추적하며 --resume 재개를 지원한다.

    파일 위치: {save_base}_logs/manage_files/progress_{year}.json

    구조 예시::

        {
          "IEEE GRSL": {
            "search_term": "Geoscience and Remote Sensing Letters",
            "status": "completed",          # in_progress | completed
            "last_page_completed": 44,
            "total_pages_found": 44,
            "pdfs_downloaded": 440,
            "started_at": "2026-04-06 11:27:03",
            "last_updated": "2026-04-06 18:45:22"
          }
        }

    --resume 동작 방식:
    - completed 저널: last_page + 1 부터 체크 (신규 논문 존재 여부 확인)
    - in_progress 저널: last_page_completed + 1 부터 재개
    - 미기록 저널: 1 페이지부터 시작
    """

    def __init__(self, save_base_path, year):
        self.year = str(year)
        progress_dir = MANAGE_FILES_PATH
        progress_dir.mkdir(parents=True, exist_ok=True)
        self.path = progress_dir / f'progress_{year}.json'
        self.data = self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self):
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f'[경고] 진행 상황 저장 실패: {e}')

    def get_start_page(self, journal_label: str, resume: bool) -> int:
        """재개 시 시작 페이지 번호를 반환한다."""
        if not resume or journal_label not in self.data:
            return 1
        entry = self.data[journal_label]
        status   = entry.get('status', 'not_started')
        last_pg  = entry.get('last_page_completed', 0)
        if status == 'completed':
            start = last_pg + 1
            print(f'[RESUME] {journal_label[:40]}: 완료 기록 있음 → 신규 논문 체크 (p.{start}~)')
            return start
        elif status == 'in_progress':
            start = max(1, last_pg + 1)
            print(f'[RESUME] {journal_label[:40]}: 진행 중 → p.{start} 부터 재개')
            return start
        return 1

    def update(self, journal_label: str, search_term: str,
               page_num: int, pdfs_downloaded: int, status: str = 'in_progress'):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if journal_label not in self.data:
            self.data[journal_label] = {'search_term': search_term, 'started_at': now}
        self.data[journal_label].update({
            'status':               status,
            'last_page_completed':  page_num,
            'pdfs_downloaded':      pdfs_downloaded,
            'last_updated':         now,
        })
        self.save()

    def mark_completed(self, journal_label: str, total_pages: int, total_pdfs: int):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry = self.data.setdefault(journal_label, {})
        entry.update({
            'status':              'completed',
            'last_page_completed': total_pages,
            'total_pages_found':   total_pages,
            'total_pdfs':          total_pdfs,
            'completed_at':        now,
            'last_updated':        now,
        })
        self.save()

    def show_summary(self, journal_targets=None):
        """진행 상황 요약을 출력한다."""
        targets = journal_targets or JOURNAL_TARGETS
        total   = len(targets)
        completed   = sum(1 for v in self.data.values() if v.get('status') == 'completed')
        in_progress = sum(1 for v in self.data.values() if v.get('status') == 'in_progress')
        not_started = total - len(self.data)
        print(f'\n[진행 상황] {self.path.name}')
        print(f'  전체 저널 {total}개 | 완료 {completed} | 진행중 {in_progress} | 미시작 {not_started}')
        for label, info in self.data.items():
            st   = info.get('status', '?')
            pg   = info.get('last_page_completed', 0)
            pdfs = info.get('pdfs_downloaded', 0)
            upd  = info.get('last_updated', '')[:16]
            print(f'  {st:12s} | p.{pg:4d} | {pdfs:6d} PDFs | {upd} | {label[:45]}')
        print()


# ==================== 기본 저장 경로 ====================
DEFAULT_SAVE_PATH_LINUX   = '/nas1/hyperspectral_literature_data_collected/01_IEEE_TGRS_1980_2025'
DEFAULT_SAVE_PATH_WINDOWS = os.path.join(os.path.expanduser('~'), 'Downloads', 'IEEE_TGRS')

# ==================== 국민대 도서관 URL / Selector ====================
LOGIN_URL     = 'https://lib.kookmin.ac.kr/login?returnUrl=%3F&queryParamsHandling=merge'
DB_SEARCH_URL = 'https://lib.kookmin.ac.kr/search/database?keyword=IEEE'

# mat-input ID는 Angular가 동적으로 부여 → formcontrolname 속성으로 대신 찾음
CSS_ID_FIELD   = 'input[formcontrolname="portalUserId"]'
CSS_PW_FIELD   = 'input[formcontrolname="portalPassword"]'
XPATH_LOGIN_BTN = '//button[@type="submit" and normalize-space(.)="로그인"]'
# IEEE 링크: 텍스트에 "IEL" 또는 "IEEE"가 포함된 a 태그 (XPath는 렌더링 환경에 따라 변함)
XPATH_IEEE_LINK = '//a[contains(text(), "IEL") or (contains(text(), "IEEE") and string-length(text()) > 5)]'

IEEE_PROXY_HOME   = 'https://ieeexplore-ieee-org-ssl.proxy.kookmin.ac.kr/Xplore/home.jsp'

# ==================== 통계 CSV 저장 경로 ====================
MANAGE_FILES_PATH = Path('/nas1/hyperspectral_literature_data_collected/01_IEEE_TGRS_1980_2025_logs/manage_files')

# ==================== 대상 저널/학회 목록 (초분광 관련도 순위 정렬, 50개) ====================
# 형식: (Publication Title 필터 검색어, 클릭할 레이블 일치 텍스트)
# 초분광(HSI)·원격탐사(RS) 관련도 기준으로 50개 저널을 Tier 1~10 순위 정렬
# --num-journals 10|15|20|25|30|35|40|45|50 옵션으로 상위 N개 사용 (기본 30개)
JOURNAL_TARGETS_ALL = [
    # ── Tier 1 (1~10): 초분광·원격탐사 핵심 저널 ──────────────────────────
    ("Transactions on Geoscience and Remote Sensing",   "IEEE Transactions on Geoscience and Remote Sensing"),
    ("Geoscience and Remote Sensing Letters",           "IEEE Geoscience and Remote Sensing Letters"),
    ("Selected Topics in Applied Earth",                "IEEE Journal of Selected Topics in Applied Earth Observations"),
    ("Sensors Journal",                                 "IEEE Sensors Journal"),
    ("IEEE Access",                                     "IEEE Access"),
    ("IGARSS",                                          "IGARSS"),
    ("Transactions on Image Processing",                "IEEE Transactions on Image Processing"),
    ("Transactions on Pattern Analysis",                "IEEE Transactions on Pattern Analysis and Machine Intelligence"),
    ("Neural Networks and Learning",                    "IEEE Transactions on Neural Networks and Learning Systems"),
    ("Geoscience and Remote Sensing Magazine",          "IEEE Geoscience and Remote Sensing Magazine"),
    # ── Tier 2 (11~15): 신호 처리·계산 영상 ──────────────────────────────
    ("Selected Topics in Signal Processing",            "IEEE Journal of Selected Topics in Signal Processing"),
    ("Transactions on Signal Processing",               "IEEE Transactions on Signal Processing"),
    ("Transactions on Computational Imaging",           "IEEE Transactions on Computational Imaging"),
    ("Photonics Journal",                               "IEEE Photonics Journal"),
    ("International Conference on Image Processing",    "IEEE International Conference on Image Processing"),
    # ── Tier 3 (16~20): 항공우주·측정·컴퓨터 비전 학회 ──────────────────────
    ("Aerospace and Electronic Systems",                "IEEE Transactions on Aerospace and Electronic Systems"),
    ("Transactions on Multimedia",                      "IEEE Transactions on Multimedia"),
    ("CVPR",                                            "IEEE/CVF Conference on Computer Vision and Pattern Recognition"),
    ("ICCV",                                            "IEEE/CVF International Conference on Computer Vision"),
    ("Instrumentation and Measurement",                 "IEEE Transactions on Instrumentation and Measurement"),
    # ── Tier 4 (21~25): 영상 처리·의료·산업 저널 ─────────────────────────
    ("Circuits and Systems for Video",                  "IEEE Transactions on Circuits and Systems for Video Technology"),
    ("Proceedings of the IEEE",                         "Proceedings of the IEEE"),
    ("Signal Processing Letters",                       "IEEE Signal Processing Letters"),
    ("Transactions on Medical Imaging",                 "IEEE Transactions on Medical Imaging"),
    ("Transactions on Industrial Electronics",          "IEEE Transactions on Industrial Electronics"),
    # ── Tier 5 (26~30): AI·로보틱스·광학 ──────────────────────────────────
    ("Transactions on Cybernetics",                     "IEEE Transactions on Cybernetics"),
    ("Transactions on Artificial Intelligence",         "IEEE Transactions on Artificial Intelligence"),
    ("Transactions on Emerging Topics in Computational","IEEE Transactions on Emerging Topics in Computational Intelligence"),
    ("Photonics Technology Letters",                    "IEEE Photonics Technology Letters"),
    ("Robotics and Automation Letters",                 "IEEE Robotics and Automation Letters"),
    # ── Tier 6 (31~35): 학회·오픈 저널 ────────────────────────────────────
    ("ICASSP",                                          "ICASSP"),
    ("International Geoscience",                        "International Geoscience and Remote Sensing Symposium"),
    ("Transactions on Big Data",                        "IEEE Transactions on Big Data"),
    ("Winter Conference on Applications of Computer",   "IEEE Winter Conference on Applications of Computer Vision"),
    ("Systems Journal",                                 "IEEE Systems Journal"),
    # ── Tier 7 (36~40): 해양·지속가능·광통신·산업 저널 ─────────────────────
    ("Journal of Oceanic Engineering",                  "IEEE Journal of Oceanic Engineering"),
    ("Transactions on Sustainable Energy",              "IEEE Transactions on Sustainable Energy"),
    ("Journal of Lightwave Technology",                 "Journal of Lightwave Technology"),
    ("Transactions on Industrial Informatics",          "IEEE Transactions on Industrial Informatics"),
    ("Open Journal of Signal",                          "IEEE Open Journal of Signal and Information Processing"),
    # ── Tier 8 (41~45): 방송·메카트로닉스·신호처리 매거진 ─────────────────
    ("Signal Processing Magazine",                      "IEEE Signal Processing Magazine"),
    ("Aerospace Conference",                            "IEEE Aerospace Conference"),
    ("Transactions on Broadcasting",                    "IEEE Transactions on Broadcasting"),
    ("Mechatronics",                                    "IEEE/ASME Transactions on Mechatronics"),
    ("Machine Learning for Signal Processing",          "IEEE International Workshop on Machine Learning for Signal Processing"),
    # ── Tier 9 (46~50): 추가 확장 커버리지 ──────────────────────────────────
    ("Transactions on Radiation and Plasma",            "IEEE Transactions on Radiation and Plasma Medical Sciences"),
    ("Transactions on Smart Grid",                      "IEEE Transactions on Smart Grid"),
    ("Transactions on Antennas and Propagation",        "IEEE Transactions on Antennas and Propagation"),
    ("Transactions on Microwave Theory",                "IEEE Transactions on Microwave Theory and Techniques"),
    ("Latin America Transactions",                      "IEEE Latin America Transactions"),
]

# 하위 호환성을 위한 기본 저널 리스트 (상위 30개, --num-journals 기본값)
JOURNAL_TARGETS = JOURNAL_TARGETS_ALL[:30]

# ==================== 저널 선택 옵션 (--journal-option) ====================
# --journal-option 1 : Publication Title 검색창에 "Remote Sensing" 입력 → 나오는 항목 전체 체크
# --journal-option 2 : 아래 JOURNAL_OPTION2_FIXED 4개 저널을 일괄 체크
# --journal-option 3 : 검색 없이 Publication Title 상위 5개 체크
# --journal-option 4 : 검색 없이 Publication Title 상위 10개 체크
#
# {year} 는 크롤링 연도로 자동 치환됨 (예: "IGARSS {year}" → "IGARSS 2024")
JOURNAL_OPTION2_FIXED = [
    ("IEEE Access",                                         "IEEE Access"),
    ("IEEE Sensors Journal",                                "IEEE Sensors Journal"),
    ("IGARSS {year}",                                       "IGARSS {year}"),
    ("Transactions on Geoscience and Remote Sensing",       "IEEE Transactions on Geoscience and Remote Sensing"),
]

# ==================== 키워드 기반 검색 목록 (--with-keywords / --keywords-only 옵션용) ====================
# IEEE Xplore 전체에서 키워드로 검색 → 저널 필터 없이 관련 논문 대량 수집
# 초분광·원격탐사 관련 50개 키워드 (저널 목록에 없는 저널의 논문도 포함)
KEYWORD_SEARCH_TERMS = [
    # ── 초분광 핵심 ──────────────────────────────────────────────────────
    "hyperspectral imaging",
    "hyperspectral remote sensing",
    "hyperspectral image classification",
    "hyperspectral image analysis",
    "hyperspectral unmixing",
    "hyperspectral anomaly detection",
    "hyperspectral target detection",
    "hyperspectral band selection",
    "hyperspectral feature extraction",
    # ── 다분광·스펙트럼 ───────────────────────────────────────────────────
    "multispectral imaging",
    "spectral imaging",
    "spectral analysis remote sensing",
    "spectral unmixing",
    "spectral super resolution",
    # ── 위성·항공·드론 원격탐사 ──────────────────────────────────────────
    "remote sensing image classification",
    "satellite image analysis",
    "aerial image analysis",
    "UAV remote sensing",
    "drone remote sensing",
    # ── SAR / 레이더 ──────────────────────────────────────────────────────
    "SAR image processing",
    "synthetic aperture radar remote sensing",
    "PolSAR classification",
    "InSAR deformation",
    "SAR change detection",
    # ── LiDAR / 3D 포인트클라우드 ────────────────────────────────────────
    "LiDAR remote sensing",
    "point cloud classification",
    "3D point cloud deep learning",
    # ── 딥러닝 방법론 (원격탐사 적용) ─────────────────────────────────────
    "deep learning remote sensing",
    "convolutional neural network remote sensing",
    "transformer remote sensing",
    "attention mechanism remote sensing",
    "generative adversarial network remote sensing",
    "self-supervised learning remote sensing",
    # ── 토지·환경 응용 ────────────────────────────────────────────────────
    "land cover classification remote sensing",
    "land use change detection",
    "vegetation mapping remote sensing",
    "crop monitoring remote sensing",
    "precision agriculture remote sensing",
    "forest monitoring remote sensing",
    # ── 도시·재해 응용 ────────────────────────────────────────────────────
    "urban remote sensing",
    "building extraction remote sensing",
    "road extraction remote sensing",
    "flood detection remote sensing",
    "wildfire detection satellite",
    "change detection satellite imagery",
    # ── 해양·빙설·토양 응용 ──────────────────────────────────────────────
    "ocean remote sensing",
    "sea ice remote sensing",
    "snow cover remote sensing",
    "soil moisture estimation remote sensing",
    # ── 의료·광학 응용 ────────────────────────────────────────────────────
    "medical hyperspectral imaging",
    "mineral mapping hyperspectral",
    "image fusion remote sensing",
    "pansharpening satellite",
    "super resolution remote sensing",
]


# ==================== 크롤링 설정 ====================
class CrawlConfig:
    def __init__(self, year, save_base_path):
        self.YEAR      = str(year)
        self.BASE_PATH = os.path.expandvars(save_base_path)
        self.SAVE_PATH = os.path.join(self.BASE_PATH, self.YEAR)

        self.TARGET_JOURNAL = "IEEE Transactions on Geoscience and Remote Sensing"
        self.START_PAGE     = 1

        self.DOWNLOAD_WAIT_SECONDS   = 300   # PDF 다운로드 최대 대기 (5분)
        self.PAGE_CHANGE_DELAY       = 5     # 페이지 이동 후 대기
        self.SEAT_LIMIT_WAIT_SECONDS = 300   # Seat Limit 시 대기 (5분)

        self.MIN_RANDOM_DELAY       = 3
        self.MAX_RANDOM_DELAY       = 8
        self.MAX_PAGE_VISITS        = 9999   # 사실상 무제한 (전체 페이지 다운)
        self.MAX_SEAT_LIMIT_RETRIES = 5
        self.MAX_PAGE_RETRIES            = 3   # 페이지 연속 실패 시 건너뜀 한계
        self.MAX_CONSECUTIVE_PAGE_FAILS  = 3   # 연속 N페이지 전체 실패 → 저널/키워드 크롤링 중단

        Path(self.SAVE_PATH).mkdir(parents=True, exist_ok=True)
        print(f"[저장 경로] {self.SAVE_PATH}")


# Linux 서버에 Chrome 145 수동 설치 경로 (환경변수로 오버라이드 가능)
CHROME_BIN_LINUX      = '/data/khkim/chrome_local/chrome_extracted/opt/google/chrome/google-chrome'
CHROMEDRIVER_BIN_LINUX = '/data/khkim/chrome_local/chromedriver-linux64/chromedriver'


# ==================== Chrome 드라이버 설정 ====================
def setup_chrome_driver(download_dir, headless=False):
    """Chrome 드라이버 초기화

    headless=False : 브라우저 창을 직접 보며 진행 상황 확인 가능 (기본)
    headless=True  : 서버 환경 (화면 없이 백그라운드 실행)
    """
    options = Options()

    # Chrome 임시 프로필 디렉토리를 /tmp 대신 명시적 경로로 지정
    # (서버에서 /tmp 가득 찼거나 권한 문제 시 "cannot create temp dir" 에러 방지)
    chrome_tmp_dir = Path(download_dir).parent / '.chrome_profile'
    chrome_tmp_dir.mkdir(parents=True, exist_ok=True)

    # TMPDIR을 /tmp 대신 로컬 경로로 오버라이드
    # Chrome은 --disable-extensions 설정과 무관하게 내부적으로 TMPDIR을 사용함
    # /tmp가 가득 찼거나 권한 문제 시 "cannot create temp dir for unpacking extensions" 에러 발생
    chrome_local_tmp = Path('/data/khkim/chrome_tmp')
    chrome_local_tmp.mkdir(parents=True, exist_ok=True)
    os.environ['TMPDIR'] = str(chrome_local_tmp)
    # 이전 실행에서 남겨진 SingletonLock 제거 (없으면 다음 Chrome 기동이 "already in use"로 실패)
    for lock in ['SingletonLock', 'SingletonCookie', 'SingletonSocket']:
        lock_path = chrome_tmp_dir / lock
        if lock_path.exists():
            try:
                lock_path.unlink()
            except Exception:
                pass
    options.add_argument(f'--user-data-dir={chrome_tmp_dir}')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-extensions')        # extension 언팩 시 /tmp 사용 방지
    options.add_argument('--disable-plugins')

    if headless:
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
    else:
        options.add_argument('--start-maximized')

    # 공통 - 봇 감지 차단
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1920,1080')
    options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36'
    )
    options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
    options.add_experimental_option('useAutomationExtension', False)

    # 다운로드 설정
    prefs = {
        'download.default_directory':                             download_dir,
        'download.prompt_for_download':                           False,
        'download.directory_upgrade':                             True,
        'safebrowsing.enabled':                                   True,
        'plugins.always_open_pdf_externally':                     True,
        # 복수 파일 동시 다운로드 허용 (팝업 차단)
        'profile.default_content_setting_values.automatic_downloads': 1,
    }
    options.add_experimental_option('prefs', prefs)
    options.page_load_strategy = 'normal'

    try:
        # Chrome 바이너리 / ChromeDriver 경로 결정
        # 우선순위: 환경변수 > Linux 서버 수동 설치 경로 > 시스템 PATH
        chrome_bin    = os.environ.get('CHROME_BINARY', '')
        chromedriver  = os.environ.get('CHROMEDRIVER_PATH', '')

        if not chrome_bin and Path(CHROME_BIN_LINUX).exists():
            chrome_bin = CHROME_BIN_LINUX
        if not chromedriver and Path(CHROMEDRIVER_BIN_LINUX).exists():
            chromedriver = CHROMEDRIVER_BIN_LINUX

        if chrome_bin:
            options.binary_location = chrome_bin
            print(f'[ChromeDriver] Chrome 바이너리: {chrome_bin}')

        if chromedriver:
            service = Service(chromedriver)
            print(f'[ChromeDriver] ChromeDriver: {chromedriver}')
        else:
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                print('[ChromeDriver] webdriver-manager 로 자동 관리')
            except ImportError:
                service = Service()
                print('[ChromeDriver] 시스템 PATH의 chromedriver 사용')

        driver = webdriver.Chrome(service=service, options=options)
        # navigator.webdriver 속성 숨기기 (프록시 봇 감지 차단)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
        driver.set_page_load_timeout(60)
        mode_str = 'headless' if headless else 'GUI'
        print(f'[Chrome] 드라이버 초기화 완료 ({mode_str})')
        return driver

    except Exception as e:
        print(f'[오류] Chrome 드라이버 초기화 실패: {e}')
        print('  → Chrome 브라우저가 설치되어 있는지 확인하세요.')
        print("  → pip install webdriver-manager  으로 자동 설치를 시도하세요.")
        sys.exit(1)


# ==================== 유틸 ====================
def random_delay(min_sec=3, max_sec=8):
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)
    return delay


def check_seat_limit(driver):
    try:
        text = driver.page_source.lower()
        return any(kw in text for kw in
                   ['seat limit', 'maximum number of users', 'too many users', 'access denied'])
    except:
        return False


def is_session_expired(driver):
    """프록시 세션 만료 여부 확인 (kookmin.ac.kr 세션 오류 페이지 감지)."""
    try:
        url = driver.current_url
        return 'sessionfail' in url or 'exceptproc' in url
    except:
        return False


def has_search_results(driver):
    """현재 페이지에 검색 결과가 있는지 확인.

    빈 페이지(마지막 페이지를 초과한 경우 등)를 감지해 False 를 반환한다.
    크롤링 루프에서 이 함수가 False 를 반환하면 해당 저널 크롤링을 종료한다.
    """
    try:
        time.sleep(3)

        # ── 결과 항목 요소 확인 ──────────────────────────────────────────
        result_selectors = [
            'xpl-result-item',
            '.List-results-items li',
            '.result-item',
            '[class*="result-item"]',
        ]
        for sel in result_selectors:
            items = driver.find_elements(By.CSS_SELECTOR, sel)
            if len(items) > 0:
                return True

        # ── "No results" 텍스트 패턴 ──────────────────────────────────────
        src_lower = driver.page_source.lower()
        no_result_phrases = [
            'no results found', '0 results', 'returned no results',
            'did not match any', 'we could not find', 'no documents found',
        ]
        if any(p in src_lower for p in no_result_phrases):
            print('[감지] 검색 결과 0건 텍스트 발견 → 저널 마지막 페이지 초과')
            return False

        # ── 결과 헤더에서 숫자 확인 ──────────────────────────────────────
        header_selectors = [
            '.Dashboard-header',
            '.results-count',
            'span.ng-star-inserted',
            '[class*="results-header"]',
        ]
        for sel in header_selectors:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                txt = el.text.strip()
                if txt and ('result' in txt.lower() or ' of ' in txt.lower()):
                    if re.search(r'\b0\b', txt):
                        print(f'[감지] 결과 0건 헤더 발견: "{txt}" → 저널 마지막 페이지 초과')
                        return False
                    return True

        # 결과 항목도 없고 헤더도 확인 안 됨 → 빈 페이지로 판단
        print('[감지] 결과 아이템·헤더 미발견 → 빈 페이지 (저널 마지막 페이지 초과)')
        return False

    except Exception as e:
        print(f'[경고] 결과 존재 확인 실패 ({e}) → 결과 있다고 가정')
        return True


# ==================== 1단계: 국민대 도서관 로그인 ====================
def login_kookmin_library(driver, username, password):
    print('\n' + '='*60)
    print('1단계: 국민대 성곡도서관 로그인')
    print('='*60)

    try:
        driver.get(LOGIN_URL)
        time.sleep(5)

        # ID 입력 (formcontrolname 기반 - mat-input ID는 동적으로 변함)
        id_field = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, CSS_ID_FIELD))
        )
        id_field.clear()
        id_field.send_keys(username)
        print(f'[OK] ID 입력: {username}')
        time.sleep(0.5)

        # 비밀번호 입력
        pw_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, CSS_PW_FIELD))
        )
        pw_field.clear()
        pw_field.send_keys(password)
        print('[OK] 비밀번호 입력')
        time.sleep(0.5)

        # 로그인 버튼 클릭
        login_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, XPATH_LOGIN_BTN))
        )
        login_btn.click()
        print('[OK] 로그인 버튼 클릭')
        time.sleep(4)

        print(f'[OK] 로그인 완료  현재 URL: {driver.current_url}\n')
        return True

    except Exception as e:
        print(f'[오류] 로그인 실패: {e}')
        return False


# ==================== 2단계: IEEE 접속 (새 창 전환) ====================
def access_ieee_via_library(driver):
    print('='*60)
    print('2단계: 학술정보DB → IEEE Xplore 접속')
    print('='*60)

    try:
        driver.get(DB_SEARCH_URL)
        # Angular SSG 렌더링 대기 (최대 20초 폴링)
        ieee_link = None
        for _ in range(20):
            time.sleep(1)
            for lnk in driver.find_elements(By.TAG_NAME, 'a'):
                t = lnk.text.strip()
                if 'IEL' in t or ('IEEE' in t and len(t) > 10):
                    ieee_link = lnk
                    break
            if ieee_link:
                break

        if not ieee_link:
            raise Exception('IEEE 링크를 찾을 수 없음 (20초 대기 후)')

        print(f'[OK] IEEE 링크 발견: {ieee_link.text[:60]}')
        original_handles = set(driver.window_handles)
        driver.execute_script('arguments[0].click();', ieee_link)  # JS 클릭 (Angular 라우터 호환)
        print('[OK] IEEE 링크 클릭 → 새 창 대기 중...')

        # 새 창이 열릴 때까지 대기 (최대 15초)
        WebDriverWait(driver, 15).until(
            lambda d: len(d.window_handles) > len(original_handles)
        )

        # 새 창으로 전환
        new_handle = (set(driver.window_handles) - original_handles).pop()
        driver.switch_to.window(new_handle)
        # 프록시 세션 확립 + IEEE Xplore 렌더링 대기 (15초 필요)
        time.sleep(15)

        print(f'[OK] IEEE Xplore 창으로 전환 완료')

        if 'Kookmin University' in driver.page_source or 'Access provided by' in driver.page_source:
            print('[OK] 국민대 프록시 인증 확인됨')
        else:
            print('[경고] 프록시 인증 미확인 (계속 진행)')

        print(f'현재 URL: {driver.current_url}\n')
        return True

    except Exception as e:
        print(f'[오류] IEEE 접속 실패: {e}')
        # 폴백: 프록시 URL 직접 접속
        try:
            print('[폴백] IEEE 프록시 URL 직접 접속 시도')
            driver.get(IEEE_PROXY_HOME)
            time.sleep(5)
            return True
        except:
            return False


# ==================== 3단계: Advanced Search ====================
def setup_ieee_advanced_search(driver, year):
    """IEEE Xplore Advanced Search 설정.

    year='all' 이면 연도 필터를 적용하지 않고 전체 연도 검색.
    """
    year_str = str(year)
    print('='*60)
    print(f'3단계: {"전체 연도" if year_str == "all" else year_str + "년"} Advanced Search 설정')
    print('='*60)

    try:
        current_url = driver.current_url
        base_url = (
            current_url.split('/Xplore')[0]
            if '/Xplore' in current_url
            else 'https://ieeexplore-ieee-org-ssl.proxy.kookmin.ac.kr'
        )
        search_url = f'{base_url}/search/advanced'

        print(f'Advanced Search: {search_url}')
        driver.get(search_url)
        time.sleep(5)
        driver.refresh()
        time.sleep(5)

        # ── year='all': 연도 필터 없이 검색 버튼만 클릭 ─────────────────
        if year_str == 'all':
            try:
                search_button = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "button.stats-Adv_search, button.xpl-btn-primary")
                    )
                )
                driver.execute_script('arguments[0].click();', search_button)
                print('[OK] 연도 필터 없이 검색 실행 (전체 연도)')
                time.sleep(10)
            except Exception:
                # 폴백: 연도 파라미터 없는 검색결과 URL 직접 이동
                fallback_url = f'{base_url}/search/searchresult.jsp?action=search&newsearch=true'
                print(f'[폴백] 전체연도 URL 직접 이동: {fallback_url}')
                driver.get(fallback_url)
                time.sleep(10)
            print(f'현재 URL: {driver.current_url}\n')
            return True

        # Year Range 라디오 버튼 클릭 (날짜범위 대신 연도범위 선택)
        try:
            year_radio = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='range'][id='id_1']"))
            )
            driver.execute_script('arguments[0].click();', year_radio)
            print('[OK] Year Range 라디오 선택')
            time.sleep(1)
        except Exception:
            print('[경고] Year Range 라디오 못 찾음 (계속 진행)')

        # Start/End Year 입력 (aria-label 기반)
        start_year_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR,
                 "input[aria-label*='start year'], input[aria-label*='Start Year'], "
                 "input[placeholder*='Start Year'], input[name*='startYear']")
            )
        )
        start_year_field.clear()
        start_year_field.send_keys(str(year))
        print(f'[OK] 시작 연도: {year}')
        time.sleep(0.5)

        end_year_field = driver.find_element(
            By.CSS_SELECTOR,
            "input[aria-label*='end year'], input[aria-label*='End Year'], "
            "input[placeholder*='End Year'], input[name*='endYear']"
        )
        end_year_field.clear()
        end_year_field.send_keys(str(year))
        print(f'[OK] 종료 연도: {year}')
        time.sleep(0.5)

        # Advanced Search 전용 버튼 (stats-Adv_search 클래스)
        # JS 클릭 사용 - Osano 쿠키 팝업 등 오버레이가 가로막는 경우 대비
        search_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "button.stats-Adv_search, button.xpl-btn-primary")
            )
        )
        driver.execute_script('arguments[0].click();', search_button)
        print('[OK] 검색 실행')
        # 검색 결과 로딩 대기
        time.sleep(10)

        print(f'현재 URL: {driver.current_url}\n')
        return True

    except Exception as e:
        print(f'[오류] Advanced Search 폼 실패: {e}')
        # 폴백: 연도 파라미터 포함 검색결과 URL 직접 이동
        try:
            cur = driver.current_url
            base = cur.split('/search')[0] if '/search' in cur else \
                   cur.split('/Xplore')[0] if '/Xplore' in cur else \
                   'https://ieeexplore-ieee-org-ssl.proxy.kookmin.ac.kr'
            ranges_param = (f'&ranges={year}_{year}_Year' if str(year) != 'all' else '')
            fallback_url = (f'{base}/search/searchresult.jsp'
                            f'?action=search&newsearch=true{ranges_param}')
            print(f'[폴백] URL 직접 이동: {fallback_url}')
            driver.get(fallback_url)
            time.sleep(10)
            print(f'[폴백] 현재 URL: {driver.current_url}')
            return True
        except Exception as e2:
            print(f'[오류] Advanced Search 폴백도 실패: {e2}')
            return False


# ==================== 4단계: Publication 필터 ====================
def apply_publication_filter(driver, search_term, label_match=None):
    """Publication Title 필터 적용.

    search_term : 필터 검색창에 입력할 텍스트 (예: "Geoscience and Remote Sensing")
    label_match : 클릭할 레이블에서 일치시킬 텍스트 (None이면 search_term 사용)
    """
    match_text = label_match or search_term
    print(f'4단계: 저널 필터 적용 - {match_text}')

    try:
        # "Publication Title" 섹션 토글 버튼 찾기 (접혀 있으면 펼침)
        pub_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//button[normalize-space(.)='Publication Title']")
            )
        )
        # 이미 펼쳐져 있지 않으면 클릭
        aria_exp = pub_btn.get_attribute('aria-expanded')
        if aria_exp != 'true':
            driver.execute_script('arguments[0].click();', pub_btn)
            time.sleep(2)
            print('[OK] Publication Title 섹션 펼침')

        # 섹션 내 검색 입력창
        search_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH,
                 "//button[normalize-space(.)='Publication Title']"
                 "/../../following-sibling::*//input[@placeholder='Enter Title' or @placeholder='Enter title']")
            )
        )
        search_input.clear()
        search_input.send_keys(search_term)
        time.sleep(4)  # 자동완성 결과 로딩 대기

        # 해당 저널 체크박스 레이블 클릭 (match_text를 포함하는 레이블)
        # match_text가 너무 길면 앞 40자만 사용
        match_substr = match_text[:40] if len(match_text) > 40 else match_text
        label = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH,
                 f"//label[contains(normalize-space(), '{match_substr}')]")
            )
        )
        driver.execute_script('arguments[0].click();', label)
        print('[OK] 저널 선택: ' + label.text[:60])
        time.sleep(2)

        # Apply 버튼 클릭 (displayed=True, enabled=True인 것 선택)
        apply_btn = WebDriverWait(driver, 10).until(
            lambda d: next(
                (b for b in d.find_elements(By.CSS_SELECTOR, "button.stats-applyRefinements-button")
                 if b.is_displayed() and b.is_enabled()),
                None
            )
        )
        driver.execute_script('arguments[0].click();', apply_btn)
        print('[OK] Apply 클릭 → 저널 필터 적용 완료')
        time.sleep(8)  # 필터 결과 로딩 대기
        return True

    except Exception as e:
        print(f'[경고] 저널 필터 적용 실패 (계속 진행): {e}')
        return False


# ==================== 4단계: Publication 필터 (다중 선택, --journal-option 전용) ====================
def apply_publication_filter_multi(driver, option, year):
    """Publication Title 필터 다중 선택 후 Apply.  --journal-option 1~4 전용.

    option 1 : 검색창에 "Remote Sensing" 입력 → 나타나는 항목 모두 체크 → Apply
    option 2 : JOURNAL_OPTION2_FIXED 의 4개 저널을 순차 검색·체크 → Apply
    option 3 : 검색 없이 기본 목록 상위 5개 체크 → Apply
    option 4 : 검색 없이 기본 목록 상위 10개 체크 → Apply
    """
    SECTION_XPATH  = "//button[normalize-space(.)='Publication Title']"
    SIBLING_XPATH  = SECTION_XPATH + "/../../following-sibling::*"
    INPUT_XPATH    = SIBLING_XPATH + "//input[@placeholder='Enter Title' or @placeholder='Enter title']"
    LABEL_XPATH    = SIBLING_XPATH + "//label"

    opt_names = {1: 'Remote Sensing 전체', 2: '4개 고정 저널', 3: '상위 5개', 4: '상위 10개'}
    print(f'4단계(다중): Publication Title 필터 적용 — 옵션{option}: {opt_names.get(option, "?")}')

    try:
        # Publication Title 섹션 펼치기
        pub_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, SECTION_XPATH))
        )
        if pub_btn.get_attribute('aria-expanded') != 'true':
            driver.execute_script('arguments[0].click();', pub_btn)
            time.sleep(2)
            print('[OK] Publication Title 섹션 펼침')

        inp = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, INPUT_XPATH))
        )

        # ── option 1: "Remote Sensing" 검색 → 전체 선택 ────────────────────
        if option == 1:
            inp.clear()
            inp.send_keys('Remote Sensing')
            time.sleep(4)
            labels = driver.find_elements(By.XPATH, LABEL_XPATH)
            if not labels:
                print('[경고] "Remote Sensing" 검색 결과 없음')
                return False
            count = 0
            for lbl in labels:
                try:
                    driver.execute_script('arguments[0].click();', lbl)
                    count += 1
                    time.sleep(0.3)
                except Exception:
                    pass
            print(f'[OK] {count}개 항목 선택 완료 (Remote Sensing 검색)')

        # ── option 2: 4개 고정 저널 순차 검색·선택 ─────────────────────────
        elif option == 2:
            selected = 0
            for search_raw, label_raw in JOURNAL_OPTION2_FIXED:
                search_term = search_raw.replace('{year}', str(year))
                match_text  = label_raw.replace('{year}', str(year))
                match_sub   = match_text[:40]

                inp.clear()
                inp.send_keys(search_term)
                time.sleep(3)

                labels = driver.find_elements(
                    By.XPATH, f"//label[contains(normalize-space(), '{match_sub}')]"
                )
                if labels:
                    driver.execute_script('arguments[0].click();', labels[0])
                    selected += 1
                    print(f'  [OK] 선택: {labels[0].text.strip()[:60]}')
                    time.sleep(0.5)
                else:
                    print(f'  [경고] 항목 없음: {match_text[:60]}')

                inp.clear()
                time.sleep(0.5)

            if selected == 0:
                print('[경고] option2: 선택된 저널 없음')
                return False
            print(f'[OK] option2: {selected}/4 저널 선택 완료')

        # ── option 3/4: 검색 없이 상위 N개 선택 ────────────────────────────
        elif option in (3, 4):
            top_n = 5 if option == 3 else 10
            time.sleep(2)
            labels = driver.find_elements(By.XPATH, LABEL_XPATH)[:top_n]
            if not labels:
                print(f'[경고] option{option}: 기본 목록 항목 없음')
                return False
            for lbl in labels:
                try:
                    driver.execute_script('arguments[0].click();', lbl)
                    time.sleep(0.3)
                except Exception:
                    pass
            print(f'[OK] option{option}: 상위 {len(labels)}개 선택 완료')

        else:
            print(f'[오류] 알 수 없는 journal_option: {option}')
            return False

        # ── Apply 버튼 클릭 ──────────────────────────────────────────────
        apply_btn = WebDriverWait(driver, 10).until(
            lambda d: next(
                (b for b in d.find_elements(By.CSS_SELECTOR, 'button.stats-applyRefinements-button')
                 if b.is_displayed() and b.is_enabled()),
                None
            )
        )
        driver.execute_script('arguments[0].click();', apply_btn)
        print('[OK] Apply 클릭 → 필터 적용 완료')
        time.sleep(8)
        return True

    except Exception as e:
        print(f'[경고] Publication Title 필터(옵션{option}) 실패: {e}')
        return False


# ==================== 키워드 기반 검색 설정 ====================
def setup_keyword_search(driver, year, keyword):
    """키워드 기반 IEEE Xplore 검색 URL로 직접 이동 (저널 필터 없음).

    Publication Title 필터를 사용하지 않고 queryText 에 키워드를 넣어 검색.
    전체 IEEE 저널·학회에서 관련 논문을 수집할 때 사용한다.

    Returns:
        base_search_url (str): 성공 시 기준 검색 URL (pageNumber=1)
        None: 실패 시
    """
    import urllib.parse

    try:
        cur = driver.current_url
        if 'ieeexplore' in cur.lower():
            if '/search' in cur:
                base = cur.split('/search')[0]
            elif '/Xplore' in cur:
                base = cur.split('/Xplore')[0]
            else:
                # 경로 끝 제거
                base = cur.rsplit('/', 1)[0]
        else:
            base = 'https://ieeexplore-ieee-org-ssl.proxy.kookmin.ac.kr'

        q = urllib.parse.quote(keyword, safe='')
        url = (f'{base}/search/searchresult.jsp?action=search'
               f'&newsearch=true&ranges={year}_{year}_Year'
               f'&queryText={q}&pageSize=10&pageNumber=1')

        print(f'[키워드검색] "{keyword}" ({year}년) → URL 직접 이동')
        driver.get(url)
        time.sleep(12)
        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        driver.execute_script('window.scrollTo(0, 0);')
        time.sleep(3)
        print(f'[OK] 키워드 검색 준비 완료')
        return url

    except Exception as e:
        print(f'[오류] 키워드 검색 설정 실패: {e}')
        return None


# ==================== 5단계: Items Per Page ====================
def set_items_per_page(driver, items=10):
    print(f'5단계: 페이지당 {items}개 항목 설정')

    SELECTORS = [
        "select[aria-label*='results per page']",
        "select[aria-label*='Results per page']",
        "select[aria-label*='per page']",
        "select.results-per-page",
    ]

    for attempt in range(3):
        try:
            time.sleep(3)  # 필터 적용 후 페이지 리렌더링 대기
            dropdown = None
            for sel in SELECTORS:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    dropdown = els[0]
                    break

            if dropdown is None:
                raise Exception('드롭다운 요소 미발견')

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dropdown)
            time.sleep(1)
            driver.execute_script(f"arguments[0].value = '{items}';", dropdown)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", dropdown)
            print(f'[OK] 페이지당 {items}개 설정')
            time.sleep(5)
            return True

        except Exception as e:
            print(f'[재시도 {attempt + 1}/3] Items per page 설정 실패: {e}')

    # CSS selector 방식 모두 실패 → URL pageSize 파라미터로 fallback
    # IEEE Xplore Angular 버전은 <select> 대신 커스텀 컴포넌트를 사용하는 경우가 있음
    try:
        cur = driver.current_url
        if f'pageSize={items}' not in cur:
            sep = '&' if '?' in cur else '?'
            new_url = cur + sep + f'pageSize={items}&pageNumber=1'
            print(f'[폴백] URL pageSize 파라미터 설정: {new_url}')
            driver.get(new_url)
            time.sleep(8)
            print(f'[OK] URL로 페이지당 {items}개 설정 완료')
            return True
    except Exception as e:
        print(f'[경고] URL pageSize 설정 실패: {e}')

    print('[경고] Items per page 설정 최종 실패 → 기본값으로 진행')
    return False


# ==================== 페이지 처리 ====================
# 전체 선택 체크박스 CSS 셀렉터 (우선순위 순)
_SELECT_ALL_SELECTORS = [
    "input.results-actions-selectall-checkbox",
    "input[type='checkbox'][class*='selectall']",
    "input[type='checkbox'][class*='select-all']",
    "input[type='checkbox'][aria-label*='Select all']",
    "input[type='checkbox'][aria-label*='select all']",
    "input[type='checkbox'][aria-label*='Select All']",
    ".results-actions-selectall input[type='checkbox']",
    "xpl-select-all input[type='checkbox']",
    "div.results-actions input[type='checkbox']",
    "input[type='checkbox'][id*='select-all']",
]


def select_all_results(driver, stats=None):
    """전체 선택 체크박스 클릭. 성공 여부 반환.

    재로그인 직후 Angular SPA 가 콜드 스타트 상태에서 중간 페이지에 직접 진입하면
    결과 목록은 로드되지만 results-actions(Select All 포함) 컴포넌트가
    뒤늦게 초기화되는 경우가 있다. 스크롤 트리거 + 긴 wait 로 대응한다.
    """
    MAX_ATTEMPTS = 5
    for attempt in range(MAX_ATTEMPTS):
        try:
            # ── Angular 렌더링 트리거: 스크롤 다운 → 업 ─────────────────────
            # 결과 목록을 한 번 스크롤해야 results-actions 컴포넌트가 활성화되는
            # IEEE Xplore 특성에 대응한다.
            driver.execute_script('window.scrollTo(0, 400);')
            time.sleep(1)
            driver.execute_script('window.scrollTo(0, 0);')
            time.sleep(2)

            # ── 여러 셀렉터로 체크박스 탐색 ─────────────────────────────────
            # 첫 시도: 주 셀렉터에 25 초 대기 (Angular 컴포넌트 초기화 충분히 기다림)
            # 이후 시도: 셀렉터당 5 초 대기 (빠른 순환)
            primary_timeout  = 25 if attempt == 0 else 5
            fallback_timeout = 5

            select_all = None
            # 주 셀렉터 (긴 wait)
            try:
                el = WebDriverWait(driver, primary_timeout).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, _SELECT_ALL_SELECTORS[0])
                    )
                )
                select_all = el
            except Exception:
                pass

            # 폴백 셀렉터들
            if select_all is None:
                for sel in _SELECT_ALL_SELECTORS[1:]:
                    try:
                        el = WebDriverWait(driver, fallback_timeout).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                        )
                        select_all = el
                        break
                    except Exception:
                        continue

            if select_all is None:
                raise TimeoutException('모든 셀렉터에서 체크박스 미발견')

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", select_all)
            time.sleep(1)
            if not select_all.is_selected():
                driver.execute_script('arguments[0].click();', select_all)
                print('[OK] Select All on Page 클릭')
                time.sleep(2)
            return True

        except Exception as e:
            err_short = f'{type(e).__name__}: {str(e)[:60]}'
            print(f'[재시도 {attempt + 1}/{MAX_ATTEMPTS}] 전체 선택 실패 ({err_short})')

            if attempt == 1:
                # 2번째 실패: 페이지 새로고침 + 더 큰 스크롤로 렌더링 재유도
                print('[재시도] 페이지 새로고침 + 스크롤 트리거...')
                try:
                    driver.refresh()
                    time.sleep(15)
                    driver.execute_script('window.scrollTo(0, 800);')
                    time.sleep(2)
                    driver.execute_script('window.scrollTo(0, 0);')
                    time.sleep(3)
                except Exception:
                    pass
            elif attempt == 3:
                # 4번째 실패: JavaScript로 직접 체크박스 탐색·클릭
                try:
                    found = driver.execute_script("""
                        var cbs = document.querySelectorAll("input[type='checkbox']");
                        for (var i=0; i<cbs.length; i++) {
                            var cls = cbs[i].className || '';
                            var lbl = (cbs[i].getAttribute('aria-label') || '').toLowerCase();
                            if (cls.toLowerCase().indexOf('select') >= 0 || lbl.indexOf('select all') >= 0) {
                                cbs[i].click();
                                return true;
                            }
                        }
                        return false;
                    """)
                    if found:
                        print('[OK] JS 직접 클릭으로 전체 선택 성공')
                        time.sleep(2)
                        return True
                except Exception:
                    pass
                time.sleep(12)
            else:
                time.sleep(12)

    print(f'[오류] 전체 선택 {MAX_ATTEMPTS}회 실패  현재 URL: {driver.current_url}')
    if stats is not None:
        stats.select_all_failures += 1
    return False


def unzip_and_cleanup(zip_path, save_dir, stats=None):
    """zip 파일에서 PDF만 추출 후 zip 삭제. 크롬 임시파일도 정리.
    Returns (extracted, skipped) 튜플."""
    save_dir = Path(save_dir)
    zip_path = Path(zip_path)
    extracted = 0
    skipped   = 0

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for member in zf.namelist():
                if not member.lower().endswith('.pdf'):
                    continue
                filename = Path(member).name   # 디렉토리 구조 무시, 파일명만 사용
                target = save_dir / filename
                if target.exists():
                    skipped += 1
                    continue
                with zf.open(member) as src, open(target, 'wb') as dst:
                    dst.write(src.read())
                extracted += 1
                print(f'  [압축해제] {filename}')

        print(f'[OK] PDF 추출: {extracted}개  (중복 건너뜀: {skipped}개)')
        zip_path.unlink()
        print(f'[OK] zip 삭제: {zip_path.name}')

    except Exception as e:
        print(f'[경고] 압축 해제 실패: {e}')

    # 크롬 임시 파일 정리 (.crdownload, .com.google.Chrome.*)
    for tmp in save_dir.iterdir():
        if tmp.name.endswith('.crdownload') or tmp.name.startswith('.com.google.Chrome'):
            try:
                tmp.unlink()
                print(f'[OK] 임시파일 삭제: {tmp.name}')
            except Exception:
                pass

    if stats is not None:
        stats.pdfs_extracted     += extracted
        stats.duplicates_skipped += skipped

    return extracted, skipped


def trigger_download(driver, config, page_number=1, stats=None):
    try:
        save_dir = Path(config.SAVE_PATH)

        # 이전 trigger_download 호출에서 Chrome이 뒤늦게 완료시킨 zip 처리
        for f in list(save_dir.iterdir()):
            if f.is_file() and f.suffix == '.zip' and not f.name.endswith('.crdownload'):
                sz = f.stat().st_size
                print(f'[재개] 이전 시도 완료 zip 발견: {f.name} ({sz // 1024} KB) → 처리')
                unzip_and_cleanup(f, save_dir, stats=stats)
                if stats is not None:
                    stats.zip_downloads += 1
                return True

        # 다운로드 전 기존 파일 목록 기록 (.crdownload 포함)
        existing = set(f.name for f in save_dir.iterdir() if f.is_file())

        # 이전 시도에서 남겨진 crdownload가 있으면 재클릭 없이 바로 모니터링
        pre_existing_crdownload = None
        for f in save_dir.iterdir():
            if f.is_file() and f.name.endswith('.crdownload'):
                pre_existing_crdownload = f
                break

        if pre_existing_crdownload:
            print(f'[재개] 기존 crdownload 감지: {pre_existing_crdownload.name}  → 다운로드 버튼 생략')
            download_started = True
            crdownload_path = pre_existing_crdownload
            crdownload_last_size = crdownload_path.stat().st_size if crdownload_path.exists() else -1
            crdownload_last_change = time.time()
            download_deadline = time.time() + 600
        else:
            # 1) "Download PDFs" 버튼 클릭 (결과 목록 상단 액션 버튼)
            dl_btn = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//button[contains(text(), 'Download PDFs')]")
                )
            )
            driver.execute_script('arguments[0].click();', dl_btn)
            print('[OK] Download PDFs 클릭')
            time.sleep(5)

            # 2) 모달 내 "Download" 확인 버튼 (class: stats-SearchResults_BulkPDFDownload)
            confirm_btn = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH,
                     "//button[normalize-space(.)='Download' "
                     "or contains(@class,'stats-SearchResults_BulkPDFDownload')]")
                )
            )
            driver.execute_script('arguments[0].click();', confirm_btn)
            print('[OK] 다운로드 확인 클릭')

            download_started = False
            crdownload_path = None
            crdownload_last_size = -1
            crdownload_last_change = None
            download_deadline = time.time() + config.DOWNLOAD_WAIT_SECONDS

        # 3) 새로 나타난 파일(zip 또는 pdf)이 저장 폴더에 나타날 때까지 대기
        print(f'[대기] 다운로드 중... (최대 {config.DOWNLOAD_WAIT_SECONDS}초, crdownload 감지 시 +600초)')
        STALL_TIMEOUT = 300  # 크기 변화 없으면 stall 판정 (초) — 대용량 zip 완료 후 Chrome 재명 대기 포함
        while time.time() < download_deadline:
            for f in save_dir.iterdir():
                if not f.is_file():
                    continue
                # 완료된 파일 감지 (새로 나타난 zip/pdf)
                if f.suffix in ('.zip', '.pdf') and not f.name.endswith('.crdownload') and f.name not in existing:
                    sz = f.stat().st_size
                    print(f'[OK] 다운로드 완료: {f.name}  (페이지 {page_number}, {sz // 1024} KB)')
                    if f.suffix == '.zip':
                        unzip_and_cleanup(f, save_dir, stats=stats)
                    if stats is not None:
                        stats.zip_downloads += 1
                    return True
                # 진행 중인 파일 감지 (.crdownload) → 데드라인 600초 연장
                if f.name.endswith('.crdownload') and not download_started:
                    download_started = True
                    crdownload_path = f
                    crdownload_last_change = time.time()
                    download_deadline = time.time() + 600
                    print(f'[진행] 다운로드 시작 감지: {f.name}  (최대 600초 추가 대기)')

            # crdownload 크기 모니터링 (stall 감지)
            if crdownload_path and crdownload_path.exists():
                cur_size = crdownload_path.stat().st_size
                if cur_size != crdownload_last_size:
                    crdownload_last_size = cur_size
                    crdownload_last_change = time.time()
                    print(f'[진행중] {crdownload_path.name}: {cur_size // 1024} KB')
                elif crdownload_last_change and (time.time() - crdownload_last_change) > STALL_TIMEOUT:
                    print(f'[경고] 다운로드 stall 감지 ({STALL_TIMEOUT}초간 크기 변화 없음) → 재시도')
                    break

            time.sleep(10)

        # stall/타임아웃 후 Chrome이 rename을 완료했을 수 있음 → 60초 추가 확인
        if crdownload_path:
            sz = crdownload_path.stat().st_size if crdownload_path.exists() else 0
            print(f'[대기] stall/타임아웃 후 60초 추가 zip 확인... (crdownload: {sz // 1024} KB)')
        else:
            print('[대기] 타임아웃 후 60초 추가 zip 확인...')
        for _ in range(12):
            time.sleep(5)
            for f in save_dir.iterdir():
                if (f.is_file() and f.suffix == '.zip'
                        and not f.name.endswith('.crdownload')
                        and f.name not in existing):
                    sz = f.stat().st_size
                    print(f'[OK] 다운로드 완료 (지연 감지): {f.name}  (페이지 {page_number}, {sz // 1024} KB)')
                    unzip_and_cleanup(f, save_dir, stats=stats)
                    if stats is not None:
                        stats.zip_downloads += 1
                    return True

        if crdownload_path and crdownload_path.exists():
            sz = crdownload_path.stat().st_size
            print(f'[경고] 다운로드 최종 타임아웃  {crdownload_path.name}: {sz // 1024} KB (파일 유지)')
        else:
            print('[경고] 다운로드 최종 타임아웃')
        if stats is not None:
            stats.download_failures += 1
        return False

    except Exception as e:
        print(f'[오류] 다운로드 실패: {e}')
        return False


def process_current_page(driver, page_number, config, stats=None):
    print(f"\n{'='*60}")
    print(f'페이지 {page_number} 처리')
    print(f"{'='*60}")

    for attempt in range(1, config.MAX_SEAT_LIMIT_RETRIES + 1):
        if check_seat_limit(driver):
            print(f'[경고] Seat Limit 감지 ({attempt}/{config.MAX_SEAT_LIMIT_RETRIES})')
            print(f'[대기] {config.SEAT_LIMIT_WAIT_SECONDS}초 대기...')
            time.sleep(config.SEAT_LIMIT_WAIT_SECONDS)
            driver.refresh()
            time.sleep(5)
            continue

        try:
            if not select_all_results(driver, stats=stats):
                continue
            if not trigger_download(driver, config, page_number, stats=stats):
                continue

            print(f'[OK] 페이지 {page_number} 완료')
            if stats is not None:
                stats.pages_processed += 1
            random_delay(5, 15)
            return True

        except Exception as e:
            if check_seat_limit(driver):
                continue
            print(f'[오류] {e}')
            raise

    print(f'[실패] 페이지 {page_number}: Seat Limit 재시도 초과')
    if stats is not None:
        stats.pages_skipped += 1
    return False


def locate_page_button(driver, page_number, timeout=10):
    selectors = [
        (By.CSS_SELECTOR, f'button.stats-Pagination_{page_number}'),
        (By.CSS_SELECTOR, f"button[aria-label='Page {page_number} of search results']"),
    ]
    end_time = time.time() + timeout
    while time.time() < end_time:
        for by, value in selectors:
            for el in driver.find_elements(by, value):
                if el.is_displayed() and el.is_enabled():
                    return el
        time.sleep(0.2)
    raise TimeoutException(f'페이지 {page_number} 버튼 미발견')


def locate_next_arrow(driver, timeout=8):
    """'>' 또는 'Next' 이동 버튼을 찾는다 (10페이지 초과 시 번호 버튼 대신 사용)."""
    selectors = [
        (By.CSS_SELECTOR, "button[class*='stats-Pagination_next']"),
        (By.CSS_SELECTOR, "button[class*='stats-Pagination_Next']"),
        (By.CSS_SELECTOR, "button[class*='Pagination_arrow_next']"),
        (By.XPATH, "//button[normalize-space(.)='>'][not(@disabled)]"),
        (By.XPATH, "//button[normalize-space(.)='Next'][not(@disabled)]"),
    ]
    end_time = time.time() + timeout
    while time.time() < end_time:
        for by, value in selectors:
            for el in driver.find_elements(by, value):
                if el.is_displayed() and el.is_enabled():
                    return el
        time.sleep(0.3)
    return None


def go_to_next_page(driver, current_page, config):
    if check_seat_limit(driver):
        time.sleep(config.SEAT_LIMIT_WAIT_SECONDS)
        driver.refresh()
        time.sleep(5)

    next_page = current_page + 1

    # ── 1순위: 저장된 기준 URL로 pageNumber만 바꿔 직접 이동 ──────────────
    # 버튼 클릭 방식은 Angular 라우팅으로 처리되어 모달/필터/pageSize가 유실될 수 있음
    base_url = getattr(config, 'base_search_url', None)
    if base_url:
        try:
            if 'pageNumber=' in base_url:
                new_url = re.sub(r'pageNumber=\d+', f'pageNumber={next_page}', base_url)
            else:
                sep = '&' if '?' in base_url else '?'
                new_url = base_url + sep + f'pageNumber={next_page}'

            driver.get(new_url)
            print(f'→ 페이지 {next_page} 이동 (URL 직접)')
            WebDriverWait(driver, 20).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            driver.execute_script('window.scrollTo(0, 0);')
            time.sleep(8)
            return next_page
        except Exception as e:
            print(f'[경고] URL 직접 이동 실패: {e}  → 버튼 클릭 방식으로 폴백')

    # ── 2순위: 기준 URL 없을 때 버튼 클릭 폴백 ───────────────────────────
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
    time.sleep(2)

    try:
        try:
            btn = locate_page_button(driver, next_page, timeout=5)
        except TimeoutException:
            btn = locate_next_arrow(driver)

        if btn is None:
            print(f'[경고] 페이지 {next_page} 버튼 및 Next 화살표 미발견 → 크롤링 종료')
            return None

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
        driver.execute_script('arguments[0].click();', btn)

        print(f'→ 페이지 {next_page} 이동 (버튼 클릭)')
        time.sleep(config.PAGE_CHANGE_DELAY)
        random_delay(1, 3)

        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        driver.execute_script('window.scrollTo(0, 0);')
        time.sleep(8)
        return next_page

    except Exception as e:
        print(f'[경고] 페이지 {next_page} 이동 실패: {e} → 크롤링 종료')
        return None


# ==================== 페이지 내비게이션 (재로그인 후 Angular warm-up) ====================
def _navigate_with_warmup(driver, base_search_url: str, target_page: int):
    """재로그인 직후 Angular 콜드 스타트 문제를 해결하는 페이지 이동 방법.

    문제:
        재로그인 후 검색 결과 중간 페이지(예: pageNumber=21)에 직접 URL로 이동하면
        IEEE Xplore Angular 앱이 콜드 스타트 상태에서 결과 목록만 렌더링하고
        results-actions 컴포넌트(Select All 체크박스 포함)를 초기화하지 않는 경우가 있다.

    해결책:
        1) 페이지 1 에 먼저 방문 → Angular 앱이 정상 초기화
        2) 스크롤 트리거로 lazy 컴포넌트 활성화
        3) 목표 페이지로 이동 → Angular 가 이미 초기화된 상태에서 페이지만 변경

    Args:
        base_search_url : 기준 검색 URL (pageNumber=1 포함)
        target_page     : 이동할 목표 페이지 번호
    """
    def _make_page_url(url, page):
        if 'pageNumber=' in url:
            return re.sub(r'pageNumber=\d+', f'pageNumber={page}', url)
        sep = '&' if '?' in url else '?'
        return url + sep + f'pageNumber={page}'

    # ── 1단계: 페이지 1 경유 (Angular 초기화) ─────────────────────────────
    url_p1 = _make_page_url(base_search_url, 1)
    print(f'[내비] 페이지 1 경유 (Angular warm-up)...')
    driver.get(url_p1)
    time.sleep(15)
    # 스크롤 트리거
    driver.execute_script('window.scrollTo(0, 400);')
    time.sleep(2)
    driver.execute_script('window.scrollTo(0, 0);')
    time.sleep(3)

    # ── 2단계: 목표 페이지 이동 ──────────────────────────────────────────
    if target_page > 1:
        url_target = _make_page_url(base_search_url, target_page)
        print(f'[내비] 페이지 {target_page} 이동...')
        driver.get(url_target)
        time.sleep(15)
        driver.execute_script('window.scrollTo(0, 400);')
        time.sleep(2)
        driver.execute_script('window.scrollTo(0, 0);')
        time.sleep(3)


# ==================== 단일 연도 크롤링 ====================
def _relogin_and_setup(driver, year, config, username, password,
                       search_term=None, label_match=None, stats=None,
                       journal_option=None):
    """세션 만료 시 재로그인 후 검색 설정 복구. 성공하면 True.

    journal_option : --journal-option 값(1~4). None이면 단일 저널 필터(기존 동작).
    """
    print('[재로그인] 프록시 세션 만료 → 재로그인 시도')
    if stats is not None:
        stats.session_relogins += 1
    if not login_kookmin_library(driver, username, password):
        print('[재로그인] 도서관 로그인 실패')
        return False
    if not access_ieee_via_library(driver):
        print('[재로그인] IEEE 접속 실패')
        return False
    if not setup_ieee_advanced_search(driver, year):
        print('[재로그인] Advanced Search 실패')
        return False
    # 필터 재적용 (journal_option 여부에 따라 분기)
    if journal_option is not None:
        if journal_option == 'all':
            print('[재로그인] journal-option all → 필터 없이 전체 크롤')
        elif not apply_publication_filter_multi(driver, journal_option, year):
            print('[재로그인] 저널 필터(다중) 건너뜀')
    else:
        cur_search = search_term or 'Transactions on Geoscience and Remote Sensing'
        cur_label  = label_match or 'IEEE Transactions on Geoscience and Remote Sensing'
        if not apply_publication_filter(driver, cur_search, cur_label):
            print('[재로그인] 저널 필터 건너뜀')
    if not set_items_per_page(driver, 10):
        print('[재로그인] Items per page 건너뜀')
    config.base_search_url = driver.current_url
    print(f'[재로그인] 복구 완료. 기준 URL: {config.base_search_url}')
    return True


def _crawl_one_journal(driver, year, config, username, password,
                       search_term, label_match, stats,
                       progress: 'ProgressTracker | None' = None,
                       start_page: int = 1):
    """단일 저널의 전 페이지 다운로드 루프. _do_year_crawl 에서 저널마다 호출.

    Args:
        progress  : ProgressTracker 인스턴스 (None이면 진행 상황 기록 안 함)
        start_page: 시작 페이지 번호 (--resume 시 마지막 완료 페이지+1)
    """
    print(f"\n{'='*60}")
    print(f'저널 크롤링 시작: {label_match}  ({year}년, p.{start_page}~)')
    print(f"{'='*60}\n")

    # ── 검색 + 필터 설정 ────────────────────────────────────────────────
    if not setup_ieee_advanced_search(driver, year):
        print(f'[경고] Advanced Search 실패 → 다음 저널로 건너뜀')
        return

    if is_session_expired(driver):
        if not _relogin_and_setup(driver, year, config, username, password,
                                  search_term, label_match, stats):
            print('[경고] 재로그인 실패 → 다음 저널로 건너뜀')
            return
    else:
        if not apply_publication_filter(driver, search_term, label_match):
            print(f'[경고] 저널 필터 실패 ({label_match}) → 다음 저널로 건너뜀')
            return

        if not set_items_per_page(driver, 10):
            print('[경고] Items per page 설정 건너뜀 - 기본값으로 진행')

        config.base_search_url = driver.current_url
        print(f'[INFO] 기준 검색 URL 저장: {config.base_search_url}')

    # ── start_page > 1 이면 warm-up 방식으로 이동 (resume) ──────────────
    if start_page > 1 and hasattr(config, 'base_search_url') and config.base_search_url:
        print(f'[RESUME] 페이지 {start_page} 로 warm-up 이동')
        _navigate_with_warmup(driver, config.base_search_url, start_page)

    current_page      = start_page
    visited_pages     = 0
    page_fail_count   = {}
    consecutive_fails = 0   # 연속으로 완전 실패(MAX_PAGE_RETRIES 소진)한 페이지 수
    last_completed    = start_page - 1   # 마지막으로 완료한 페이지 번호

    while visited_pages < config.MAX_PAGE_VISITS:
        # ── 세션 만료 체크 ────────────────────────────────────────────────
        if is_session_expired(driver):
            if not _relogin_and_setup(driver, year, config, username, password,
                                      search_term, label_match, stats):
                print('[경고] 페이지 처리 중 재로그인 실패 → 저널 크롤링 중단')
                break
            if hasattr(config, 'base_search_url') and config.base_search_url:
                # 재로그인 후 Angular warm-up: 페이지 1 경유 → 목표 페이지
                # 직접 pageNumber=N 으로 점프하면 Angular 콜드 스타트 상태에서
                # results-actions(Select All) 컴포넌트가 초기화 안 되는 버그 방지
                _navigate_with_warmup(driver, config.base_search_url, current_page)

        # ── 빈 페이지 감지 (마지막 페이지 초과) ──────────────────────────
        # "전체 선택" 체크박스 자체가 없는 원인: 결과가 0건인 빈 페이지
        if not has_search_results(driver):
            print(f'[완료] {label_match}: p.{current_page} 빈 페이지 감지 → 저널 크롤링 종료')
            if progress:
                progress.mark_completed(label_match, last_completed,
                                        stats.pdfs_extracted)
            break

        success = process_current_page(driver, current_page, config, stats=stats)

        if not success:
            fails = page_fail_count.get(current_page, 0) + 1
            page_fail_count[current_page] = fails
            if fails >= config.MAX_PAGE_RETRIES:
                consecutive_fails += 1
                print(f'[경고] 페이지 {current_page} {fails}회 실패 → 건너뜀 '
                      f'(연속 {consecutive_fails}페이지 완전 실패)')

                # ── 연속 실패 한도 초과: 다운로드 할당량 소진 또는 UI 오류 ──
                # Select All 체크박스가 없는 상태(세션 한도·프록시 제한)에서
                # 페이지를 계속 시도해도 개선되지 않으므로 저널을 건너뜀.
                if consecutive_fails >= config.MAX_CONSECUTIVE_PAGE_FAILS:
                    print(f'[중단] {consecutive_fails}페이지 연속 전체 실패 → '
                          f'다운로드 한도 소진 또는 UI 오류로 판단, 저널 크롤링 중단')
                    if progress:
                        progress.update(label_match, search_term, last_completed,
                                        stats.pdfs_extracted, status='in_progress')
                    break

                if stats is not None:
                    stats.pages_skipped += 1
                visited_pages += 1
                next_page = go_to_next_page(driver, current_page, config)
                if next_page is None:
                    print(f'[완료] {label_match} 전체 페이지 처리 완료!')
                    if progress:
                        progress.mark_completed(label_match, last_completed,
                                                stats.pdfs_extracted)
                    break
                current_page = next_page
            else:
                print(f'[경고] 페이지 {current_page} 실패 ({fails}/{config.MAX_PAGE_RETRIES}), 2분 대기 후 재시도')
                time.sleep(120)
            continue

        # ── 페이지 성공 처리 ─────────────────────────────────────────────
        consecutive_fails = 0   # 성공 시 연속 실패 카운터 리셋
        page_fail_count[current_page] = 0
        last_completed = current_page
        visited_pages += 1

        # 진행 상황 및 통계 실시간 업데이트
        if progress:
            progress.update(label_match, search_term, current_page,
                            stats.pdfs_extracted, status='in_progress')
        stats.checkpoint()   # ← zip 처리 후 CSV 즉시 반영

        next_page = go_to_next_page(driver, current_page, config)
        if next_page is None:
            print(f'[완료] {label_match} 전체 페이지 처리 완료!')
            if progress:
                progress.mark_completed(label_match, last_completed,
                                        stats.pdfs_extracted)
            break
        current_page = next_page

    end_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'='*60}")
    print(f'[완료] {label_match} ({year}년)  종료: {end_ts}')
    print(f"  페이지: {stats.pages_processed}개 완료, {stats.pages_skipped}개 건너뜀")
    print(f"  PDF: {stats.pdfs_extracted}개 추출, {stats.duplicates_skipped}개 중복")
    print(f"  Zip: {stats.zip_downloads}개  전체선택실패: {stats.select_all_failures}회")
    print(f"{'='*60}\n")


def _crawl_with_journal_option(driver, year, config, username, password,
                                option, stats, progress=None, start_page=1):
    """--journal-option 기반 크롤링: Publication Title 필터를 다중 선택 후 전 페이지 다운로드.

    apply_publication_filter_multi 로 여러 저널/학회를 한 번에 필터링하고
    결과 전체를 단일 크롤 단위로 처리한다.

    option 'all': 필터 없이 전체 (연도 필터만 적용)
    option 1    : "Remote Sensing" 검색 → 전체 항목 선택
    option 2    : 4개 고정 저널 (IEEE Access / Sensors Journal / IGARSS / TGRS)
    option 3    : 검색 없이 상위 5개
    option 4    : 검색 없이 상위 10개
    """
    opt_labels = {'all': '필터 없음 전체', 1: 'Remote Sensing 전체',
                  2: '4개 고정 저널', 3: '상위 5개', 4: '상위 10개'}
    label = f'[OPT{option}] {opt_labels.get(option, "?")}'
    year_str = str(year)

    print(f"\n{'='*60}")
    print(f'저널옵션{option} 크롤링 시작: {label}  '
          f'({"전체 연도" if year_str == "all" else year_str + "년"}, p.{start_page}~)')
    print(f"{'='*60}\n")

    # ── 검색 + 필터 설정 ─────────────────────────────────────────────────
    if not setup_ieee_advanced_search(driver, year):
        print('[경고] Advanced Search 실패 → 건너뜀')
        return

    if is_session_expired(driver):
        if not _relogin_and_setup(driver, year, config, username, password,
                                  stats=stats, journal_option=option):
            print('[경고] 재로그인 실패 → 건너뜀')
            return
    else:
        if option == 'all':
            print('[INFO] journal-option all → Publication Title 필터 없이 전체 크롤')
        elif not apply_publication_filter_multi(driver, option, year):
            print('[경고] Publication Title 필터(다중) 실패 → 건너뜀')
            return
        if not set_items_per_page(driver, 10):
            print('[경고] Items per page 설정 건너뜀')
        config.base_search_url = driver.current_url
        print(f'[INFO] 기준 검색 URL: {config.base_search_url}')

    # ── start_page > 1 이면 warm-up 이동 ────────────────────────────────
    if start_page > 1 and hasattr(config, 'base_search_url') and config.base_search_url:
        print(f'[RESUME] p.{start_page} 로 warm-up 이동')
        _navigate_with_warmup(driver, config.base_search_url, start_page)

    current_page      = start_page
    visited_pages     = 0
    page_fail_count   = {}
    consecutive_fails = 0
    last_completed    = start_page - 1

    while visited_pages < config.MAX_PAGE_VISITS:
        if is_session_expired(driver):
            if not _relogin_and_setup(driver, year, config, username, password,
                                      stats=stats, journal_option=option):
                print('[경고] 재로그인 실패 → 크롤링 중단')
                break
            if hasattr(config, 'base_search_url') and config.base_search_url:
                _navigate_with_warmup(driver, config.base_search_url, current_page)

        if not has_search_results(driver):
            print(f'[완료] {label}: p.{current_page} 빈 페이지 → 종료')
            if progress:
                progress.mark_completed(label, last_completed, stats.pdfs_extracted)
            break

        success = process_current_page(driver, current_page, config, stats=stats)

        if not success:
            fails = page_fail_count.get(current_page, 0) + 1
            page_fail_count[current_page] = fails
            if fails >= config.MAX_PAGE_RETRIES:
                consecutive_fails += 1
                print(f'[경고] p.{current_page} {fails}회 실패 → 건너뜀 '
                      f'(연속 {consecutive_fails}페이지)')
                if consecutive_fails >= config.MAX_CONSECUTIVE_PAGE_FAILS:
                    print(f'[중단] {consecutive_fails}페이지 연속 실패 → 크롤링 중단')
                    if progress:
                        progress.update(label, f'OPT{option}', last_completed,
                                        stats.pdfs_extracted, status='in_progress')
                    break
                stats.pages_skipped += 1
                visited_pages += 1
                next_page = go_to_next_page(driver, current_page, config)
                if next_page is None:
                    if progress:
                        progress.mark_completed(label, last_completed, stats.pdfs_extracted)
                    break
                current_page = next_page
            else:
                print(f'[경고] p.{current_page} 실패 ({fails}/{config.MAX_PAGE_RETRIES}), 2분 대기')
                time.sleep(120)
            continue

        consecutive_fails = 0
        page_fail_count[current_page] = 0
        last_completed = current_page
        visited_pages += 1

        if progress:
            progress.update(label, f'OPT{option}', current_page,
                            stats.pdfs_extracted, status='in_progress')
        stats.checkpoint()

        next_page = go_to_next_page(driver, current_page, config)
        if next_page is None:
            print(f'[완료] {label} 전체 페이지 처리 완료!')
            if progress:
                progress.mark_completed(label, last_completed, stats.pdfs_extracted)
            break
        current_page = next_page

    end_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'='*60}")
    print(f'[완료] {label} ({year}년)  종료: {end_ts}')
    print(f"  페이지: {stats.pages_processed}개 완료, {stats.pages_skipped}개 건너뜀")
    print(f"  PDF: {stats.pdfs_extracted}개 추출, {stats.duplicates_skipped}개 중복")
    print(f"  Zip: {stats.zip_downloads}개  전체선택실패: {stats.select_all_failures}회")
    print(f"{'='*60}\n")


def _crawl_by_keyword(driver, year, config, username, password,
                      keyword, stats,
                      progress=None, start_page: int = 1):
    """키워드 기반 IEEE 전체 검색 결과 다운로드 루프.

    Publication Title 필터 없이 키워드(queryText)로만 검색해
    전체 IEEE 저널·학회에서 관련 논문을 수집한다.
    로직은 _crawl_one_journal 과 동일하나 설정 단계가 간략하다.

    Args:
        keyword   : IEEE Xplore queryText 검색어
        stats     : CrawlStats 인스턴스 (외부에서 생성해 전달)
        progress  : ProgressTracker 인스턴스 (None이면 진행 상황 기록 안 함)
        start_page: 시작 페이지 (--resume 시 마지막 완료 페이지+1)
    """
    label = f'[KW] {keyword}'

    print(f"\n{'='*60}")
    print(f'키워드 크롤링 시작: "{keyword}"  ({year}년, p.{start_page}~)')
    print(f"{'='*60}\n")

    # ── 키워드 검색 URL 설정 ───────────────────────────────────────────────
    if is_session_expired(driver):
        if not _relogin_and_setup(driver, year, config, username, password, stats=stats):
            print('[경고] 재로그인 실패 → 키워드 크롤링 건너뜀')
            return

    base_url = setup_keyword_search(driver, year, keyword)
    if base_url is None:
        print(f'[경고] 키워드 "{keyword}" 검색 설정 실패 → 다음 키워드로 건너뜀')
        return

    config.base_search_url = base_url

    # ── start_page > 1 이면 warm-up 방식으로 이동 (resume) ──────────────
    if start_page > 1:
        print(f'[RESUME] 키워드 "{keyword}" p.{start_page} 로 warm-up 이동')
        _navigate_with_warmup(driver, base_url, start_page)

    current_page      = start_page
    visited_pages     = 0
    page_fail_count   = {}
    consecutive_fails = 0
    last_completed    = start_page - 1

    while visited_pages < config.MAX_PAGE_VISITS:
        # ── 세션 만료 체크 ─────────────────────────────────────────────────
        if is_session_expired(driver):
            if not _relogin_and_setup(driver, year, config, username, password, stats=stats):
                print('[경고] 재로그인 실패 → 키워드 크롤링 중단')
                break
            new_url = setup_keyword_search(driver, year, keyword)
            if new_url:
                base_url = new_url
                config.base_search_url = base_url
                _navigate_with_warmup(driver, base_url, current_page)

        # ── 빈 페이지 감지 ─────────────────────────────────────────────────
        if not has_search_results(driver):
            print(f'[완료] 키워드 "{keyword}": p.{current_page} 빈 페이지 → 크롤링 종료')
            if progress:
                progress.mark_completed(label, last_completed, stats.pdfs_extracted)
            break

        success = process_current_page(driver, current_page, config, stats=stats)

        if not success:
            fails = page_fail_count.get(current_page, 0) + 1
            page_fail_count[current_page] = fails
            if fails >= config.MAX_PAGE_RETRIES:
                consecutive_fails += 1
                print(f'[경고] 페이지 {current_page} {fails}회 실패 → 건너뜀 '
                      f'(연속 {consecutive_fails}페이지 실패)')
                if consecutive_fails >= config.MAX_CONSECUTIVE_PAGE_FAILS:
                    print(f'[중단] {consecutive_fails}페이지 연속 실패 → 키워드 크롤링 중단')
                    if progress:
                        progress.update(label, keyword, last_completed,
                                        stats.pdfs_extracted, status='in_progress')
                    break
                stats.pages_skipped += 1
                visited_pages += 1
                next_page = go_to_next_page(driver, current_page, config)
                if next_page is None:
                    if progress:
                        progress.mark_completed(label, last_completed, stats.pdfs_extracted)
                    break
                current_page = next_page
            else:
                print(f'[경고] 페이지 {current_page} 실패 ({fails}/{config.MAX_PAGE_RETRIES}), 2분 대기')
                time.sleep(120)
            continue

        # ── 페이지 성공 처리 ──────────────────────────────────────────────
        consecutive_fails = 0
        page_fail_count[current_page] = 0
        last_completed = current_page
        visited_pages += 1

        if progress:
            progress.update(label, keyword, current_page,
                            stats.pdfs_extracted, status='in_progress')
        stats.checkpoint()

        next_page = go_to_next_page(driver, current_page, config)
        if next_page is None:
            print(f'[완료] 키워드 "{keyword}" 전체 페이지 처리 완료!')
            if progress:
                progress.mark_completed(label, last_completed, stats.pdfs_extracted)
            break
        current_page = next_page

    end_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'='*60}")
    print(f'[완료] 키워드 "{keyword}" ({year}년)  종료: {end_ts}')
    print(f"  페이지: {stats.pages_processed}개 완료, {stats.pages_skipped}개 건너뜀")
    print(f"  PDF: {stats.pdfs_extracted}개 추출, {stats.duplicates_skipped}개 중복")
    print(f"  Zip: {stats.zip_downloads}개  전체선택실패: {stats.select_all_failures}회")
    print(f"{'='*60}\n")


def _do_year_crawl(driver, year, config, username, password,
                   journal_targets=None, num_journals=None,
                   keyword_targets=None, resume: bool = False,
                   journal_option=None):
    """단일 연도의 크롤링 내부 루프 — 모든 대상 저널 + (옵션) 키워드를 순회.

    Args:
        num_journals  : 사용할 저널 수 (JOURNAL_TARGETS_ALL[:n] 기준). None이면 30개.
        keyword_targets: 키워드 기반 크롤링 목록 (None이면 키워드 크롤링 건너뜀).
        resume        : True이면 progress_{year}.json 을 읽어 완료/진행 중 항목을 재개.
        journal_option: 1~4 이면 --journal-option 모드 (단일 다중필터 크롤). None이면 기존 저널별 순회.
    """
    # 진행 상황 추적기 생성 (resume 여부와 무관하게 항상 기록)
    progress = ProgressTracker(config.BASE_PATH, year)

    # CDP로 해당 연도 다운로드 경로 변경
    try:
        driver.execute_cdp_cmd('Browser.setDownloadBehavior', {
            'behavior': 'allow',
            'downloadPath': str(config.SAVE_PATH),
            'eventsEnabled': True,
        })
        print(f'[CDP] 다운로드 경로(Browser): {config.SAVE_PATH}')
    except Exception:
        driver.execute_cdp_cmd('Page.setDownloadBehavior', {
            'behavior': 'allow',
            'downloadPath': str(config.SAVE_PATH),
        })
        print(f'[CDP] 다운로드 경로(Page): {config.SAVE_PATH}')

    try:
        # ── --journal-option 모드: 다중 필터를 한 번에 적용해 단일 크롤 ─────
        if journal_option is not None:
            opt_labels = {'all': '필터 없음 전체', 1: 'Remote Sensing 전체',
                          2: '4개 고정 저널', 3: '상위 5개', 4: '상위 10개'}
            label = f'[OPT{journal_option}] {opt_labels.get(journal_option, "?")}'
            start_page = progress.get_start_page(label, resume)

            print(f"\n{'#'*60}")
            print(f'# [journal-option {journal_option}] {label}  (p.{start_page}~)')
            print(f"{'#'*60}")

            stats = CrawlStats(year=year, journal=label)
            try:
                _crawl_with_journal_option(driver, year, config, username, password,
                                           journal_option, stats,
                                           progress=progress, start_page=start_page)
            except KeyboardInterrupt:
                stats.finalize()
                write_stats_row(stats)
                raise
            except Exception as e:
                ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f'[ERROR] journal-option{journal_option} 크롤링 실패 [{ts}]: {e}')
                traceback.print_exc()
            finally:
                stats.finalize()
                write_stats_row(stats)

            # journal_option 모드에서는 키워드 크롤링도 이어서 실행 가능
            # (keyword_targets 가 주어진 경우 아래 키워드 루프로 낙하)

        else:
            # ── 기존 저널별 순회 모드 ──────────────────────────────────────
            if journal_targets is None:
                n = num_journals if num_journals is not None else 30
                journal_targets = JOURNAL_TARGETS_ALL[:n]

            if resume:
                progress.show_summary(journal_targets)

            for idx, (search_term, label_match) in enumerate(journal_targets, 1):
                # resume 모드: 시작 페이지 결정
                start_page = progress.get_start_page(label_match, resume)

                print(f"\n{'#'*60}")
                print(f'# [{idx}/{len(journal_targets)}] {label_match}  (p.{start_page}~)')
                print(f"{'#'*60}")

                stats = CrawlStats(year=year, journal=label_match)
                try:
                    _crawl_one_journal(driver, year, config, username, password,
                                       search_term, label_match, stats,
                                       progress=progress, start_page=start_page)
                except KeyboardInterrupt:
                    stats.finalize()
                    write_stats_row(stats)
                    raise
                except Exception as e:
                    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f'[ERROR] {label_match} 크롤링 실패 [{ts}]: {e}')
                    traceback.print_exc()
                finally:
                    stats.finalize()
                    write_stats_row(stats)

                # 저널 간 짧은 대기
                if idx < len(journal_targets):
                    print('[대기] 다음 저널 전 15초 대기...')
                    time.sleep(15)

            end_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n{'='*60}")
            print(f'{year}년 저널 크롤링 완료!  저장 경로: {config.SAVE_PATH}')
            print(f'종료 시각: {end_ts}')
            print(f"{'='*60}\n")

        # ── 키워드 기반 추가 크롤링 (journal_option 모드에서도 실행 가능) ───
        if keyword_targets:
            print(f"\n{'#'*60}")
            print(f'# {year}년 키워드 기반 크롤링 시작 ({len(keyword_targets)}개 키워드)')
            print(f"{'#'*60}\n")

            for kw_idx, keyword in enumerate(keyword_targets, 1):
                label = f'[KW] {keyword}'
                start_page = progress.get_start_page(label, resume)

                print(f"\n{'#'*60}")
                print(f'# [KW {kw_idx}/{len(keyword_targets)}] "{keyword}"  (p.{start_page}~)')
                print(f"{'#'*60}")

                stats = CrawlStats(year=year, journal=label)
                try:
                    _crawl_by_keyword(driver, year, config, username, password,
                                      keyword, stats,
                                      progress=progress, start_page=start_page)
                except KeyboardInterrupt:
                    stats.finalize()
                    write_stats_row(stats)
                    raise
                except Exception as e:
                    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f'[ERROR] 키워드 "{keyword}" 크롤링 실패 [{ts}]: {e}')
                    traceback.print_exc()
                finally:
                    stats.finalize()
                    write_stats_row(stats)

                if kw_idx < len(keyword_targets):
                    print('[대기] 다음 키워드 전 10초 대기...')
                    time.sleep(10)

            kw_end_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n{'='*60}")
            print(f'{year}년 키워드 크롤링 완료!  종료 시각: {kw_end_ts}')
            print(f"{'='*60}\n")

    except KeyboardInterrupt:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'\n[INTERRUPTED] 사용자 중단  [{ts}]')
        raise
    except Exception as e:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'\n[ERROR] {year}년 크롤링 실패  [{ts}]: {e}')
        traceback.print_exc()
        raise


def crawl_year(year, username, password, save_base_path, headless=False):
    """단일 연도 크롤링 (드라이버 생성·로그인 포함). 단독 실행 또는 외부 호출용."""
    logger = None
    orig_stdout = sys.stdout
    if headless:
        logger = setup_file_logger(save_base_path, year)
        sys.stdout = logger

    start_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'='*60}")
    print(f'{year}년 IEEE TGRS 논문 크롤링 시작  [{start_ts}]')
    print(f"{'='*60}\n")

    config = CrawlConfig(year, save_base_path)
    driver = setup_chrome_driver(str(config.SAVE_PATH), headless=headless)

    try:
        if not login_kookmin_library(driver, username, password):
            print(f'\n[ERROR] {year}년: 도서관 로그인 실패')
            return
        if not access_ieee_via_library(driver):
            print(f'\n[ERROR] {year}년: IEEE 접속 실패')
            return
        _do_year_crawl(driver, year, config, username, password)
    except KeyboardInterrupt:
        pass  # _do_year_crawl 에서 이미 출력
    except Exception:
        pass  # _do_year_crawl 에서 이미 출력
    finally:
        driver.quit()
        if logger:
            sys.stdout = orig_stdout
            logger.close()


# ==================== credentials.json 로드 ====================
def load_credentials(cred_file='credentials.json'):
    for path in [Path(cred_file), Path(__file__).parent / cred_file]:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            uid = data.get('univ_id', '').strip()
            upw = data.get('univ_pw', '').strip()
            if uid and upw and uid not in ('학번 또는 ID', ''):
                return uid, upw
    return None, None


# ==================== CLI ====================
def parse_args():
    default_save = (
        DEFAULT_SAVE_PATH_WINDOWS if platform.system() == 'Windows'
        else DEFAULT_SAVE_PATH_LINUX
    )

    parser = argparse.ArgumentParser(
        description='IEEE 논문 대용량 크롤러 (국민대 성곡도서관 프록시)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
실행 예시:
  python crawling_ieee_2023_2025.py --years 2023 2024 2025
  python crawling_ieee_2023_2025.py --headless --years 2023 2024 2025

  # 중단 후 재개
  python crawling_ieee_2023_2025.py --headless --resume --years 2023 2024 2025

  # 저널 수 지정 (초분광 관련도 순위 기준 상위 N개)
  python crawling_ieee_2023_2025.py --headless --num-journals 50 --years 2023 2024 2025

  # 저널 + 키워드 기반 동시 크롤링 (PDF 수집량 대폭 확대)
  python crawling_ieee_2023_2025.py --headless --num-journals 30 --with-keywords --years 2024 2025

  # 키워드 기반 크롤링만 실행 (저널 크롤링 건너뜀)
  python crawling_ieee_2023_2025.py --headless --keywords-only --years 2024 2025

  # 저널 선택 옵션 사용 (--journal-option)
  # option all: 필터 없이 전체 다운로드 (Publication Title 필터 미적용)
  python crawling_ieee_2023_2025.py --headless --journal-option all --years 2024 2025
  # option all + 전체 연도: 연도·저널 필터 없이 IEEE 전체 다운로드
  python crawling_ieee_2023_2025.py --headless --journal-option all --years all
  # option1: "Remote Sensing" 검색 → 나오는 저널 모두 체크 후 일괄 크롤
  python crawling_ieee_2023_2025.py --headless --journal-option 1 --years 2024 2025
  # option2: IEEE Access / Sensors Journal / IGARSS / TGRS 4개 고정 일괄 크롤
  python crawling_ieee_2023_2025.py --headless --journal-option 2 --years 2024 2025
  # option3: 검색 없이 Publication Title 상위 5개 일괄 크롤
  python crawling_ieee_2023_2025.py --headless --journal-option 3 --years 2023 2024 2025
  # option4: 검색 없이 Publication Title 상위 10개 일괄 크롤
  python crawling_ieee_2023_2025.py --headless --journal-option 4 --years 2023 2024 2025
  # 전체 연도 단독 사용 (연도 필터 없이 저널 기반 크롤)
  python crawling_ieee_2023_2025.py --headless --num-journals 10 --years all

  # 진행 상황만 출력
  python crawling_ieee_2023_2025.py --status --years 2023 2024 2025

  python crawling_ieee_2023_2025.py --year 2024 --save-path /my/dir
  python crawling_ieee_2023_2025.py --year 2023 --username myid --password mypw
        """
    )
    parser.add_argument(
        '--headless', action='store_true',
        help='브라우저를 화면 없이 백그라운드로 실행 (서버 환경)'
    )
    parser.add_argument(
        '--resume', action='store_true',
        help='이전 실행에서 중단된 지점부터 재개 (progress_YEAR.json 참조)'
    )
    parser.add_argument(
        '--status', action='store_true',
        help='크롤링 진행 상황만 출력하고 종료 (실제 크롤링 안 함)'
    )
    parser.add_argument(
        '--num-journals', type=int, default=30,
        choices=[10, 15, 20, 25, 30, 35, 40, 45, 50],
        metavar='{10,15,20,25,30,35,40,45,50}',
        help='크롤링할 저널 수 (초분광 관련도 순위 상위 N개, 기본값: 30)'
    )
    parser.add_argument(
        '--with-keywords', action='store_true',
        help='저널 크롤링 후 키워드 기반 추가 크롤링 실행 (PDF 수집량 대폭 확대)'
    )
    parser.add_argument(
        '--keywords-only', action='store_true',
        help='키워드 기반 크롤링만 실행 (저널 크롤링 건너뜀)'
    )
    parser.add_argument(
        '--journal-option', type=str, default=None,
        choices=['1', '2', '3', '4', 'all'],
        metavar='{1,2,3,4,all}',
        help=(
            '저널/학회 선택 방식 지정 (기본값: 없음 → --num-journals 로 순위 기반 순회).\n'
            '  all = Publication Title 필터 없이 전체 다운로드\n'
            '  1   = Publication Title 검색창에 "Remote Sensing" 입력 → 나오는 항목 전체 체크 후 일괄 크롤\n'
            '  2   = 4개 고정 저널 일괄 체크 (IEEE Access / Sensors Journal / IGARSS / TGRS)\n'
            '  3   = 검색 없이 Publication Title 상위 5개 체크 후 일괄 크롤\n'
            '  4   = 검색 없이 Publication Title 상위 10개 체크 후 일괄 크롤'
        )
    )
    parser.add_argument('--year',  type=str, default=None,
                        help='크롤링 단일 연도 (예: 2024)')
    parser.add_argument('--years', type=str, nargs='+', default=None,
                        help='크롤링 연도 목록 (예: --years 2023 2024 2025, 또는 --years all)')
    parser.add_argument('--save-path', default=None,
                        help=f'저장 기본 경로 (기본값: {default_save})')
    parser.add_argument('--username', default=None, help='도서관 로그인 ID')
    parser.add_argument('--password', default=None, help='도서관 로그인 비밀번호')
    return parser.parse_args()


# ==================== 메인 ====================
def main():
    args = parse_args()

    # 연도 결정 ('all' 포함 처리)
    if args.year and args.years:
        print('[오류] --year 와 --years 를 동시에 사용할 수 없습니다.')
        sys.exit(1)
    elif args.year:
        raw_years = [args.year]
    elif args.years:
        raw_years = args.years
    else:
        raw_years = ['2023', '2024', '2025']
        print(f'[INFO] 연도 미지정 → 기본값: {raw_years}')

    # 'all' 이면 ['all'] 유지, 아니면 int 변환
    if len(raw_years) == 1 and raw_years[0].lower() == 'all':
        years = ['all']
    else:
        try:
            years = [int(y) for y in raw_years]
        except ValueError:
            print(f'[오류] --years 에 유효하지 않은 값 포함: {raw_years}  (숫자 또는 all 만 허용)')
            sys.exit(1)

    # 저장 경로
    if args.save_path:
        save_base_path = args.save_path
    elif platform.system() == 'Windows':
        save_base_path = DEFAULT_SAVE_PATH_WINDOWS
    else:
        save_base_path = DEFAULT_SAVE_PATH_LINUX

    # --num-journals / --keywords-only / --journal-option 처리
    num_journals   = args.num_journals
    with_keywords  = args.with_keywords
    keywords_only  = args.keywords_only
    # journal_option: 'all' 그대로 유지, 숫자 문자열은 int 변환
    _jopt_raw = args.journal_option
    if _jopt_raw is None:
        journal_option = None
    elif _jopt_raw == 'all':
        journal_option = 'all'
    else:
        journal_option = int(_jopt_raw)

    if keywords_only and with_keywords:
        print('[오류] --with-keywords 와 --keywords-only 를 동시에 사용할 수 없습니다.')
        sys.exit(1)

    if journal_option is not None and (with_keywords or keywords_only):
        print('[오류] --journal-option 은 --with-keywords / --keywords-only 와 동시에 사용할 수 없습니다.')
        sys.exit(1)

    # 실제 사용할 저널 수 결정 (--journal-option 지정 시 저널 목록 사용 안 함)
    effective_num_journals = 0 if (keywords_only or journal_option is not None) else num_journals
    effective_keywords     = KEYWORD_SEARCH_TERMS if (with_keywords or keywords_only) else None
    effective_targets      = JOURNAL_TARGETS_ALL[:effective_num_journals] if effective_num_journals > 0 else []

    # --status: 진행 상황만 출력하고 종료
    if args.status:
        print('\n[진행 상황 조회]')
        for year in years:
            pt = ProgressTracker(save_base_path, year)
            pt.show_summary(effective_targets or JOURNAL_TARGETS_ALL[:num_journals])
        return

    # 로그인 정보
    username = args.username
    password = args.password

    if not username or not password:
        uid, upw = load_credentials()
        if uid and upw:
            username = username or uid
            password = password or upw
            print(f'[INFO] credentials.json 로드 완료 (ID: {username})')
        else:
            print('[오류] 로그인 정보가 없습니다.')
            print('  → credentials.json 에 univ_id / univ_pw 를 설정하거나')
            print('  → --username / --password 옵션을 사용하세요.')
            sys.exit(1)

    # 시작 요약
    resume_flag = getattr(args, 'resume', False)
    if journal_option is not None:
        jopt_names = {1: 'Remote Sensing 전체', 2: '4개 고정 저널', 3: '상위 5개', 4: '상위 10개'}
        crawl_mode = f'저널옵션{journal_option} ({jopt_names.get(journal_option, "?")})'
    elif keywords_only:
        crawl_mode = '키워드만'
    elif with_keywords:
        crawl_mode = '저널+키워드'
    else:
        crawl_mode = '저널만'
    print('\n' + '='*60)
    print('IEEE 논문 대용량 크롤러 시작')
    print('='*60)
    years_display = '전체 연도 (필터 없음)' if years == ['all'] else str(years)
    print(f'  브라우저    : {"headless" if args.headless else "GUI (브라우저 화면 표시)"}')
    print(f'  대상 연도   : {years_display}')
    print(f'  크롤링 모드 : {crawl_mode}')
    if journal_option is None and not keywords_only:
        print(f'  저널 수     : {effective_num_journals}개 (초분광 관련도 순위 상위)')
    if effective_keywords:
        print(f'  키워드 수   : {len(effective_keywords)}개')
    print(f'  재개 모드   : {"ON (--resume)" if resume_flag else "OFF (처음부터)"}')
    print(f'  저장 경로   : {save_base_path}')
    print(f'  통계 경로   : {MANAGE_FILES_PATH}')
    print(f'  로그인 ID   : {username}')
    print('='*60 + '\n')

    # 드라이버 1회 생성 → 로그인 1회 → 연도별 루프 (연도마다 재로그인 불필요)
    first_config = CrawlConfig(years[0], save_base_path)
    driver = setup_chrome_driver(str(first_config.SAVE_PATH), headless=args.headless)

    try:
        if not login_kookmin_library(driver, username, password):
            print('[오류] 도서관 로그인 실패')
            return
        if not access_ieee_via_library(driver):
            print('[오류] IEEE 접속 실패')
            return

        for year in years:
            print(f"\n{'#'*60}")
            print(f'# {year}년 크롤링 시작  [{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]')
            print(f"{'#'*60}\n")

            config = CrawlConfig(year, save_base_path)

            # headless 모드 - 연도별 로그 파일 설정
            logger = None
            orig_stdout = sys.stdout
            if args.headless:
                logger = setup_file_logger(save_base_path, year)
                sys.stdout = logger

            interrupted = False
            try:
                _do_year_crawl(driver, year, config, username, password,
                               journal_targets=effective_targets if effective_targets else None,
                               num_journals=effective_num_journals,
                               keyword_targets=effective_keywords,
                               resume=resume_flag,
                               journal_option=journal_option)
            except KeyboardInterrupt:
                interrupted = True
            except Exception:
                pass  # _do_year_crawl 에서 이미 출력
            finally:
                if logger:
                    sys.stdout = orig_stdout
                    logger.close()

            if interrupted:
                break

            if year != years[-1]:
                print('\n[대기] 다음 연도 전 30초 대기...')
                time.sleep(30)

    except KeyboardInterrupt:
        print('[INTERRUPTED] 사용자 중단')
    finally:
        driver.quit()

    print(f"\n{'#'*60}")
    print(f'# 모든 연도 크롤링 완료!  [{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]')
    print(f"{'#'*60}")


if __name__ == '__main__':
    main()
