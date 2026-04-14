#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ScienceDirect 저널별 논문 수 / 페이지 수 카운트 스크립트

전략:
  1) undetected-chromedriver 로 국민대 도서관 로그인 → SD 프록시 접속
     (navigator.webdriver 플래그 패치 → 봇 탐지 우회)
  2) 브라우저 쿠키를 requests.Session 으로 이전
  3) SD 내부 JSON API (/search/api?pub=...&articleTypes=FLA&date=...) 를
     requests 로 직접 호출 → 브라우저 UA/JS 탐지 없이 결과 수 취득
  4) requests 실패 시 브라우저 페이지에서 React 렌더 후 텍스트 파싱으로 fallback

실행 예시:
  python count_ScienceDirect.py --headless
  python count_ScienceDirect.py --headless --years 2022 2023 2024
  python count_ScienceDirect.py --headless --years all
"""

import os
import re
import sys
import json
import time
import math
import shutil
import argparse
import requests
import urllib3
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ==================== 상수 ====================
_HERE = Path(__file__).parent          # .../crawler_sciencedirect/
_PARENT = _HERE.parent                 # .../hsi-paper-fetcher/

DEFAULT_CRED_FILE = _PARENT / 'credentials.json'
RESULTS_FILE = _HERE / 'count_results_ScienceDirect.txt'
SCREENSHOT_DIR = _HERE / 'debug_screenshots'

LOGIN_URL      = 'https://lib.kookmin.ac.kr/login?returnUrl=%3F&queryParamsHandling=merge'
DB_SEARCH_URL  = 'https://lib.kookmin.ac.kr/search/database?keyword=ScienceDirect'
CSS_ID_FIELD   = 'input[formcontrolname="portalUserId"]'
CSS_PW_FIELD   = 'input[formcontrolname="portalPassword"]'
XPATH_LOGIN_BTN = '//button[@type="submit" and normalize-space(.)="로그인"]'

CHROME_BIN       = '/data/khkim/chrome_local/chrome_extracted/opt/google/chrome/google-chrome'
CHROMEDRIVER_BIN = '/data/khkim/chrome_local/chromedriver-linux64/chromedriver'
CHROME_VERSION   = 145  # 설치된 Chrome 메이저 버전

DESKTOP_UA = (
    'Mozilla/5.0 (X11; Linux x86_64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/125.0.0.0 Safari/537.36'
)

SD_PROXY_BASE = ''    # 런타임 자동 발견
KIST_WAIT_SECS = [120, 300]
RESULTS_PER_PAGE = 25

# ==================== 저널 목록 ====================
JOURNAL_TARGETS = [
    # Tier 1
    ('Remote Sensing of Environment',
     'Remote Sensing of Environment'),
    ('ISPRS Journal of Photogrammetry and Remote Sensing',
     'ISPRS Journal of Photogrammetry and Remote Sensing'),
    ('International Journal of Applied Earth Observation and Geoinformation',
     'International Journal of Applied Earth Observation and Geoinformation'),
    ('Advances in Space Research',
     'Advances in Space Research'),
    # Tier 2
    ('Information Fusion',       'Information Fusion'),
    ('Pattern Recognition',      'Pattern Recognition'),
    ('Neural Networks',          'Neural Networks'),
    ('Signal Processing',        'Signal Processing'),
    # Tier 3
    ('Neurocomputing',                          'Neurocomputing'),
    ('Expert Systems with Applications',        'Expert Systems with Applications'),
    ('Knowledge-Based Systems',                 'Knowledge-Based Systems'),
    ('Computers and Geosciences',               'Computers & Geosciences'),
    ('Computer Vision and Image Understanding', 'Computer Vision and Image Understanding'),
    ('Image and Vision Computing',              'Image and Vision Computing'),
    ('The Egyptian Journal of Remote Sensing and Space Sciences',
     'The Egyptian Journal of Remote Sensing and Space Sciences'),
]


# ==================== 드라이버 설정 ====================
def setup_chrome_driver(headless=False):
    """undetected-chromedriver 사용: navigator.webdriver 패치로 봇 탐지 우회"""
    chrome_local_tmp = Path('/data/khkim/chrome_tmp')
    chrome_profile_dir = chrome_local_tmp / '.chrome_profile_sd_count'
    if chrome_profile_dir.exists():
        try:
            shutil.rmtree(str(chrome_profile_dir))
        except Exception:
            for lock in ['SingletonLock', 'SingletonCookie', 'SingletonSocket']:
                lp = chrome_profile_dir / lock
                if lp.exists():
                    try: lp.unlink()
                    except Exception: pass
    chrome_profile_dir.mkdir(parents=True, exist_ok=True)

    # undetected_chromedriver 는 chromedriver 바이너리를 직접 수정(패치)함.
    # 원본 바이너리가 다른 프로세스에 의해 점유 중이면 "Text file busy" 에러 발생.
    # → 임시 복사본을 만들어서 패치 대상으로 사용.
    uc_driver_dir = chrome_local_tmp / 'uc_driver'
    uc_driver_dir.mkdir(parents=True, exist_ok=True)
    tmp_chromedriver = uc_driver_dir / 'chromedriver'
    shutil.copy2(CHROMEDRIVER_BIN, str(tmp_chromedriver))
    tmp_chromedriver.chmod(0o755)

    options = uc.ChromeOptions()
    options.add_argument(f'--user-data-dir={chrome_profile_dir}')
    options.add_argument('--window-size=1400,900')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    # --user-agent 플래그: 헤드리스 모드에서도 HTTP 요청 UA 교체
    options.add_argument(f'--user-agent={DESKTOP_UA}')
    if headless:
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

    driver = uc.Chrome(
        options=options,
        driver_executable_path=str(tmp_chromedriver),
        browser_executable_path=CHROME_BIN,
        version_main=CHROME_VERSION,
    )

    # CDP UA 오버라이드 (Network + Emulation 둘 다 시도)
    for cdp_cmd in ['Network.setUserAgentOverride', 'Emulation.setUserAgentOverride']:
        try:
            driver.execute_cdp_cmd(cdp_cmd, {
                'userAgent': DESKTOP_UA,
                'platform': 'Linux x86_64',
            })
            print(f'    [UA] {cdp_cmd} 적용 완료')
            break
        except Exception as e:
            print(f'    [UA 경고] {cdp_cmd} 실패: {e}')

    # JS navigator.userAgent 패치 (모든 새 페이지에 적용)
    try:
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': f"Object.defineProperty(navigator, 'userAgent', {{ get: () => '{DESKTOP_UA}', configurable: true }});"
        })
    except Exception:
        pass

    return driver


# ==================== 로그인 ====================
def login_kookmin_library(driver, username, password):
    print('[1단계] 국민대 도서관 로그인...')
    driver.get(LOGIN_URL)
    time.sleep(5)
    try:
        WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, CSS_ID_FIELD))
        ).send_keys(username)
        time.sleep(0.3)
        driver.find_element(By.CSS_SELECTOR, CSS_PW_FIELD).send_keys(password)
        time.sleep(0.3)
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
        time.sleep(4)
        print(f'    로그인 완료: {driver.current_url[:60]}')
        return True
    except Exception as e:
        print(f'    [오류] 로그인 실패: {e}')
        return False


# ==================== SD 접속 ====================
def access_sd_via_library(driver):
    global SD_PROXY_BASE

    print('[2단계] ScienceDirect 접속...')
    driver.get(DB_SEARCH_URL)
    time.sleep(10)

    # SD 링크 탐색
    sd_link = None
    for _ in range(20):
        time.sleep(1)
        for lnk in driver.find_elements(By.TAG_NAME, 'a'):
            t = lnk.text.strip()
            if 'ScienceDirect' in t or 'Elsevier' in t:
                sd_link = lnk
                break
        if sd_link:
            break
    if not sd_link:
        print('    [경고] ScienceDirect 링크를 찾지 못했습니다.')
        return False

    # window.open 을 가로채서 인증 URL 획득
    # (링크 클릭 시 Angular가 window.open()으로 새 창을 열려 함)
    driver.execute_script('''
        window._capturedOpenUrl = null;
        var _orig = window.open;
        window.open = function(url, name, features) {
            window._capturedOpenUrl = url;
            return { closed: false, focus: function(){}, close: function(){} };
        };
    ''')
    driver.execute_script('arguments[0].click();', sd_link)
    time.sleep(5)

    captured_url = driver.execute_script('return window._capturedOpenUrl;')
    if not captured_url:
        print('    [경고] window.open URL 캡처 실패')
        return False

    print(f'    proxy-redirect URL 획득: {captured_url[:80]}')
    # 현재 창에서 인증 URL로 이동 → SD 프록시로 리다이렉트됨
    driver.get(captured_url)
    time.sleep(15)

    # KIST 차단 페이지 감지 및 재시도
    for _ki, wait_sec in enumerate(KIST_WAIT_SECS):
        if 'kist.kookmin.ac.kr' not in driver.current_url:
            break
        print(f'    [경고] KIST 차단 ({_ki+1}/{len(KIST_WAIT_SECS)+1}), {wait_sec}초 대기...')
        time.sleep(wait_sec)
        # 도서관 페이지로 돌아가서 새 토큰으로 재시도
        driver.get(DB_SEARCH_URL)
        time.sleep(10)
        sd_link = None
        for lnk in driver.find_elements(By.TAG_NAME, 'a'):
            if 'ScienceDirect' in lnk.text.strip() or 'Elsevier' in lnk.text.strip():
                sd_link = lnk; break
        if not sd_link:
            return False
        driver.execute_script('''
            window._capturedOpenUrl = null;
            window.open = function(url, name, features) {
                window._capturedOpenUrl = url;
                return { closed: false, focus: function(){}, close: function(){} };
            };
        ''')
        driver.execute_script('arguments[0].click();', sd_link)
        time.sleep(5)
        captured_url = driver.execute_script('return window._capturedOpenUrl;')
        if not captured_url:
            return False
        driver.get(captured_url)
        time.sleep(15)

    if 'kist.kookmin.ac.kr' in driver.current_url:
        print('    [오류] KIST 차단 해제 불가')
        return False

    current = driver.current_url
    m = re.match(r'(https?://[^/]+)', current)
    globals()['SD_PROXY_BASE'] = m.group(1) if m else 'https://www-sciencedirect-com.proxy.kookmin.ac.kr'
    print(f'    SD 프록시 베이스: {SD_PROXY_BASE}')
    print(f'    ScienceDirect 접속 완료: {current[:80]}')
    return True


# ==================== requests 세션 구성 ====================
def build_requests_session(driver):
    """
    Selenium 브라우저의 현재 쿠키를 requests.Session 으로 복사.
    이후 requests 로 SD API를 직접 호출할 수 있음.
    """
    session = requests.Session()
    try:
        # SD 프록시 도메인의 쿠키 수집
        for cookie in driver.get_cookies():
            session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=cookie.get('domain', '').lstrip('.'),
            )
    except Exception as e:
        print(f'    [쿠키 추출 경고] {e}')

    session.headers.update({
        'User-Agent': DESKTOP_UA,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8',
        'Referer': SD_PROXY_BASE + '/',
        'X-Requested-With': 'XMLHttpRequest',
    })
    session.verify = False  # 프록시 인증서 이슈 방지
    return session


def build_api_url(pub_param, year=None):
    base = (f'{SD_PROXY_BASE}/search/api?'
            f'pub={quote_plus(pub_param)}&articleTypes=FLA')
    if year and str(year) != 'all':
        base += f'&date={year}'
    base += '&show=1&offset=0'
    return base


def build_search_url(pub_param, year=None):
    base = f'{SD_PROXY_BASE}/search?pub={quote_plus(pub_param)}&articleTypes=FLA'
    if year and str(year) != 'all':
        base += f'&date={year}'
    return base


# ==================== 결과 수 조회 ====================
def get_count_via_requests(session, pub_param, year=None):
    """
    requests 로 SD JSON API 직접 호출.
    성공 시 정수 반환, 실패 시 -1.
    """
    url = build_api_url(pub_param, year)
    try:
        resp = session.get(url, timeout=30, allow_redirects=True)
        if resp.status_code != 200:
            return -1
        # JSON 파싱
        try:
            data = resp.json()
            for key in ('resultsFound', 'totalResults', 'total',
                        'resultCount', 'count', 'numberOfResults'):
                v = data.get(key)
                if isinstance(v, int) and v >= 0:
                    return v
                if isinstance(v, str):
                    try: return int(v.replace(',', ''))
                    except ValueError: pass
        except ValueError:
            pass
        # 텍스트에서 JSON 키 정규식
        text = resp.text
        for pat in [
            r'"resultsFound"\s*:\s*(\d+)',
            r'"totalResults"\s*:\s*(\d+)',
            r'"total"\s*:\s*(\d+)',
            r'"resultCount"\s*:\s*(\d+)',
        ]:
            m = re.search(pat, text)
            if m:
                return int(m.group(1))
    except Exception as e:
        print(f'      [requests 오류] {e}')
    return -1


INTER_REQUEST_DELAY = 12   # 요청 간 딜레이 (초) — 빠른 요청 시 SD 봇 탐지 방지
BROWSER_POLL_TIMEOUT  = 90  # body.innerText 폴링 최대 시간 (초)
BROWSER_POLL_INTERVAL = 2   # 폴링 간격 (초)

COUNT_PATTERNS = [
    r'([\d,]+)\s+results?\b',
    r'([\d,]+)\s+articles?\b',
    r'([\d,]+)\s+search\s+results?\b',
    r'Showing\s+\d+\s*[-–]\s*\d+\s+of\s+([\d,]+)',
    r'Found\s+([\d,]+)',
]

BOT_PHRASES = [
    'There was a problem providing the content you requested',
    'Please confirm you are a human',
    'Are you a robot',
    'Access Denied',
    'CAPTCHA',
]

# 일시적 오류 — 재시도 가능
TRANSIENT_PHRASES = [
    'Your request could not be processed due to a network issue',
    'Service Unavailable',
    'Bad Gateway',
    '503',
]


def _parse_count(text):
    """body.innerText 에서 결과 수를 추출. 없으면 None."""
    for pat in COUNT_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            v = int(m.group(1).replace(',', ''))
            if v > 0:
                return v
    return None


def get_count_via_browser(driver, pub_param, year=None, debug=False, _retry=True):
    """
    requests 실패 시 browser fallback.
    body.innerText 를 폴링하며 결과 수가 나타날 때까지 대기.
    차단/일시오류 감지 시 자동 재시도 1회.
    """
    url = build_search_url(pub_param, year)
    try:
        driver.get(url)

        deadline = time.time() + BROWSER_POLL_TIMEOUT
        rendered = ''
        while time.time() < deadline:
            rendered = driver.execute_script(
                "return document.body ? document.body.innerText : ''"
            ) or ''

            # 봇 탐지 / 차단 페이지
            if any(phrase in rendered for phrase in BOT_PHRASES):
                print('      [경고] 봇 탐지 또는 차단 페이지 감지')
                if debug:
                    _save_debug(driver, pub_param, year, rendered)
                if _retry:
                    print(f'      [재시도] {INTER_REQUEST_DELAY * 3}초 대기 후 재시도...')
                    time.sleep(INTER_REQUEST_DELAY * 3)
                    return get_count_via_browser(driver, pub_param, year, debug, _retry=False)
                return -1

            # 일시적 오류 (네트워크 오류 등) — 짧게 대기 후 재시도
            if any(phrase in rendered for phrase in TRANSIENT_PHRASES):
                print('      [경고] 일시적 오류 감지')
                if debug:
                    _save_debug(driver, pub_param, year, rendered)
                if _retry:
                    print(f'      [재시도] {INTER_REQUEST_DELAY}초 대기 후 재시도...')
                    time.sleep(INTER_REQUEST_DELAY)
                    return get_count_via_browser(driver, pub_param, year, debug, _retry=False)
                return -1

            v = _parse_count(rendered)
            if v is not None:
                return v

            time.sleep(BROWSER_POLL_INTERVAL)

        # 타임아웃 — outerHTML 인라인 JSON 마지막 시도
        outer = driver.execute_script(
            "return document.documentElement.outerHTML"
        ) or ''
        for pat in [
            r'"resultsFound"\s*:\s*(\d+)',
            r'"totalResults"\s*:\s*(\d+)',
            r'"total"\s*:\s*(\d+)',
        ]:
            m_res = re.search(pat, outer)
            if m_res:
                v = int(m_res.group(1))
                if v > 0:
                    return v

        if debug:
            _save_debug(driver, pub_param, year, rendered)

    except Exception as e:
        print(f'      [browser 오류] {e}')

    return -1


def _save_debug(driver, pub_param, year, rendered_text):
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%H%M%S')
        safe = re.sub(r'[^\w]', '_', pub_param)[:35]
        path = SCREENSHOT_DIR / f'{ts}_{safe}_{year or "all"}.png'
        driver.save_screenshot(str(path))
        print(f'      [스크린샷] {path}')
        print(f'      [body.innerText 앞 1500자]\n{rendered_text[:1500]}\n')
    except Exception as e:
        print(f'      [디버그 저장 실패] {e}')


# ==================== 실시간 결과 파일 기록 ====================
class ResultWriter:
    def __init__(self, path, years_label):
        self.path = Path(path)
        self.years_label = years_label
        self._rows = []
        self._year_idx = 0
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('=' * 72 + '\n')
            f.write('  ScienceDirect 저널별 논문/페이지 수 카운트 결과\n')
            f.write(f'  실행 시각 : {now_str}\n')
            f.write(f'  조회 연도 : {years_label}\n')
            f.write('=' * 72 + '\n')

    def start_year(self, year):
        self._current_year = year
        self._year_idx = 0
        yr_label = '전체 연도' if year == 'all' else f'{year}년'
        with open(self.path, 'a', encoding='utf-8') as f:
            f.write(f'\n[연도: {yr_label}]\n')
            f.write(f'  {"#":>2}  {"저널":<58}  {"총 논문 수":>10}  {"페이지 수":>9}\n')
            f.write(f'  {"--":>2}  {"-"*58}  {"-"*10}  {"-"*9}\n')

    def add(self, label, total, pages):
        self._year_idx += 1
        total_str = f'{total:,}' if total >= 0 else 'N/A'
        pages_str = f'{pages:,}' if pages >= 0 else 'N/A'
        line = f'  {self._year_idx:>2}  {label[:58]:<58}  {total_str:>10}  {pages_str:>9}\n'
        with open(self.path, 'a', encoding='utf-8') as f:
            f.write(line)
        self._rows.append((self._current_year, self._year_idx, label, total, pages))

    def finalize(self):
        ok   = sum(1 for r in self._rows if r[3] >= 0)
        fail = len(self._rows) - ok
        with open(self.path, 'a', encoding='utf-8') as f:
            f.write('\n' + '=' * 72 + '\n')
            f.write(f'  저널 수: {len(JOURNAL_TARGETS)}  조회 연도: {len(self.years_label)}개  '
                    f'성공: {ok}  실패(N/A): {fail}\n')
            f.write('=' * 72 + '\n')
        print(f'\n결과 저장 완료: {self.path}')
        if fail:
            print(f'[주의] N/A 항목 {fail}개 — debug_screenshots/ 폴더를 확인하세요.')


# ==================== 메인 ====================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--years', nargs='+', default=['2023', '2024'])
    parser.add_argument('--username', default=None)
    parser.add_argument('--password', default=None)
    parser.add_argument('--cred', default=None)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    # 크리덴셜 로드
    username, password = args.username, args.password
    if not username or not password:
        cred_path = Path(args.cred) if args.cred else DEFAULT_CRED_FILE
        if cred_path.exists():
            with open(cred_path, 'r', encoding='utf-8') as f:
                cred = json.load(f)
            username = username or cred.get('univ_id') or cred.get('username')
            password = password or cred.get('univ_pw') or cred.get('password')
    if not username or not password:
        print('[오류] --username/--password 또는 credentials.json 필요')
        sys.exit(1)

    years_label = ['all'] if args.years == ['all'] else [str(y) for y in args.years]

    print('=' * 72)
    print('  ScienceDirect 저널별 논문/페이지 수 카운트')
    print(f'  조회 연도: {years_label}  /  저널 수: {len(JOURNAL_TARGETS)}')
    print('=' * 72)

    driver = setup_chrome_driver(headless=args.headless)
    writer = ResultWriter(RESULTS_FILE, years_label)

    try:
        if not login_kookmin_library(driver, username, password):
            print('[오류] 로그인 실패')
            sys.exit(1)
        if not access_sd_via_library(driver):
            print('[오류] ScienceDirect 접속 실패')
            sys.exit(1)

        # requests 세션 구성 (쿠키 이전)
        req_session = build_requests_session(driver)
        print(f'[INFO] requests 세션 쿠키 {len(req_session.cookies)}개 전달')

        for year in years_label:
            yr_label = '전체 연도' if year == 'all' else f'{year}년'
            print(f'\n[연도: {yr_label}]')
            print(f'  {"#":>2}  {"저널":<58}  {"총 논문 수":>10}  {"페이지 수":>9}')
            print(f'  {"--":>2}  {"-"*58}  {"-"*10}  {"-"*9}')
            writer.start_year(year)

            for i, (label, pub_param) in enumerate(JOURNAL_TARGETS, 1):
                yr_val = year if year != 'all' else None

                # 1차: requests API 호출
                total = get_count_via_requests(req_session, pub_param, yr_val)

                # 2차: 브라우저 fallback
                if total < 0:
                    total = get_count_via_browser(driver, pub_param, yr_val, debug=args.debug)

                pages = math.ceil(total / RESULTS_PER_PAGE) if total > 0 else (0 if total == 0 else -1)
                total_str = f'{total:,}' if total >= 0 else 'N/A'
                pages_str = f'{pages:,}' if pages >= 0 else 'N/A'
                print(f'  {i:>2}  {label[:58]:<58}  {total_str:>10}  {pages_str:>9}')
                sys.stdout.flush()
                writer.add(label, total, pages)

                # 요청 간 딜레이 (봇 탐지 방지)
                if i < len(JOURNAL_TARGETS):
                    time.sleep(INTER_REQUEST_DELAY)

    finally:
        driver.quit()
        writer.finalize()


if __name__ == '__main__':
    main()
