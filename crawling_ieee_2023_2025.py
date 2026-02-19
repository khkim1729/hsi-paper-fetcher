#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IEEE TGRS 논문 크롤링 (2023-2025)
국민대학교 성곡도서관 → 학술정보DB → IEEE

실행 예시:
  # Linux 서버 (headless, 기본)
  python crawling_ieee_2023_2025.py --mode linux --years 2023 2024 2025

  # Windows 로컬 PC (브라우저 화면 표시)
  python crawling_ieee_2023_2025.py --mode windows --years 2023 2024 2025

  # 단일 연도, 저장 경로 지정
  python crawling_ieee_2023_2025.py --mode linux --year 2024 --save-path /my/save/dir

  # credentials.json 대신 직접 입력
  python crawling_ieee_2023_2025.py --mode windows --year 2023 --username myid --password mypw
"""

import os
import sys
import json
import time
import random
import platform
import argparse
import warnings
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException
)

warnings.filterwarnings('ignore')

# ==================== 기본 저장 경로 ====================
DEFAULT_SAVE_PATH_LINUX   = '/nas1/hyperspectral_literature_data_collected/01_IEEE_TGRS_1980_2025'
DEFAULT_SAVE_PATH_WINDOWS = r'C:\Users\%USERNAME%\Downloads\IEEE_TGRS'


# ==================== 크롤링 설정 ====================
class CrawlConfig:
    def __init__(self, year, save_base_path, mode='linux'):
        self.MODE      = mode
        self.YEAR      = str(year)
        self.BASE_PATH = save_base_path

        # Windows 환경변수 치환
        if self.MODE == 'windows':
            self.BASE_PATH = os.path.expandvars(self.BASE_PATH)

        self.SAVE_PATH = os.path.join(self.BASE_PATH, self.YEAR)

        # 검색 조건
        self.TARGET_JOURNAL = "IEEE Transactions on Geoscience and Remote Sensing"

        # 시작 페이지
        self.START_PAGE = 1

        # 타이밍 설정
        self.DOWNLOAD_WAIT_SECONDS    = 300  # PDF 다운로드 대기 (5분)
        self.PAGE_CHANGE_DELAY        = 5    # 페이지 이동 후 대기
        self.SEAT_LIMIT_WAIT_SECONDS  = 300  # Seat limit 시 대기 (5분)

        # 랜덤 지연 범위
        self.MIN_RANDOM_DELAY = 3
        self.MAX_RANDOM_DELAY = 8

        # 안전 장치
        self.MAX_PAGE_VISITS       = 100  # 연도당 최대 100 페이지
        self.MAX_SEAT_LIMIT_RETRIES = 5

        Path(self.SAVE_PATH).mkdir(parents=True, exist_ok=True)
        print(f"[저장 경로] {self.SAVE_PATH}")


# ==================== Chrome 드라이버 설정 ====================
def setup_chrome_driver(download_dir, mode='linux'):
    """Chrome 드라이버 설정

    mode='linux'   : Headless (서버 환경)
    mode='windows' : GUI 표시 (로컬 PC, 브라우저를 직접 눈으로 확인 가능)
    """
    options = Options()

    if mode == 'linux':
        # ── Linux 서버용 (Headless) ──────────────────────────────
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument(
            'user-agent=Mozilla/5.0 (X11; Linux x86_64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        )
    else:
        # ── Windows 로컬 PC용 (브라우저 화면 표시) ───────────────
        # headless 옵션 없음 → 사용자가 직접 브라우저를 보며 진행 상황 파악 가능
        options.add_argument('--start-maximized')          # 창 최대화
        options.add_argument('--disable-extensions')
        options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        )
        print("[Windows 모드] 브라우저 창이 열립니다. 진행 상황을 직접 확인하세요.")

    # 공통 설정
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    # 다운로드 경로 설정
    prefs = {
        "download.default_directory":    download_dir,
        "download.prompt_for_download":  False,
        "download.directory_upgrade":    True,
        "safebrowsing.enabled":          True,
        "plugins.always_open_pdf_externally": True   # PDF 자동 다운로드
    }
    options.add_experimental_option("prefs", prefs)
    options.page_load_strategy = 'eager'

    try:
        # webdriver-manager가 설치된 경우 자동으로 드라이버 관리
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            print("[ChromeDriver] webdriver-manager 로 자동 설치/관리")
        except ImportError:
            service = Service()   # PATH에 chromedriver가 있다고 가정
            print("[ChromeDriver] 시스템 PATH의 chromedriver 사용")

        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(60)
        print(f"[Chrome] 드라이버 초기화 완료 (mode={mode})")
        return driver

    except Exception as e:
        print(f"[오류] Chrome 드라이버 초기화 실패: {e}")
        if mode == 'windows':
            print("  → Chrome 브라우저가 설치되어 있는지 확인하세요.")
            print("  → 'pip install webdriver-manager' 로 자동 설치를 시도하세요.")
        sys.exit(1)


# ==================== 랜덤 지연 ====================
def random_delay(min_sec=3, max_sec=8):
    """봇 탐지 회피용 랜덤 지연"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)
    return delay


