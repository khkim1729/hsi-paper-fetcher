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
import sys
import json
import time
import random
import platform
import argparse
import warnings
import traceback
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
        self.MAX_PAGE_VISITS        = 100
        self.MAX_SEAT_LIMIT_RETRIES = 5

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
    print('='*60)
    print(f'3단계: {year}년 논문 Advanced Search 설정')
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
        print(f'[오류] Advanced Search 설정 실패: {e}')
        return False


# ==================== 4단계: Publication 필터 ====================
def apply_publication_filter(driver, journal_name):
    print(f'4단계: 저널 필터 적용 - {journal_name}')

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
        # DOM 구조: <header> (grandparent of btn) > following-sibling > input[placeholder='Enter Title']
        search_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH,
                 "//button[normalize-space(.)='Publication Title']"
                 "/../../following-sibling::*//input[@placeholder='Enter Title' or @placeholder='Enter title']")
            )
        )
        search_input.clear()
        search_input.send_keys('Geoscience and Remote Sensing')
        time.sleep(4)  # 자동완성 결과 로딩 대기

        # 해당 저널 체크박스 레이블 클릭
        # "IEEE Transactions on Geoscience and Remote Sensing" 정확히 선택
        label = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH,
                 "//label[contains(normalize-space(), 'Transactions on Geoscience and Remote Sensing')]")
            )
        )
        driver.execute_script('arguments[0].click();', label)
        print('[OK] 저널 선택: ' + label.text[:60])
        time.sleep(2)

        # Apply 버튼 클릭 (displayed=True, enabled=True인 것 선택)
        # Year 필터용 Apply(disabled)와 Publication Title용 Apply(enabled) 중 enabled 것을 클릭
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


# ==================== 5단계: Items Per Page ====================
def set_items_per_page(driver, items=10):
    print(f'5단계: 페이지당 {items}개 항목 설정')

    try:
        dropdown = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "select[aria-label*='results per page']")
            )
        )
        driver.execute_script(f"arguments[0].value = '{items}';", dropdown)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", dropdown)
        print(f'[OK] 페이지당 {items}개 설정')
        time.sleep(5)
        return True

    except Exception as e:
        print(f'[오류] Items per page 설정 실패: {e}')
        return False


# ==================== 페이지 처리 ====================
def select_all_results(driver):
    try:
        # IEEE Xplore 결과 페이지의 "Select All on Page" 체크박스
        # class="xpl-checkbox-default results-actions-selectall-checkbox ..."
        select_all = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input.results-actions-selectall-checkbox")
            )
        )
        if not select_all.is_selected():
            driver.execute_script('arguments[0].click();', select_all)
            print('[OK] Select All on Page 클릭')
            time.sleep(2)
        return True
    except Exception as e:
        print(f'[오류] 전체 선택 실패: {e}')
        return False


def trigger_download(driver, config, page_number=1):
    try:
        save_dir = Path(config.SAVE_PATH)
        # 다운로드 전 기존 파일 목록 기록 (.crdownload 포함)
        existing = set(f.name for f in save_dir.iterdir() if f.is_file())

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

        # 3) 새로 나타난 파일(zip 또는 pdf)이 저장 폴더에 나타날 때까지 대기
        print(f'[대기] 다운로드 중... (최대 {config.DOWNLOAD_WAIT_SECONDS}초)')
        start_time = time.time()
        while time.time() - start_time < config.DOWNLOAD_WAIT_SECONDS:
            for f in save_dir.iterdir():
                if f.name in existing:
                    continue  # 이미 있던 파일 무시
                if f.suffix in ('.zip', '.pdf') and not f.name.endswith('.crdownload'):
                    sz = f.stat().st_size
                    print(f'[OK] 다운로드 완료: {f.name}  (페이지 {page_number}, {sz // 1024} KB)')
                    return True
            time.sleep(5)

        print('[경고] 다운로드 타임아웃')
        return False

    except Exception as e:
        print(f'[오류] 다운로드 실패: {e}')
        return False


def process_current_page(driver, page_number, config):
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
            if not select_all_results(driver):
                continue
            if not trigger_download(driver, config, page_number):
                continue

            print(f'[OK] 페이지 {page_number} 완료')
            random_delay(5, 15)
            return True

        except Exception as e:
            if check_seat_limit(driver):
                continue
            print(f'[오류] {e}')
            raise

    print(f'[실패] 페이지 {page_number}: Seat Limit 재시도 초과')
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


def go_to_next_page(driver, current_page, config):
    if check_seat_limit(driver):
        time.sleep(config.SEAT_LIMIT_WAIT_SECONDS)
        driver.refresh()
        time.sleep(5)

    next_page = current_page + 1
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
    time.sleep(2)

    try:
        btn = locate_page_button(driver, next_page)
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
        driver.execute_script('arguments[0].click();', btn)

        print(f'→ 페이지 {next_page} 이동')
        time.sleep(config.PAGE_CHANGE_DELAY)
        random_delay(1, 3)

        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        driver.execute_script('window.scrollTo(0, 0);')
        time.sleep(2)
        return next_page

    except:
        print(f'[경고] 페이지 {next_page} 버튼 미발견 → 크롤링 종료')
        return None


