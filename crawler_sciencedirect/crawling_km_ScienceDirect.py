#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ScienceDirect(Elsevier) 논문 PDF 대용량 크롤러
국민대학교 성곡도서관 → 학술정보DB → ScienceDirect 프록시

흐름:
  1. 도서관 로그인  https://lib.kookmin.ac.kr/login?...
  2. ScienceDirect DB 페이지 이동 → 링크 클릭 → 새 창으로 SD 프록시 열림
  3. 저널별 검색 URL로 이동 (연도 + articleTypes=FLA 필터)
  4. 페이지별 전체 선택 → PDF 다운로드

실행 예시:
  # 기본 (Remote Sensing of Environment, 2023년, headless)
  python crawling_km_ScienceDirect.py --headless --years 2023

  # 여러 연도
  python crawling_km_ScienceDirect.py --headless --years 2022 2023 2024

  # 전체 연도 (연도 필터 없음)
  python crawling_km_ScienceDirect.py --headless --years all

  # 저널 옵션 (1=RSE, 2=상위4개, 3=상위8개, all=전체15개)
  python crawling_km_ScienceDirect.py --headless --years 2023 --journal-option 2

  # 재개
  python crawling_km_ScienceDirect.py --headless --years 2023 --resume

  # 진행 상황 확인
  python crawling_km_ScienceDirect.py --status --years 2023