# ==================== Seat Limit 체크 ====================
def check_seat_limit(driver):
    """Seat limit 메시지 감지"""
    try:
        page_text = driver.page_source.lower()
        indicators = ["seat limit", "maximum number of users", "too many users", "access denied"]
        return any(indicator in page_text for indicator in indicators)
    except:
        return False


# ==================== 1단계: 국민대 도서관 로그인 ====================
def login_kookmin_library(driver, username, password):
    """국민대 도서관 로그인"""
    print("\n" + "="*60)
    print("1단계: 국민대 성곡도서관 로그인")
    print("="*60)

    try:
        driver.get("https://lib.kookmin.ac.kr/")
        time.sleep(3)

        login_selectors = [
            (By.LINK_TEXT,         "로그인"),
            (By.PARTIAL_LINK_TEXT, "로그인"),
            (By.CSS_SELECTOR,      "a[href*='login']"),
            (By.XPATH,             "//a[contains(text(), '로그인')]"),
        ]

        login_link = None
        for by, selector in login_selectors:
            try:
                login_link = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((by, selector))
                )
                break
            except:
                continue

        if login_link:
            login_link.click()
            print("[OK] 로그인 페이지로 이동")
            time.sleep(3)
        else:
            print("[경고] 로그인 버튼 미발견, 현재 페이지에서 진행")

        # ID 입력
        id_field = None
        for selector in ['user_id', 'userId', 'id', 'username', 'login_id']:
            try:
                id_field = driver.find_element(By.NAME, selector)
                break
            except:
                try:
                    id_field = driver.find_element(By.ID, selector)
                    break
                except:
                    continue

        if not id_field:
            text_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
            if text_inputs:
                id_field = text_inputs[0]

        if id_field:
            id_field.clear()
            id_field.send_keys(username)
            print(f"[OK] ID 입력: {username}")
            time.sleep(1)
        else:
            raise Exception("ID 입력 필드를 찾을 수 없습니다.")

        # 비밀번호 입력
        pw_field = None
        for selector in ['password', 'passwd', 'pwd', 'user_password']:
            try:
                pw_field = driver.find_element(By.NAME, selector)
                break
            except:
                try:
                    pw_field = driver.find_element(By.ID, selector)
                    break
                except:
                    continue

        if not pw_field:
            pw_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")

        if pw_field:
            pw_field.clear()
            pw_field.send_keys(password)
            print("[OK] 비밀번호 입력 완료")
            time.sleep(1)
        else:
            raise Exception("비밀번호 입력 필드를 찾을 수 없습니다.")

        # 로그인 버튼 클릭 또는 Enter
        try:
            submit_btn = driver.find_element(
                By.CSS_SELECTOR, "button[type='submit'], input[type='submit']"
            )
            submit_btn.click()
            print("[OK] 로그인 버튼 클릭")
        except:
            pw_field.send_keys(Keys.RETURN)
            print("[OK] Enter 키로 로그인")

        time.sleep(5)
        print(f"[OK] 로그인 완료  현재 URL: {driver.current_url}\n")
        return True

    except Exception as e:
        print(f"[오류] 로그인 실패: {e}")
        return False