# ==================== 단일 연도 크롤링 ====================
def crawl_year(year, username, password, save_base_path, headless=False):
    # headless 모드일 때만 파일 로그 활성화
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
    driver = setup_chrome_driver(config.SAVE_PATH, headless=headless)

    try:
        if not login_kookmin_library(driver, username, password):
            raise Exception('도서관 로그인 실패')

        if not access_ieee_via_library(driver):
            raise Exception('IEEE 접속 실패')

        if not setup_ieee_advanced_search(driver, year):
            raise Exception('Advanced Search 실패')

        if not apply_publication_filter(driver, config.TARGET_JOURNAL):
            print('[경고] 저널 필터 건너뜀 - 전체 연도 결과로 진행')

        if not set_items_per_page(driver, 10):
            print('[경고] Items per page 설정 건너뜀 - 기본값으로 진행')

        current_page = config.START_PAGE
        visited_pages = 0

        while visited_pages < config.MAX_PAGE_VISITS:
            success = process_current_page(driver, current_page, config)

            if not success:
                print(f'[경고] 페이지 {current_page} 실패, 10분 대기 후 재시도')
                time.sleep(600)
                continue

            visited_pages += 1
            next_page = go_to_next_page(driver, current_page, config)
            if next_page is None:
                print(f'\n[완료] {year}년 모든 페이지 처리 완료!')
                break
            current_page = next_page

        end_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n{'='*60}")
        print(f'{year}년 크롤링 완료!  저장 경로: {config.SAVE_PATH}')
        print(f'종료 시각: {end_ts}')
        print(f"{'='*60}\n")

    except KeyboardInterrupt:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'\n[INTERRUPTED] 사용자 중단  [{ts}]  (페이지 {current_page if "current_page" in dir() else "?"}까지 완료)')
    except Exception as e:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'\n[ERROR] {year}년 크롤링 실패  [{ts}]: {e}')
        traceback.print_exc()
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
        description='IEEE TGRS 논문 크롤러 (국민대 성곡도서관 프록시)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
실행 예시:
  python crawling_ieee_2023_2025.py --years 2023 2024 2025
  python crawling_ieee_2023_2025.py --headless --years 2023 2024 2025
  python crawling_ieee_2023_2025.py --year 2024 --save-path /my/dir
  python crawling_ieee_2023_2025.py --year 2023 --username myid --password mypw
        """
    )
    parser.add_argument(
        '--headless', action='store_true',
        help='브라우저를 화면 없이 백그라운드로 실행 (서버 환경)'
    )
    parser.add_argument('--year',  type=int, default=None, help='크롤링 단일 연도 (예: 2024)')
    parser.add_argument('--years', type=int, nargs='+', default=None,
                        help='크롤링 연도 목록 (예: --years 2023 2024 2025)')
    parser.add_argument('--save-path', default=None,
                        help=f'저장 기본 경로 (기본값: {default_save})')
    parser.add_argument('--username', default=None, help='도서관 로그인 ID')
    parser.add_argument('--password', default=None, help='도서관 로그인 비밀번호')
    return parser.parse_args()


# ==================== 메인 ====================
def main():
    args = parse_args()

    # 연도 결정
    if args.year and args.years:
        print('[오류] --year 와 --years 를 동시에 사용할 수 없습니다.')
        sys.exit(1)
    elif args.year:
        years = [args.year]
    elif args.years:
        years = args.years
    else:
        years = [2023, 2024, 2025]
        print(f'[INFO] 연도 미지정 → 기본값: {years}')

    # 저장 경로
    if args.save_path:
        save_base_path = args.save_path
    elif platform.system() == 'Windows':
        save_base_path = DEFAULT_SAVE_PATH_WINDOWS
    else:
        save_base_path = DEFAULT_SAVE_PATH_LINUX

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
    print('\n' + '='*60)
    print('IEEE TGRS 논문 크롤러 시작')
    print('='*60)
    print(f'  브라우저    : {"headless" if args.headless else "GUI (브라우저 화면 표시)"}')
    print(f'  대상 연도   : {years}')
    print(f'  저장 경로   : {save_base_path}')
    print(f'  로그인 ID   : {username}')
    print('='*60 + '\n')

    for year in years:
        print(f"\n{'#'*60}")
        print(f'# {year}년 크롤링 시작  [{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]')
        print(f"{'#'*60}\n")

        try:
            crawl_year(year, username, password, save_base_path, headless=args.headless)
        except Exception as e:
            print(f'[오류] {year}년 크롤링 실패: {e}')
            continue

        if year != years[-1]:
            print('\n[대기] 다음 연도 전 30초 대기...')
            time.sleep(30)

    print(f"\n{'#'*60}")
    print(f'# 모든 연도 크롤링 완료!  [{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]')
    print(f"{'#'*60}")


if __name__ == '__main__':
    main()
