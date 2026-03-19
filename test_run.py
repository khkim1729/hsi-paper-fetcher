#!/usr/bin/env python3
"""테스트: 로그인 → IEEE 접속 → Advanced Search 3단계 확인"""
import time, json
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

CHROME_BIN       = '/data/khkim/chrome_local/chrome_extracted/opt/google/chrome/google-chrome'
CHROMEDRIVER_BIN = '/data/khkim/chrome_local/chromedriver-linux64/chromedriver'
SAVE_PATH        = '/tmp/ieee_test_download'
Path(SAVE_PATH).mkdir(parents=True, exist_ok=True)

LOGIN_URL     = 'https://lib.kookmin.ac.kr/login?returnUrl=%3F&queryParamsHandling=merge'
DB_SEARCH_URL = 'https://lib.kookmin.ac.kr/search/database?keyword=IEEE'
CSS_ID_FIELD  = 'input[formcontrolname="portalUserId"]'
CSS_PW_FIELD  = 'input[formcontrolname="portalPassword"]'
XPATH_BTN     = '//button[@type="submit" and normalize-space(.)="로그인"]'
XPATH_IEEE    = '//*[@id="content"]/ng-component/ik-er-sources/section/ik-er-sources-list-view/div/div[2]/div[2]/a'

cred = json.load(open('/data/hsi_fm_bench_123/more_projects/all_hsi_crawling/hsi-paper-fetcher/credentials.json'))
UID, UPW = cred['univ_id'], cred['univ_pw']
print(f'[INFO] 로그인 ID: {UID}')

options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--disable-blink-features=AutomationControlled')
options.binary_location = CHROME_BIN
options.add_experimental_option('prefs', {
    'download.default_directory': SAVE_PATH,
    'download.prompt_for_download': False,
    'plugins.always_open_pdf_externally': True,
})
options.page_load_strategy = 'normal'

driver = webdriver.Chrome(service=Service(CHROMEDRIVER_BIN), options=options)
driver.set_page_load_timeout(60)
print('[OK] Chrome 시작\n')

try:
    # ── 1단계: 로그인 ──────────────────────────────────────────
    print('[1단계] 도서관 로그인')
    driver.get(LOGIN_URL)
    time.sleep(5)  # Angular 렌더링 대기
    print(f'  URL: {driver.current_url}')

    id_field = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.CSS_SELECTOR, CSS_ID_FIELD)))
    id_field.clear(); id_field.send_keys(UID)
    print(f'  ID 입력: {UID}')

    pw_field = driver.find_element(By.CSS_SELECTOR, CSS_PW_FIELD)
    pw_field.clear(); pw_field.send_keys(UPW)
    print('  PW 입력 완료')

    login_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, XPATH_BTN)))
    login_btn.click()
    print('  로그인 버튼 클릭')
    time.sleep(5)
    print(f'  로그인 후 URL: {driver.current_url}')

    # 로그인 성공 여부 확인
    if 'login' in driver.current_url:
        # 오류 메시지 찾기
        err = driver.find_elements(By.CSS_SELECTOR, '.error, .mat-error, [class*="error"]')
        for e in err:
            if e.text:
                print(f'  [경고] 오류 메시지: {e.text}')
        print('  [경고] 아직 로그인 페이지 (로그인 실패 가능)')
    else:
        print('  [OK] 로그인 성공')

    # ── 2단계: IEEE DB ─────────────────────────────────────────
    print('\n[2단계] IEEE DB 페이지 이동')
    driver.get(DB_SEARCH_URL)
    time.sleep(5)
    print(f'  URL: {driver.current_url}')

    ieee_link = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, XPATH_IEEE)))
    print(f'  IEEE 링크: {ieee_link.text[:60]}')

    original_handles = set(driver.window_handles)
    ieee_link.click()
    print('  IEEE 링크 클릭 → 새 창 대기...')

    WebDriverWait(driver, 15).until(lambda d: len(d.window_handles) > len(original_handles))
    new_handle = (set(driver.window_handles) - original_handles).pop()
    driver.switch_to.window(new_handle)
    time.sleep(5)
    print(f'  새 창 URL: {driver.current_url}')

    if 'ieee' in driver.current_url.lower():
        print('  [OK] IEEE Xplore 프록시 접속 성공!')
    else:
        print(f'  [경고] 예상과 다른 URL')

    # 프록시 인증 확인
    if 'Kookmin University' in driver.page_source or 'Access provided by' in driver.page_source:
        print('  [OK] 국민대 프록시 인증 확인')

    # ── 3단계: Advanced Search ─────────────────────────────────
    print('\n[3단계] Advanced Search (2023)')
    base_url = driver.current_url.split('/Xplore')[0] if '/Xplore' in driver.current_url else 'https://ieeexplore-ieee-org-ssl.proxy.kookmin.ac.kr'
    driver.get(f'{base_url}/search/advanced')
    time.sleep(5)
    driver.refresh()
    time.sleep(5)

    sy = WebDriverWait(driver, 15).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "input[placeholder*='Start Year'], input[name*='startYear']")))
    sy.clear(); sy.send_keys('2023')

    ey = driver.find_element(By.CSS_SELECTOR, "input[placeholder*='End Year'], input[name*='endYear']")
    ey.clear(); ey.send_keys('2023')
    print('  연도 입력: 2023')

    sbtn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR, "button[type='submit'], button.submit-button")))
    sbtn.click()
    time.sleep(6)
    print(f'  검색 URL: {driver.current_url}')

    results = driver.find_elements(By.CSS_SELECTOR, '.result-item, xpl-result-item, .List-results-items, .article-list-item')
    total_text = driver.find_elements(By.CSS_SELECTOR, '.result-count, .ng-star-inserted')
    print(f'  검색 결과 요소: {len(results)}개')
    for el in total_text[:3]:
        if el.text and any(c.isdigit() for c in el.text):
            print(f'  결과 텍스트: {el.text[:80]}')

    print('\n[SUCCESS] 3단계까지 정상 동작 확인!')
    driver.save_screenshot('/tmp/success_screenshot.png')
    print('[디버그] 스크린샷: /tmp/success_screenshot.png')

except Exception as e:
    print(f'\n[오류] {e}')
    import traceback; traceback.print_exc()
    try:
        driver.save_screenshot('/tmp/error_screenshot.png')
        print(f'[디버그] 스크린샷: /tmp/error_screenshot.png')
        print(f'[디버그] URL: {driver.current_url}')
        print(f'[디버그] title: {driver.title}')
    except: pass
finally:
    driver.quit()
    print('\n[종료] Chrome 종료')