# ==================== 2단계: IEEE 접속 ====================
def access_ieee_via_library(driver):
    """도서관 → 학술정보DB → IEEE 접속"""
    print("="*60)
    print("2단계: 학술정보DB를 통한 IEEE 접속")
    print("="*60)

    try:
        db_selectors = [
            (By.PARTIAL_LINK_TEXT, "학술정보"),
            (By.PARTIAL_LINK_TEXT, "학술DB"),
            (By.PARTIAL_LINK_TEXT, "Database"),
            (By.XPATH, "//a[contains(text(), '학술정보')]"),
            (By.XPATH, "//a[contains(text(), '학술DB')]"),
        ]

        db_link = None
        for by, selector in db_selectors:
            try:
                db_link = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((by, selector))
                )
                break
            except:
                continue

        if db_link:
            db_link.click()
            print("[OK] 학술정보DB 페이지로 이동")
            time.sleep(3)
        else:
            print("[경고] 학술정보DB 링크 미발견, IEEE 직접 접속 시도")

        # IEEE 검색
        try:
            search_box = driver.find_element(
                By.CSS_SELECTOR, "input[type='text'], input[type='search']"
            )
            search_box.clear()
            search_box.send_keys("IEEE")
            search_box.send_keys(Keys.RETURN)
            print("[OK] IEEE 검색")
            time.sleep(3)

            ieee_link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "IEEE"))
            )
            ieee_link.click()
            print("[OK] IEEE 링크 클릭")
            time.sleep(5)
        except:
            print("[경고] IEEE 검색 실패, 프록시 URL 직접 접속")
            driver.get("https://ieeexplore-ieee-org-ssl.proxy.kookmin.ac.kr/Xplore/home.jsp")
            time.sleep(5)

        page_source = driver.page_source
        if "Kookmin University" in page_source or "Access provided by" in page_source:
            print("[OK] 국민대 프록시 인증 확인됨")
        else:
            print("[경고] 프록시 인증 미확인 (계속 진행)")

        print(f"현재 URL: {driver.current_url}\n")
        return True

    except Exception as e:
        print(f"[오류] IEEE 접속 실패: {e}")
        try:
            driver.get("https://ieeexplore-ieee-org-ssl.proxy.kookmin.ac.kr/Xplore/home.jsp")
            time.sleep(5)
            return True
        except:
            return False


# ==================== 3단계: Advanced Search ====================
def setup_ieee_advanced_search(driver, year):
    """IEEE Advanced Search 페이지에서 연도 검색 설정"""
    print("="*60)
    print(f"3단계: {year}년 논문 검색 설정")
    print("="*60)

    try:
        current_url = driver.current_url
        base_url = (
            current_url.split('/Xplore')[0]
            if '/Xplore' in current_url
            else "https://ieeexplore-ieee-org-ssl.proxy.kookmin.ac.kr"
        )
        search_url = f"{base_url}/search/advanced"

        print(f"Advanced Search 접속: {search_url}")
        driver.get(search_url)
        time.sleep(5)
        driver.refresh()
        time.sleep(5)

        print(f"연도 설정: {year}")

        start_year_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[placeholder*='Start Year'], input[name*='startYear']")
            )
        )
        start_year_field.clear()
        start_year_field.send_keys(str(year))
        print(f"[OK] 시작 연도: {year}")
        time.sleep(1)

        end_year_field = driver.find_element(
            By.CSS_SELECTOR, "input[placeholder*='End Year'], input[name*='endYear']"
        )
        end_year_field.clear()
        end_year_field.send_keys(str(year))
        print(f"[OK] 종료 연도: {year}")
        time.sleep(1)

        search_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[type='submit'], button.submit-button")
            )
        )
        search_button.click()
        print("[OK] 검색 실행")
        time.sleep(5)

        print(f"검색 완료  현재 URL: {driver.current_url}\n")
        return True

    except Exception as e:
        print(f"[오류] Advanced Search 설정 실패: {e}")
        return False


