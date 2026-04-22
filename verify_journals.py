#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IEEE Publication Title 필터 클릭 검증 스크립트 (2023 기준)

list_affiliation/list_affiliation.txt 의 25개 항목을 IEEE Xplore 에서
실제로 클릭할 수 있는지 빠르게 확인한다.

실행 예시:
  python verify_journals.py --username ID --password PW
  python verify_journals.py --headless --username ID --password PW
"""

import os
import sys
import time
import argparse
import json
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ── 메인 스크립트와 동일한 경로 상수 ──────────────────────────────────
LOGIN_URL     = 'https://lib.kookmin.ac.kr/login?returnUrl=%2F'
DB_SEARCH_URL = 'https://lib.kookmin.ac.kr/search/database?keyword=IEEE'
IEEE_PROXY_HOME = 'https://ieeexplore-ieee-org.libproxy.kookmin.ac.kr'

CSS_ID_FIELD   = 'input[formcontrolname="loginId"]'
CSS_PW_FIELD   = 'input[formcontrolname="loginPw"]'
XPATH_LOGIN_BTN = '//button[contains(., "로그인") or contains(., "Login")]'

CHROME_BIN_LINUX       = '/data/khkim/chrome_local/chrome_extracted/opt/google/chrome/google-chrome'
CHROMEDRIVER_BIN_LINUX = '/data/khkim/chrome_local/chromedriver-linux64/chromedriver'

VERIFY_YEAR = 2023

# ── 25개 타겟 Publication (list_affiliation.txt 기반, 2023 기준) ──────
# 형식: (search_term, label_match)
#   search_term  : Publication Title 검색창에 입력할 문자열
#   label_match  : 체크박스 레이블에서 일치 확인할 문자열 (앞 40자로 매칭)
VERIFY_TARGETS = [
    # 1
    ("IEEE Access",                                "IEEE Access"),
    # 2
    ("IEEE Sensors Journal",                       "IEEE Sensors Journal"),
    # 3  연도 포함 학회
    ("ICASSP 2023",                                "ICASSP 2023"),
    # 4
    ("2023 IEEE/CVF Conference on Computer Vision and Pattern",
     "2023 IEEE/CVF Conference on Computer Vision and Pattern Recognition"),
    # 5
    ("Transactions on Instrumentation and Measurement",
     "IEEE Transactions on Instrumentation and Measurement"),
    # 6
    ("2023 IEEE/CVF International Conference on Computer Vision",
     "2023 IEEE/CVF International Conference on Computer Vision"),
    # 7
    ("IGARSS 2023",                                "IGARSS 2023"),
    # 8
    ("Transactions on Geoscience and Remote Sensing",
     "IEEE Transactions on Geoscience and Remote Sensing"),
    # 9
    ("Internet of Things Journal",                 "IEEE Internet of Things Journal"),
    # 10
    ("2023 Conference on Lasers and Electro-Optics",
     "2023 Conference on Lasers and Electro-Optics (CLEO)"),
    # 11
    ("2023 China Automation Congress",             "2023 China Automation Congress (CAC)"),
    # 12
    ("ICCCNT",                                     "ICCCNT"),
    # 13
    ("2023 42nd Chinese Control Conference",       "2023 42nd Chinese Control Conference"),
    # 14
    ("Transactions on Power Electronics",          "IEEE Transactions on Power Electronics"),
    # 15
    ("CLEO/Europe",                                "CLEO/Europe-EQEC"),
    # 16
    ("Transactions on Vehicular Technology",       "IEEE Transactions on Vehicular Technology"),
    # 17
    ("2023 IEEE International Conference on Robotics and Automation",
     "2023 IEEE International Conference on Robotics and Automation"),
    # 18
    ("GLOBECOM 2023",                              "GLOBECOM 2023"),
    # 19
    ("Transactions on Intelligent Transportation", "IEEE Transactions on Intelligent Transportation Systems"),
    # 20
    ("Transactions on Industrial Electronics",     "IEEE Transactions on Industrial Electronics"),
    # 21
    ("2023 45th Annual International Conference of the IEEE Engineering in Medicine",
     "2023 45th Annual International Conference of the IEEE Engineering"),
    # 22
    ("2023 IEEE/RSJ International Conference on Intelligent Robots",
     "2023 IEEE/RSJ International Conference on Intelligent Robots"),
    # 23
    ("Robotics and Automation Letters",            "IEEE Robotics and Automation Letters"),
    # 24
    ("2023 62nd IEEE Conference on Decision and Control",
     "2023 62nd IEEE Conference on Decision and Control"),
    # 25
    ("IECON 2023",                                 "IECON 2023"),
]


def setup_driver(headless=False):
    opts = Options()
    if headless:
        opts.add_argument('--headless=new')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1400,900')
    opts.add_argument('--disable-gpu')

    if sys.platform.startswith('linux') and os.path.exists(CHROME_BIN_LINUX):
        opts.binary_location = CHROME_BIN_LINUX
        service = Service(CHROMEDRIVER_BIN_LINUX)
    else:
        service = Service()

    driver = webdriver.Chrome(service=service, options=opts)
    return driver


def login(driver, username, password):
    print('[1단계] 도서관 로그인...')
    driver.get(LOGIN_URL)
    time.sleep(5)
    try:
        WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, CSS_ID_FIELD))
        ).send_keys(username)
        time.sleep(0.3)
        driver.find_element(By.CSS_SELECTOR, CSS_PW_FIELD).send_keys(password)
        time.sleep(0.3)
        driver.find_element(By.XPATH, XPATH_LOGIN_BTN).click()
        time.sleep(4)
        print(f'    OK  URL={driver.current_url}')
        return True
    except Exception as e:
        print(f'    FAIL  {e}')
        return False


def open_ieee(driver):
    print('[2단계] IEEE Xplore 접속...')
    driver.get(DB_SEARCH_URL)
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
        print('    FAIL  IEEE 링크 없음 → 프록시 직접 접속 시도')
        driver.get(IEEE_PROXY_HOME)
        time.sleep(10)
        return True

    original = set(driver.window_handles)
    driver.execute_script('arguments[0].click();', ieee_link)
    try:
        WebDriverWait(driver, 15).until(lambda d: len(d.window_handles) > len(original))
        new_h = (set(driver.window_handles) - original).pop()
        driver.switch_to.window(new_h)
    except TimeoutException:
        pass
    time.sleep(15)
    print(f'    OK  URL={driver.current_url[:80]}')
    return True


def go_advanced_search(driver, year):
    """Advanced Search로 이동 후 연도 필터 적용"""
    print(f'[3단계] Advanced Search ({year}년)...')
    adv_url = (f'{IEEE_PROXY_HOME}/search/advanced?'
               f'queryText=&newsearch=true&'
               f'ranges={year}_{year}_Year')
    driver.get(adv_url)
    time.sleep(8)
    print(f'    URL={driver.current_url[:80]}')


def try_filter(driver, idx, search_term, label_match):
    """Publication Title 필터 한 건 시도. (OK / FAIL / NOTFOUND) 반환"""
    match_substr = label_match[:40]
    try:
        # Publication Title 섹션 펼치기
        pub_btn = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (By.XPATH, "//button[normalize-space(.)='Publication Title']")
            )
        )
        if pub_btn.get_attribute('aria-expanded') != 'true':
            driver.execute_script('arguments[0].click();', pub_btn)
            time.sleep(2)

        # 검색어 입력
        inp = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (By.XPATH,
                 "//button[normalize-space(.)='Publication Title']"
                 "/../../following-sibling::*//input[@placeholder='Enter Title' or @placeholder='Enter title']")
            )
        )
        inp.clear()
        inp.send_keys(search_term)
        time.sleep(3)  # 자동완성 대기

        # 레이블 찾기
        labels = driver.find_elements(
            By.XPATH, f"//label[contains(normalize-space(), '{match_substr}')]"
        )
        if not labels:
            return 'NOTFOUND', 'label 없음'

        # 찾으면 클릭 (검증 목적이므로 Apply 까지는 안 함)
        found_text = labels[0].text.strip()[:70]
        return 'OK', found_text

    except TimeoutException:
        return 'FAIL', 'timeout'
    except Exception as e:
        return 'FAIL', str(e)[:60]
    finally:
        # 입력창 초기화 (다음 검색 준비)
        try:
            inp = driver.find_element(
                By.XPATH,
                "//button[normalize-space(.)='Publication Title']"
                "/../../following-sibling::*//input[@placeholder='Enter Title' or @placeholder='Enter title']"
            )
            inp.clear()
            time.sleep(1)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', default=None)
    parser.add_argument('--password', default=None)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--cred', default='credentials.json')
    args = parser.parse_args()

    username, password = args.username, args.password
    if not username or not password:
        cred_file = Path(args.cred)
        if cred_file.exists():
            with open(cred_file, 'r', encoding='utf-8') as f:
                cred = json.load(f)
            username = username or cred.get('username')
            password = password or cred.get('password')
    if not username or not password:
        print('[오류] --username / --password 또는 credentials.json 필요')
        sys.exit(1)

    driver = setup_driver(headless=args.headless)
    results = []

    try:
        if not login(driver, username, password):
            print('[오류] 로그인 실패')
            sys.exit(1)

        if not open_ieee(driver):
            print('[오류] IEEE 접속 실패')
            sys.exit(1)

        go_advanced_search(driver, VERIFY_YEAR)

        print(f'\n{"="*70}')
        print(f'  Publication Title 필터 클릭 검증 ({VERIFY_YEAR}년 기준, {len(VERIFY_TARGETS)}개)')
        print(f'{"="*70}')
        print(f'  {"#":>2}  {"결과":<8}  {"검색어":<45}  {"매칭 레이블"}')
        print(f'  {"-"*2}  {"-"*8}  {"-"*45}  {"-"*40}')

        ok_count = fail_count = notfound_count = 0

        for i, (search_term, label_match) in enumerate(VERIFY_TARGETS, 1):
            status, detail = try_filter(driver, i, search_term, label_match)
            results.append({
                'idx': i,
                'search_term': search_term,
                'label_match': label_match,
                'status': status,
                'detail': detail,
            })
            if status == 'OK':
                ok_count += 1
            elif status == 'NOTFOUND':
                notfound_count += 1
            else:
                fail_count += 1

            status_str = {'OK': '[OK]      ', 'NOTFOUND': '[NOTFOUND]', 'FAIL': '[FAIL]    '}[status]
            print(f'  {i:>2}  {status_str}  {search_term[:45]:<45}  {detail[:50]}')

    finally:
        driver.quit()

    print(f'\n{"="*70}')
    print(f'  결과 요약: OK={ok_count}  NOTFOUND={notfound_count}  FAIL={fail_count}  합계={len(VERIFY_TARGETS)}')
    print(f'{"="*70}')

    # 결과 저장
    out_path = Path(__file__).parent / 'list_affiliation' / f'verify_result_{VERIFY_YEAR}.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f'  상세 결과 저장: {out_path}')

    # 문제 항목만 출력
    problems = [r for r in results if r['status'] != 'OK']
    if problems:
        print(f'\n  [주의] 클릭 실패/미발견 항목 ({len(problems)}개):')
        for r in problems:
            print(f"    #{r['idx']:>2} [{r['status']}] {r['search_term']}")
    else:
        print('\n  모든 항목 클릭 가능 확인!')


if __name__ == '__main__':
    main()