"""

import os
import re
import sys
import json
import time
import csv
import shutil
import argparse
import warnings
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

warnings.filterwarnings('ignore')


# ==================== 상수 ====================
DEFAULT_SAVE_PATH = '/nas1/hyperspectral_literature_data_collected/02_ScienceDirect'
MANAGE_FILES_PATH = Path('/nas1/hyperspectral_literature_data_collected/02_ScienceDirect_logs/manage_files')

# 국민대 도서관 URL / Selector
LOGIN_URL      = 'https://lib.kookmin.ac.kr/login?returnUrl=%3F&queryParamsHandling=merge'
DB_SEARCH_URL  = 'https://lib.kookmin.ac.kr/search/database?keyword=ScienceDirect'
CSS_ID_FIELD   = 'input[formcontrolname="portalUserId"]'
CSS_PW_FIELD   = 'input[formcontrolname="portalPassword"]'
XPATH_LOGIN_BTN = '//button[@type="submit" and normalize-space(.)="로그인"]'

CHROME_BIN       = '/data/khkim/chrome_local/chrome_extracted/opt/google/chrome/google-chrome'
CHROMEDRIVER_BIN = '/data/khkim/chrome_local/chromedriver-linux64/chromedriver'

# ScienceDirect 프록시 베이스 URL (자동 발견 후 설정됨)
SD_PROXY_BASE = ''

# 다운로드 대기 (ScienceDirect는 ZIP 한 건씩 내려받음, 최대 20개/페이지)
DOWNLOAD_WAIT_SECONDS = 300
PAGE_CHANGE_DELAY     = 5


# ==================== 대상 저널 목록 (HSI/RS 관련도 순위) ====================
# 형식: (라벨, ScienceDirect pub 파라미터 값, 설명)
JOURNAL_TARGETS = [
    # Tier 1: 핵심 원격탐사 저널
    ('Remote Sensing of Environment',
     'Remote Sensing of Environment',
     'Elsevier 최상위 원격탐사 저널'),
    ('ISPRS Journal of Photogrammetry and Remote Sensing',
     'ISPRS Journal of Photogrammetry and Remote Sensing',
     'ISPRS 원격탐사·사진측량'),
    ('International Journal of Applied Earth Observation and Geoinformation',
     'International Journal of Applied Earth Observation and Geoinformation',
     'JAG — 지구관측 응용'),
    ('Advances in Space Research',
     'Advances in Space Research',
     '우주·지구관측 응용'),

    # Tier 2: 영상처리·딥러닝
    ('Information Fusion',
     'Information Fusion',
     '멀티소스 데이터 융합'),
    ('Pattern Recognition',
     'Pattern Recognition',
     '패턴인식·머신러닝'),
    ('Neural Networks',
     'Neural Networks',
     '신경망·딥러닝'),
    ('Signal Processing',
     'Signal Processing',
     '신호처리'),

    # Tier 3: 컴퓨터과학 응용
    ('Neurocomputing',
     'Neurocomputing',
     '뉴로컴퓨팅·딥러닝 응용'),
    ('Expert Systems with Applications',
     'Expert Systems with Applications',
     '전문가 시스템 응용'),
    ('Knowledge-Based Systems',
     'Knowledge-Based Systems',
     '지식기반 시스템'),
    ('Computers and Geosciences',
     'Computers & Geosciences',
     '지구과학 컴퓨팅'),
    ('Computer Vision and Image Understanding',
     'Computer Vision and Image Understanding',
     '컴퓨터 비전·영상 이해'),
    ('Image and Vision Computing',
     'Image and Vision Computing',
     '영상·비전 컴퓨팅'),
    ('International Journal of Remote Sensing Applications',
     'The Egyptian Journal of Remote Sensing and Space Sciences',
     '원격탐사 응용'),
]


# ==================== 로거 ====================
class TeeLogger:
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
    log_dir = Path(str(save_base_path) + '_logs') / str(year)
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = log_dir / f'crawl_sd_{year}_{ts}.log'
    logger = TeeLogger(str(log_path))
    print(f'[LOG] 로그 파일: {log_path}')
    return logger


def _year_label(year):
    return '전체 연도' if str(year) == 'all' else f'{year}년'


# ==================== 통계 ====================
class CrawlStats:
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
        self.year_crawled    = str(year)
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
        now = datetime.now()
        end_t   = self.end_time or now.strftime('%H:%M:%S')
        elapsed = self.elapsed_minutes if self.elapsed_minutes else \
                  round((now - self._start_dt).total_seconds() / 60, 2)
        return {
            'date': self.date, 'start_time': self.start_time,
            'end_time': end_t, 'elapsed_minutes': elapsed,
            'year_crawled': self.year_crawled, 'journal': self.journal,
            'pages_processed': self.pages_processed,
            'pages_skipped': self.pages_skipped,
            'zip_downloads': self.zip_downloads,
            'pdfs_extracted': self.pdfs_extracted,
            'duplicates_skipped': self.duplicates_skipped,
            'select_all_failures': self.select_all_failures,
            'download_failures': self.download_failures,
            'session_relogins': self.session_relogins,
        }

    def checkpoint(self):
        try:
            MANAGE_FILES_PATH.mkdir(parents=True, exist_ok=True)
            ym = datetime.now().strftime('%Y_%m')
            csv_path = MANAGE_FILES_PATH / f'stats_sd_{ym}.csv'
            session_key = (self.date, self.start_time, str(self.year_crawled), self.journal)
            rows = []
            found = False
            if csv_path.exists():
                with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                    for row in csv.DictReader(f):
                        key = (row.get('date',''), row.get('start_time',''),
                               row.get('year_crawled',''), row.get('journal',''))
                        rows.append(self.as_row() if key == session_key else row)
                        if key == session_key:
                            found = True
            if not found:
                rows.append(self.as_row())
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=CrawlStats.CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
        except Exception as e:
            print(f'[경고] 통계 저장 실패: {e}')


def write_stats_row(stats):
    stats.checkpoint()
    print(f'[STATS] stats_sd_{datetime.now().strftime("%Y_%m")}.csv 최종 저장 완료')


# ==================== 진행 상황 추적 ====================
class ProgressTracker:
    def __init__(self, year):
        self.year = str(year)
        MANAGE_FILES_PATH.mkdir(parents=True, exist_ok=True)
        self.path = MANAGE_FILES_PATH / f'progress_sd_{year}.json'
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

    def get_start_page(self, label, resume):
        if not resume or label not in self.data:
            return 1
        entry = self.data[label]
        status = entry.get('status', '')
        last_pg = entry.get('last_page_completed', 0)
        if status == 'completed':
            start = last_pg + 1
            print(f'[RESUME] {label[:40]}: 완료 → 신규 체크 p.{start}~')
            return start
        elif status == 'in_progress':
            start = max(1, last_pg + 1)
            print(f'[RESUME] {label[:40]}: 진행중 → p.{start} 재개')
            return start
        return 1

    def update(self, label, page_num, pdfs, status='in_progress'):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if label not in self.data:
            self.data[label] = {'started_at': now}
        self.data[label].update({
            'status': status,
            'last_page_completed': page_num,
            'pdfs_downloaded': pdfs,
            'last_updated': now,
        })
        self.save()

    def mark_completed(self, label, total_pages, total_pdfs):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.data.setdefault(label, {}).update({
            'status': 'completed',
            'last_page_completed': total_pages,
            'total_pages_found': total_pages,
            'total_pdfs': total_pdfs,
            'completed_at': now,
            'last_updated': now,
        })
        self.save()

    def show_summary(self):
        print(f'\n[진행 상황] {self.path.name}')
        total = len(JOURNAL_TARGETS)
        completed   = sum(1 for v in self.data.values() if v.get('status') == 'completed')
        in_progress = sum(1 for v in self.data.values() if v.get('status') == 'in_progress')
        print(f'  전체 {total}개 | 완료 {completed} | 진행중 {in_progress} | 미시작 {total - len(self.data)}')
        for label, info in self.data.items():
            st  = info.get('status', '?')
            pg  = info.get('last_page_completed', 0)
            pdf = info.get('pdfs_downloaded', 0)
            upd = info.get('last_updated', '')[:16]
            print(f'  {st:12s} | p.{pg:4d} | {pdf:6d} PDFs | {upd} | {label[:50]}')
        print()


# ==================== Chrome 드라이버 ====================
def setup_chrome_driver(download_dir, headless=False):
    chrome_local_tmp = Path('/data/khkim/chrome_tmp')
    chrome_local_tmp.mkdir(parents=True, exist_ok=True)
    os.environ['TMPDIR'] = str(chrome_local_tmp)

    chrome_profile_dir = chrome_local_tmp / '.chrome_profile_sd'
    if chrome_profile_dir.exists():
        try:
            shutil.rmtree(str(chrome_profile_dir))
        except Exception:
            for lock in ['SingletonLock', 'SingletonCookie', 'SingletonSocket']:
                lp = chrome_profile_dir / lock
                if lp.exists():
                    try:
                        lp.unlink()
                    except Exception:
                        pass
    chrome_profile_dir.mkdir(parents=True, exist_ok=True)

    options = Options()
    options.add_argument(f'--user-data-dir={chrome_profile_dir}')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')

    if headless:
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
    else:
        options.add_argument('--start-maximized')

    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1920,1080')
    options.add_argument(
        '--user-agent=Mozilla/5.0 (X11; Linux x86_64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    )
    options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
    options.add_experimental_option('useAutomationExtension', False)

    prefs = {
        'download.default_directory': download_dir,
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': True,
        'plugins.always_open_pdf_externally': True,
    }
    options.add_experimental_option('prefs', prefs)

    if os.path.exists(CHROME_BIN):
        options.binary_location = CHROME_BIN
        service = Service(CHROMEDRIVER_BIN)
    else:
        service = Service()

    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        # CDP 다운로드 경로 설정
        driver.execute_cdp_cmd('Page.setDownloadBehavior', {
            'behavior': 'allow',
            'downloadPath': download_dir,
        })
        print(f'[Chrome] 드라이버 초기화 완료 ({"headless" if headless else "GUI"})')
        return driver
    except Exception as e:
        print(f'[오류] Chrome 드라이버 초기화 실패: {e}')
        sys.exit(1)


# ==================== 1단계: 국민대 도서관 로그인 ====================
def login_kookmin_library(driver, username, password):
    print('\n' + '='*60)
    print('1단계: 국민대 성곡도서관 로그인')
    print('='*60)
    try:
        driver.get(LOGIN_URL)
        time.sleep(5)
        id_field = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, CSS_ID_FIELD))
        )
        id_field.clear()
        id_field.send_keys(username)
        print(f'[OK] ID 입력: {username}')
        time.sleep(0.5)

        pw_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, CSS_PW_FIELD))
        )
        pw_field.clear()
        pw_field.send_keys(password)
        print('[OK] 비밀번호 입력')
        time.sleep(0.5)

        login_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, XPATH_LOGIN_BTN))
        )
        try:
            overlay = driver.find_element(By.CSS_SELECTOR, '.cdk-overlay-backdrop')
            driver.execute_script('arguments[0].click();', overlay)
            time.sleep(1)
        except Exception:
            pass
        try:
            login_btn.click()
        except Exception:
            driver.execute_script('arguments[0].click();', login_btn)
        print('[OK] 로그인 버튼 클릭')
        time.sleep(4)
        print(f'[OK] 로그인 완료  현재 URL: {driver.current_url}\n')
        return True
    except Exception as e:
        print(f'[오류] 로그인 실패: {e}')
        return False


# ==================== 2단계: ScienceDirect 접속 ====================
def access_sd_via_library(driver):
    """도서관 학술정보DB → ScienceDirect 링크 클릭 → 새 창 전환.

    성공 시 전역 SD_PROXY_BASE 설정 후 True 반환.
    """
    global SD_PROXY_BASE
    KIST_WAIT_SECS = [120, 300]

    print('\n' + '='*60)
    print('2단계: 학술정보DB → ScienceDirect 접속')
    print('='*60)

    def _click_sd_link():
        driver.get(DB_SEARCH_URL)
        sd_link = None
        for _ in range(20):
            time.sleep(1)
            for lnk in driver.find_elements(By.TAG_NAME, 'a'):
                t = lnk.text.strip()
                if 'ScienceDirect' in t or 'Elsevier' in t or 'Science Direct' in t:
                    sd_link = lnk
                    break
            if sd_link:
                break
        if not sd_link:
            return None, None
        print(f'[OK] ScienceDirect 링크 발견: {sd_link.text[:60]}')
        before = set(driver.window_handles)
        lib_h  = driver.current_window_handle
        driver.execute_script('arguments[0].click();', sd_link)
        print('[OK] 링크 클릭 → 새 창 대기 중...')
        try:
            WebDriverWait(driver, 15).until(lambda d: len(d.window_handles) > len(before))
        except Exception:
            return None, lib_h
        new_h = (set(driver.window_handles) - before).pop()
        return new_h, lib_h

    try:
        new_h, lib_h = _click_sd_link()
        if not new_h:
            raise Exception('ScienceDirect 링크 없음 또는 새 창 미열림')

        driver.switch_to.window(new_h)
        time.sleep(15)
        print('[OK] ScienceDirect 창 전환 완료')

        # KIST 차단 감지 시 재시도
        for _ki, wait_sec in enumerate(KIST_WAIT_SECS):
            if 'kist.kookmin.ac.kr' not in driver.current_url:
                break
            print(f'[경고] KIST 차단 감지 ({_ki+1}/{len(KIST_WAIT_SECS)+1}): {driver.current_url}')
            print(f'  → KIST 창 닫기 → 도서관 복귀 → {wait_sec}초 대기 후 재시도')
            try:
                driver.close()
            except Exception:
                pass
            try:
                if lib_h and lib_h in driver.window_handles:
                    driver.switch_to.window(lib_h)
                else:
                    driver.switch_to.window(driver.window_handles[0])
            except Exception:
                pass
            time.sleep(wait_sec)
            new_h, lib_h = _click_sd_link()
            if not new_h:
                print('  → 재클릭 실패')
                break
            driver.switch_to.window(new_h)
            time.sleep(15)
            print(f'  → 재접속 URL: {driver.current_url}')

        if 'kist.kookmin.ac.kr' in driver.current_url:
            print('[경고] KIST 차단 해제 불가 → False')
            return False

        # 프록시 베이스 URL 추출
        cur = driver.current_url
        if 'sciencedirect' in cur.lower():
            # e.g. https://www-sciencedirect-com.proxy.kookmin.ac.kr/
            from urllib.parse import urlparse
            parsed = urlparse(cur)
            SD_PROXY_BASE = f'{parsed.scheme}://{parsed.netloc}'
            print(f'[OK] SD 프록시 베이스: {SD_PROXY_BASE}')
        else:
            print(f'[경고] ScienceDirect 프록시 URL 미확인 (현재: {cur})')

        print(f'현재 URL: {driver.current_url}\n')
        return True

    except Exception as e:
        print(f'[오류] ScienceDirect 접속 실패: {e}')
        return False


# ==================== 세션 만료 확인 ====================
def is_session_expired(driver):
    try:
        url = driver.current_url
        return any(p in url for p in [
            'kist.kookmin.ac.kr',
            'lib.kookmin.ac.kr/login',
            'sessionfail', 'exceptproc',
        ])
    except Exception:
        return False


# ==================== ScienceDirect 검색 설정 ====================
def build_search_url(journal_pub_param, year):
    """저널·연도 검색 URL 생성"""
    if not SD_PROXY_BASE:
        return None
    pub_enc = quote_plus(journal_pub_param)
    base = f'{SD_PROXY_BASE}/search?pub={pub_enc}&articleTypes=FLA'
    if str(year) != 'all':
        base += f'&date={year}'
    return base


def navigate_to_search(driver, journal_label, journal_pub_param, year):
    """검색 페이지 이동 및 결과 존재 확인. 성공 시 True."""
    url = build_search_url(journal_pub_param, year)
    if not url:
        print('[경고] SD 프록시 URL 미설정 → 검색 불가')
        return False
    print(f'[검색] {url}')
    driver.get(url)
    time.sleep(8)
    if is_session_expired(driver):
        return False
    return True


# ==================== 결과 수 파악 ====================
def get_total_results(driver):
    """현재 페이지 총 검색 결과 수 반환. 실패 시 -1."""
    try:
        # ScienceDirect 결과 수 표시 패턴 시도
        for selector in [
            "//h2[contains(@class,'search-body-results-count')]",
            "//*[contains(@class,'search-body-results-count')]",
            "//*[@data-aa-name='results-count-text']",
            "//div[contains(@class,'result-count')]",
            "//*[contains(text(),' results')]",
            "//*[contains(text(),' Results')]",
        ]:
            try:
                elems = driver.find_elements(By.XPATH, selector)
                for el in elems:
                    txt = el.text.strip()
                    m = re.search(r'([\d,]+)\s+[Rr]esult', txt)
                    if m:
                        return int(m.group(1).replace(',', ''))
            except Exception:
                pass
        # 페이지 소스에서 추출
        src = driver.page_source
        m = re.search(r'([\d,]+)\s+[Rr]esult', src)
        if m:
            return int(m.group(1).replace(',', ''))
        return -1
    except Exception:
        return -1


def get_current_page_number(driver):
    """현재 페이지 번호 반환. 기본 1."""
    try:
        for selector in [
            "//*[contains(text(),'Page') and contains(text(),' of ')]",
            "//*[contains(@aria-label,'Page') and contains(@aria-label,' of ')]",
        ]:
            elems = driver.find_elements(By.XPATH, selector)
            for el in elems:
                m = re.search(r'Page\s+(\d+)\s+of', el.text)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return 1


def has_search_results(driver):
    """검색 결과 있는지 확인"""
    try:
        # 결과 없음 메시지
        no_result_texts = ['No results found', '결과 없음', 'no results', '0 results']
        src_lower = driver.page_source.lower()
        for txt in no_result_texts:
            if txt.lower() in src_lower and 'no results' in src_lower:
                return False
        # 논문 아이템 존재 확인
        items = driver.find_elements(By.CSS_SELECTOR,
            'li.ResultItem, article.result-item, div.result-item, '
            'li[data-aa-name="result-list-item"]')
        return len(items) > 0
    except Exception:
        return True


# ==================== 페이지 처리 ====================
def select_all_results(driver):
    """전체 선택 체크박스 클릭. 성공 True."""
    selectors = [
        '#select-all-results',
        'input[id="select-all-results"]',
        'input[data-aa-name="select-all-results"]',
        'label[for="select-all-results"]',
        'input.select-all-results',
    ]
    for attempt in range(5):
        for sel in selectors:
            try:
                cb = WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                driver.execute_script(
                    'arguments[0].scrollIntoView({behavior:"instant",block:"center"});', cb)
                time.sleep(0.5)
                checked = (cb.get_attribute('aria-checked') == 'true' or
                           cb.get_attribute('checked') is not None or
                           cb.is_selected())
                if not checked:
                    driver.execute_script('arguments[0].click();', cb)
                    time.sleep(0.5)
                print('[OK] 전체 선택 완료')
                return True
            except Exception:
                pass
        if attempt == 1:
            driver.refresh()
            time.sleep(8)
    print('[경고] 전체 선택 실패')
    return False


def trigger_download(driver):
    """다운로드 버튼 클릭. 성공 True."""
    selectors = [
        'span.download-all-link-text',
        'button[data-aa-name="export-download-pdfs"]',
        'button[data-testid="export-download-pdfs"]',
        '*[aria-label*="Download"]',
        'button.export-all',
    ]
    for sel in selectors:
        try:
            el = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            # 부모 button 찾기
            try:
                btn = el.find_element(By.XPATH, './ancestor::button')
            except Exception:
                btn = el
            driver.execute_script(
                'arguments[0].scrollIntoView({behavior:"instant",block:"center"});', btn)
            driver.execute_script('arguments[0].click();', btn)
            print('[OK] 다운로드 버튼 클릭')
            return True
        except Exception:
            pass
    print('[경고] 다운로드 버튼 미발견')
    return False


def wait_for_download(download_dir, timeout=DOWNLOAD_WAIT_SECONDS):
    """다운로드 완료 대기. 완료된 파일 목록 반환."""
    deadline = time.time() + timeout
    crdownload_extra = 0
    while time.time() < deadline + crdownload_extra:
        files = list(Path(download_dir).glob('*.crdownload')) + \
                list(Path(download_dir).glob('*.part'))
        if files:
            crdownload_extra = min(crdownload_extra + 60, 600)
            time.sleep(5)
            continue
        # 새로 생긴 zip/pdf 확인
        break
    return list(Path(download_dir).glob('*.zip')) + list(Path(download_dir).glob('*.pdf'))


def extract_zip(zip_path, extract_dir, stats):
    """ZIP 압축 해제 후 삭제. 추출된 PDF 수 반환."""
    extracted = 0
    try:
        with zipfile.ZipFile(str(zip_path), 'r') as zf:
            for name in zf.namelist():
                if not name.lower().endswith('.pdf'):
                    continue
                dest = Path(extract_dir) / Path(name).name
                if dest.exists():
                    stats.duplicates_skipped += 1
                    continue
                zf.extract(name, extract_dir)
                # 서브폴더 이동
                src = Path(extract_dir) / name
                if src != dest:
                    src.rename(dest)
                extracted += 1
                print(f'  [압축해제] {Path(name).name}')
        zip_path.unlink()
        print(f'[OK] zip 삭제: {zip_path.name}')
        return extracted
    except Exception as e:
        print(f'[경고] ZIP 처리 실패 ({zip_path.name}): {e}')
        return 0


def process_page(driver, page_num, download_dir, stats):
    """현재 페이지 전체 선택 → 다운로드 → ZIP 처리. 성공 True."""
    print(f'\n{"="*60}')
    print(f'페이지 {page_num} 처리')
    print('='*60)

    before_zips = set(Path(download_dir).glob('*.zip'))
    before_pdfs = set(Path(download_dir).glob('*.pdf'))

    if not select_all_results(driver):
        stats.select_all_failures += 1
        return False

    if not trigger_download(driver):
        stats.download_failures += 1
        return False

    print(f'[대기] 다운로드 중... (최대 {DOWNLOAD_WAIT_SECONDS}초)')
    time.sleep(DOWNLOAD_WAIT_SECONDS)

    # ZIP 처리
    after_zips = set(Path(download_dir).glob('*.zip'))
    new_zips   = after_zips - before_zips
    extracted  = 0
    for zp in new_zips:
        extracted += extract_zip(zp, download_dir, stats)
        stats.zip_downloads += 1

    # 직접 다운로드된 PDF
    after_pdfs = set(Path(download_dir).glob('*.pdf'))
    new_pdfs   = after_pdfs - before_pdfs - {Path(download_dir) / z.stem for z in new_zips}
    direct_pdfs = len(new_pdfs)

    total_new = extracted + direct_pdfs
    stats.pdfs_extracted += total_new
    print(f'[OK] PDF 추출: {total_new}개  (ZIP {len(new_zips)}개, 직접 {direct_pdfs}개, 중복 {stats.duplicates_skipped}개)')
    stats.pages_processed += 1
    return True


def go_to_next_page(driver):
    """다음 페이지로 이동. 성공 시 새 페이지 번호 반환, 마지막이면 None."""
    try:
        btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "a[data-aa-name='srp-next-page'], "
                "a[aria-label='Next page'], "
                "button[aria-label='Next page']"))
        )
        driver.execute_script(
            'arguments[0].scrollIntoView({behavior:"instant",block:"center"});', btn)
        driver.execute_script('arguments[0].click();', btn)
        time.sleep(PAGE_CHANGE_DELAY)
        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        time.sleep(2)
        return get_current_page_number(driver)
    except TimeoutException:
        return None
    except Exception as e:
        print(f'[경고] 다음 페이지 이동 실패: {e}')
        return None


# ==================== 재로그인 ====================
def _relogin_and_setup(driver, journal_label, journal_pub_param, year,
                       config, username, password, stats):
    print('[재로그인] SD 세션 만료 → 재로그인')
    if stats:
        stats.session_relogins += 1
    if not login_kookmin_library(driver, username, password):
        return False
    if not access_sd_via_library(driver):
        return False
    if not navigate_to_search(driver, journal_label, journal_pub_param, year):
        return False
    return True


# ==================== 저널 크롤링 ====================
def crawl_one_journal(driver, journal_label, journal_pub_param, year,
                      save_path, username, password,
                      progress, stats, start_page=1):
    """단일 저널의 전 페이지 PDF 다운로드"""
    print(f'\n{"="*60}')
    print(f'저널 크롤링: {journal_label}  ({_year_label(year)}, p.{start_page}~)')
    print('='*60)

    if not navigate_to_search(driver, journal_label, journal_pub_param, year):
        if is_session_expired(driver):
            if not _relogin_and_setup(driver, journal_label, journal_pub_param,
                                      year, None, username, password, stats):
                return
        else:
            print('[경고] 검색 이동 실패 → 건너뜀')
            return

    if not has_search_results(driver):
        print(f'[완료] {journal_label}: 검색 결과 없음')
        return

    total = get_total_results(driver)
    if total > 0:
        print(f'[INFO] 총 {total:,}건 검색됨')

    # start_page > 1 이면 Next 버튼으로 이동
    current_page = get_current_page_number(driver)
    if start_page > current_page:
        print(f'[RESUME] 페이지 {start_page}로 이동 중...')
        for _ in range(start_page - current_page):
            nxt = go_to_next_page(driver)
            if nxt is None:
                print('[경고] 목표 페이지 도달 불가')
                return
        current_page = start_page

    visited = 0
    last_completed = current_page - 1
    consecutive_fails = 0
    MAX_CONSECUTIVE = 3

    while True:
        if is_session_expired(driver):
            if not _relogin_and_setup(driver, journal_label, journal_pub_param,
                                      year, None, username, password, stats):
                break
            # 복귀 페이지로 이동
            for _ in range(current_page - 1):
                go_to_next_page(driver)

        if not has_search_results(driver):
            print(f'[완료] {journal_label}: p.{current_page} 빈 페이지 → 종료')
            progress.mark_completed(journal_label, last_completed, stats.pdfs_extracted)
            break

        ok = process_page(driver, current_page, save_path, stats)
        if ok:
            consecutive_fails = 0
            last_completed = current_page
            progress.update(journal_label, current_page, stats.pdfs_extracted)
            stats.checkpoint()
        else:
            consecutive_fails += 1
            stats.pages_skipped += 1
            if consecutive_fails >= MAX_CONSECUTIVE:
                print(f'[중단] {consecutive_fails}페이지 연속 실패 → 저널 종료')
                break

        visited += 1
        nxt = go_to_next_page(driver)
        if nxt is None:
            print(f'[완료] {journal_label}: 마지막 페이지 → 종료')
            progress.mark_completed(journal_label, last_completed, stats.pdfs_extracted)
            break
        current_page = nxt

    stats.finalize()
    write_stats_row(stats)


# ==================== CLI 파싱 ====================
def parse_args():
    p = argparse.ArgumentParser(
        description='국민대 도서관 ScienceDirect PDF 대용량 크롤러')
    p.add_argument('--years', nargs='+', default=['2023'],
                   help='크롤링 연도 (복수 가능) 또는 all')
    p.add_argument('--year', type=str, help='단일 연도 (--years 와 동일)')
    p.add_argument('--headless', action='store_true', help='headless Chrome')
    p.add_argument('--resume', action='store_true', help='이전 진행 상황에서 재개')
    p.add_argument('--status', action='store_true', help='진행 상황 확인 후 종료')
    p.add_argument('--save-path', default=DEFAULT_SAVE_PATH)
    p.add_argument('--username', default=None)
    p.add_argument('--password', default=None)
    p.add_argument('--cred', default=None,
                   help='credentials.json 경로 (기본: 상위 hsi-paper-fetcher/ 폴더)')
    p.add_argument('--journal-option', type=str, default=None,
                   choices=['1', '2', '3', 'all'],
                   help='저널 범위: 1=RSE only, 2=상위4, 3=상위8, all=전체15개')
    return p.parse_args()


# ==================== main ====================
def main():
    args = parse_args()

    # 인증 정보
    # credentials.json 은 상위 hsi-paper-fetcher/ 폴더에 위치
    _HERE_MAIN = Path(__file__).parent
    _DEFAULT_CRED = _HERE_MAIN.parent / 'credentials.json'
    username, password = args.username, args.password
    if not username or not password:
        cred_path = Path(args.cred) if args.cred else _DEFAULT_CRED
        if cred_path.exists():
            cred = json.loads(cred_path.read_text(encoding='utf-8'))
            username = username or cred.get('username') or cred.get('univ_id')
            password = password or cred.get('password') or cred.get('univ_pw')
    if not username or not password:
        print('[오류] --username/--password 또는 credentials.json 필요')
        sys.exit(1)
    print(f'[INFO] 로그인 ID: {username}')

    # 연도 목록
    raw_years = args.years or ([args.year] if args.year else ['2023'])
    if 'all' in raw_years:
        years = ['all']
    else:
        years = []
        for y in raw_years:
            try:
                years.append(int(y))
            except ValueError:
                years.append(y)

    # 저널 목록 결정
    jopt = args.journal_option
    if jopt == '1':
        journals = JOURNAL_TARGETS[:1]
    elif jopt == '2':
        journals = JOURNAL_TARGETS[:4]
    elif jopt == '3':
        journals = JOURNAL_TARGETS[:8]
    else:
        journals = JOURNAL_TARGETS  # all

    save_path = args.save_path
    year_lbl  = '전체 연도' if years == ['all'] else ' / '.join(str(y) for y in years)

    print('\n' + '='*60)
    print('ScienceDirect PDF 크롤러 시작')
    print('='*60)
    print(f'  대상 연도  : {year_lbl}')
    print(f'  저널 범위  : {jopt or "all"} ({len(journals)}개)')
    print(f'  저장 경로  : {save_path}')
    print(f'  headless   : {args.headless}')
    print(f'  재개 모드  : {"ON" if args.resume else "OFF"}')
    print('='*60)

    for year in years:
        year_save_path = str(Path(save_path) / str(year))
        Path(year_save_path).mkdir(parents=True, exist_ok=True)

        if args.status:
            pt = ProgressTracker(year)
            pt.show_summary()
            continue

        logger = setup_file_logger(save_path, year)
        sys.stdout = logger

        driver = setup_chrome_driver(year_save_path, headless=args.headless)
        progress = ProgressTracker(year)

        try:
            if not login_kookmin_library(driver, username, password):
                print('[오류] 로그인 실패')
                continue
            if not access_sd_via_library(driver):
                print('[오류] ScienceDirect 접속 실패')
                continue

            for label, pub_param, _ in journals:
                stats = CrawlStats(year, label)
                start_page = progress.get_start_page(label, args.resume)

                crawl_one_journal(
                    driver, label, pub_param, year,
                    year_save_path, username, password,
                    progress, stats, start_page=start_page
                )
                time.sleep(5)

        except KeyboardInterrupt:
            print('\n[중단] 사용자 인터럽트')
        except Exception as e:
            print(f'[오류] 예외 발생: {e}')
            traceback.print_exc()
        finally:
            try:
                driver.quit()
            except Exception:
                pass
            if hasattr(logger, 'close'):
                logger.close()
            sys.stdout = logger.terminal if hasattr(logger, 'terminal') else sys.__stdout__

    print('\n[완료] 모든 연도 크롤링 종료')


if __name__ == '__main__':
    main()