# ==================== 4단계: Publication 필터 ====================
def apply_publication_filter(driver, journal_name):
    """특정 저널로 필터링"""
    print(f"4단계: 저널 필터 적용 - {journal_name}")

    try:
        pub_section = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.XPATH,
                 "//xpl-facet-publication-title | //div[contains(@class, 'facet-publication')]")
            )
        )

        search_input = pub_section.find_element(By.CSS_SELECTOR, "input[type='text']")
        search_input.clear()
        search_input.send_keys(journal_name)
        time.sleep(2)

        checkbox = WebDriverWait(pub_section, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, f".//label[contains(normalize-space(), '{journal_name}')]")
            )
        )
        checkbox.click()
        print(f"[OK] 저널 필터 적용: {journal_name}")
        time.sleep(5)
        return True

    except Exception as e:
        print(f"[오류] 저널 필터 적용 실패: {e}")
        return False


# ==================== 5단계: Items Per Page ====================
def set_items_per_page(driver, items=10):
    """페이지당 항목 수 설정"""
    print(f"5단계: 페이지당 {items}개 항목으로 설정")

    try:
        dropdown = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "select[aria-label*='results per page']")
            )
        )
        driver.execute_script(f"arguments[0].value = '{items}';", dropdown)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", dropdown)

        print(f"[OK] 페이지당 {items}개 설정 완료")
        time.sleep(5)
        return True

    except Exception as e:
        print(f"[오류] Items per page 설정 실패: {e}")
        return False


# ==================== 페이지 처리 ====================
def select_all_results(driver):
    """현재 페이지 전체 선택"""
    try:
        select_all = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[aria-label*='Select all']"))
        )
        if not select_all.is_selected():
            driver.execute_script("arguments[0].click();", select_all)
            print("[OK] 전체 선택 완료")
            time.sleep(2)
        return True
    except Exception as e:
        print(f"[오류] 전체 선택 실패: {e}")
        return False


def trigger_download(driver, config):
    """PDF 다운로드"""
    try:
        download_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Download')]"))
        )
        download_btn.click()
        print("[OK] Download 버튼 클릭")
        time.sleep(3)

        pdf_option = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'PDF')]"))
        )
        pdf_option.click()
        print("[OK] PDF 옵션 선택")
        time.sleep(2)

        confirm_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Download')]"))
        )
        confirm_btn.click()
        print("[OK] 다운로드 확인")

        print(f"[대기] 다운로드 중... (최대 {config.DOWNLOAD_WAIT_SECONDS}초)")
        start_time = time.time()

        while time.time() - start_time < config.DOWNLOAD_WAIT_SECONDS:
            try:
                close_icon = driver.find_elements(By.CSS_SELECTOR, "button[aria-label='Close']")
                if close_icon:
                    print("[OK] 다운로드 완료 감지")
                    break
            except:
                pass
            time.sleep(5)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        return True

    except Exception as e:
        print(f"[오류] 다운로드 실패: {e}")
        return False


def process_current_page(driver, page_number, config):
    """현재 페이지 처리"""
    print(f"\n{'='*60}")
    print(f"페이지 {page_number} 처리")
    print(f"{'='*60}")

    for attempt in range(1, config.MAX_SEAT_LIMIT_RETRIES + 1):
        if check_seat_limit(driver):
            print(f"[경고] Seat Limit 감지 ({attempt}/{config.MAX_SEAT_LIMIT_RETRIES})")
            print(f"[대기] {config.SEAT_LIMIT_WAIT_SECONDS}초 대기 중...")
            time.sleep(config.SEAT_LIMIT_WAIT_SECONDS)
            driver.refresh()
            time.sleep(5)
            continue

        try:
            if not select_all_results(driver):
                continue
            if not trigger_download(driver, config):
                continue

            print(f"[OK] 페이지 {page_number} 완료")
            random_delay(5, 15)
            return True

        except Exception as e:
            if check_seat_limit(driver):
                continue
            else:
                print(f"[오류] {e}")
                raise

    print(f"[실패] 페이지 {page_number}: Seat Limit 재시도 초과")
    return False


def locate_page_button(driver, page_number, timeout=10):
    """페이지 버튼 찾기"""
    selectors = [
        (By.CSS_SELECTOR, f"button.stats-Pagination_{page_number}"),
        (By.CSS_SELECTOR, f"button[aria-label='Page {page_number} of search results']"),
    ]

    end_time = time.time() + timeout
    while time.time() < end_time:
        for by, value in selectors:
            elements = driver.find_elements(by, value)
            for element in elements:
                if element.is_displayed() and element.is_enabled():
                    return element
        time.sleep(0.2)

    raise TimeoutException(f"페이지 {page_number} 버튼 미발견")


def go_to_next_page(driver, current_page, config):
    """다음 페이지 이동"""
    if check_seat_limit(driver):
        time.sleep(config.SEAT_LIMIT_WAIT_SECONDS)
        driver.refresh()
        time.sleep(5)

    next_page = current_page + 1
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

    try:
        page_button = locate_page_button(driver, next_page)
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", page_button)
        driver.execute_script("arguments[0].click();", page_button)

        print(f"→ 페이지 {next_page} 이동")
        time.sleep(config.PAGE_CHANGE_DELAY)
        random_delay(1, 3)

        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
        return next_page

    except:
        print(f"[경고] 페이지 {next_page} 버튼 미발견 → 크롤링 종료")
        return None


# ==================== 단일 연도 크롤링 ====================
def crawl_year(year, username, password, save_base_path, mode='linux'):
    """특정 연도 크롤링"""
    print(f"\n{'='*60}")
    print(f"{year}년 IEEE TGRS 논문 크롤링 시작  [mode={mode}]")
    print(f"{'='*60}\n")

    config = CrawlConfig(year, save_base_path, mode)
    driver = setup_chrome_driver(config.SAVE_PATH, mode)

    try:
        if not login_kookmin_library(driver, username, password):
            raise Exception("도서관 로그인 실패")

        if not access_ieee_via_library(driver):
            raise Exception("IEEE 접속 실패")

        if not setup_ieee_advanced_search(driver, year):
            raise Exception("Advanced Search 실패")

        if not apply_publication_filter(driver, config.TARGET_JOURNAL):
            raise Exception("저널 필터 실패")

        if not set_items_per_page(driver, 10):
            raise Exception("Items per page 실패")

        current_page = config.START_PAGE
        visited_pages = 0

        while visited_pages < config.MAX_PAGE_VISITS:
            success = process_current_page(driver, current_page, config)

            if not success:
                print(f"[경고] 페이지 {current_page} 실패, 10분 대기 후 재시도")
                time.sleep(600)
                continue

            visited_pages += 1

            next_page = go_to_next_page(driver, current_page, config)
            if next_page is None:
                print(f"\n[완료] {year}년 모든 페이지 처리 완료!")
                break

            current_page = next_page

        print(f"\n{'='*60}")
        print(f"{year}년 크롤링 완료!")
        print(f"저장 경로: {config.SAVE_PATH}")
        print(f"{'='*60}\n")

    except KeyboardInterrupt:
        print(f"\n[중단] {year}년 크롤링 사용자 중단")
    except Exception as e:
        print(f"\n[오류] {year}년 크롤링 실패: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()


# ==================== credentials.json 로드 ====================
def load_credentials(cred_file='credentials.json'):
    """credentials.json 에서 로그인 정보 읽기"""
    cred_path = Path(cred_file)
    if not cred_path.exists():
        # 스크립트와 같은 폴더에서 찾기
        cred_path = Path(__file__).parent / cred_file

    if cred_path.exists():
        with open(cred_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        uid = data.get('univ_id', '').strip()
        upw = data.get('univ_pw', '').strip()
        if uid and upw and uid != '학번 또는 ID':
            return uid, upw
    return None, None


# ==================== CLI 파싱 ====================
def parse_args():
    parser = argparse.ArgumentParser(
        description='IEEE TGRS 논문 크롤러 (국민대 도서관 프록시)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
실행 예시:
  # Linux 서버 (headless)
  python crawling_ieee_2023_2025.py --mode linux --years 2023 2024 2025

  # Windows PC (브라우저 화면 표시, 진행 상황 직접 확인 가능)
  python crawling_ieee_2023_2025.py --mode windows --years 2023 2024 2025

  # 단일 연도
  python crawling_ieee_2023_2025.py --mode linux --year 2024

  # 저장 경로 직접 지정
  python crawling_ieee_2023_2025.py --mode windows --year 2023 --save-path D:\\MyPapers

  # 로그인 정보 직접 입력 (credentials.json 미사용)
  python crawling_ieee_2023_2025.py --mode windows --year 2023 --username myid --password mypw
        """
    )

    parser.add_argument(
        '--mode', choices=['linux', 'windows'], default=None,
        help=(
            'linux: Headless 서버 모드 (기본값). '
            'windows: 브라우저 화면을 표시하는 로컬 PC 모드.'
        )
    )
    parser.add_argument(
        '--year', type=int, default=None,
        help='크롤링할 단일 연도 (예: 2024)'
    )
    parser.add_argument(
        '--years', type=int, nargs='+', default=None,
        help='크롤링할 연도 목록 (예: --years 2023 2024 2025)'
    )
    parser.add_argument(
        '--save-path', default=None,
        help=(
            '저장 기본 경로. '
            f'Linux 기본값: {DEFAULT_SAVE_PATH_LINUX}  '
            f'Windows 기본값: {DEFAULT_SAVE_PATH_WINDOWS}'
        )
    )
    parser.add_argument('--username', default=None, help='도서관 로그인 ID')
    parser.add_argument('--password', default=None, help='도서관 로그인 비밀번호')

    return parser.parse_args()


# ==================== 메인 ====================
def main():
    args = parse_args()

    # ── 모드 결정 ──────────────────────────────────────────────
    if args.mode is None:
        # 자동 감지: 실행 중인 OS 기반
        detected = 'windows' if platform.system() == 'Windows' else 'linux'
        print(f"[INFO] --mode 미지정 → OS 자동 감지: {detected}")
        args.mode = detected

    # ── 연도 결정 ──────────────────────────────────────────────
    if args.year and args.years:
        print("[오류] --year 와 --years 를 동시에 사용할 수 없습니다.")
        sys.exit(1)
    elif args.year:
        years = [args.year]
    elif args.years:
        years = args.years
    else:
        years = [2023, 2024, 2025]  # 기본값
        print(f"[INFO] 연도 미지정 → 기본값 사용: {years}")

    # ── 저장 경로 결정 ────────────────────────────────────────
    if args.save_path:
        save_base_path = args.save_path
    elif args.mode == 'windows':
        save_base_path = DEFAULT_SAVE_PATH_WINDOWS
    else:
        save_base_path = DEFAULT_SAVE_PATH_LINUX

    # ── 로그인 정보 결정 ──────────────────────────────────────
    username = args.username
    password = args.password

    if not username or not password:
        uid, upw = load_credentials()
        if uid and upw:
            username = username or uid
            password = password or upw
            print(f"[INFO] credentials.json 에서 로그인 정보 로드 완료 (ID: {username})")
        else:
            print("[오류] 로그인 정보가 없습니다.")
            print("  방법 1: credentials.json 에 univ_id / univ_pw 를 설정하세요.")
            print("  방법 2: --username 과 --password 옵션을 사용하세요.")
            sys.exit(1)

    # ── 요약 출력 ────────────────────────────────────────────
    print("\n" + "="*60)
    print("IEEE TGRS 논문 크롤러 시작")
    print("="*60)
    print(f"  실행 모드  : {args.mode}")
    print(f"  대상 연도  : {years}")
    print(f"  저장 경로  : {save_base_path}")
    print(f"  로그인 ID  : {username}")
    print("="*60 + "\n")

    # ── 연도별 순차 크롤링 ───────────────────────────────────
    for year in years:
        print(f"\n{'#'*60}")
        print(f"# {year}년 크롤링 시작")
        print(f"{'#'*60}\n")

        try:
            crawl_year(year, username, password, save_base_path, args.mode)
        except Exception as e:
            print(f"[오류] {year}년 크롤링 실패: {e}")
            continue

        if year != years[-1]:
            print(f"\n[대기] 다음 연도 크롤링 전 30초 대기 중...")
            time.sleep(30)

    print(f"\n{'#'*60}")
    print("# 모든 연도 크롤링 완료!")
    print(f"{'#'*60}")


if __name__ == "__main__":
    main()
