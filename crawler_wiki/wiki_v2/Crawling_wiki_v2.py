import wikipediaapi
import requests
import re
import json
import sys
import os
from datetime import datetime

# Windows 콘솔 인코딩 문제 해결
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

txt_save_dir = 'wiki_texts'
if not os.path.exists(txt_save_dir):
    os.makedirs(txt_save_dir)

# 초기 검색어 리스트 (여기에 세팅하신 긴 리스트를 그대로 쓰시면 됩니다)
initial_words = [
    'hyperspectral',
    'wavelength',
    'scattering',
    'band',
    'material',
    'reflectance',
    'spectral unmixing',
    'material classification',
    'spectroscopic features',
    
    # 관련 조합 용어들
    'hyperspectral imaging',
    'hyperspectral remote sensing',
    'spectral band',
    'wavelength band',
    'spectral reflectance',
    'material identification',
    'spectral signature',
    'hyperspectral classification',
    'spectral resolution',
    'hyperspectral sensor',
    'spectral library',
    'endmember extraction',
    'spectral angle mapper',
    'hyperspectral data',
    'spectral matching',
    'material mapping',
    'hyperspectral camera',
    'spectral analysis',
    'absorption band',
    'reflectance spectroscopy',
    'hyperspectral cube',
    'spectral dimension',
    'spatial resolution',
    'spectral preprocessing',
    'noise reduction',
    'atmospheric correction',
    'radiometric calibration',
    'geometric correction',
    'spectral calibration',
    'hyperspectral preprocessing',
    'dimensionality reduction',
    'principal component analysis',
    'independent component analysis',
    'linear spectral unmixing',
    'nonlinear unmixing',
    'abundance estimation',
    'subpixel classification',
    'pixel purity index',
    'band selection',
    'spectral indices',
    'vegetation indices',
    'normalized difference vegetation index',
    'soil adjusted vegetation index',
    'enhanced vegetation index',
    'normalized difference water index',
    'normalized difference built-up index',
    'mineral indices',
    'clay minerals',
    'iron oxides',
    'carbonate minerals',
    'hydroxyl minerals',
    'spectral mixture analysis',
    'multiple endmember spectral mixture analysis',
    'automated spectral library',
    'spectral database',
    'mineral mapping',
    'geological mapping',
    'lithological mapping',
    'alteration mapping',
    'vegetation mapping',
    'land cover classification',
    'land use classification',
    'crop classification',
    'disease detection',
    'precision agriculture',
    'environmental monitoring',
    'pollution detection',
    'water quality assessment',
    'coastal monitoring',
    'marine applications',
    'forest monitoring',
    'biodiversity assessment',
    'urban mapping',
    'archaeological applications',
    'food quality inspection',
    'pharmaceutical applications',
    'medical imaging',
    'hyperspectral microscopy',
    'fluorescence spectroscopy',
    'raman spectroscopy',
    'infrared spectroscopy',
    'near infrared',
    'shortwave infrared',
    'thermal infrared',
    'visible spectrum',
    'ultraviolet',
    'multispectral imaging',
    'hyperspectral vs multispectral',
    'imaging spectrometer',
    'pushbroom scanner',
    'whiskbroom scanner',
    'snapshot hyperspectral imaging',
    'hyperspectral video',
    'real-time processing',
    'onboard processing',
    'data compression',
    'lossless compression',
    'lossy compression',
    'hyperspectral storage',
    
    # 파장 대역 관련 용어들
    'electromagnetic spectrum',
    'spectral range',
    'wavelength range',
    'visible light',
    'visible wavelength',
    'ultraviolet spectrum',
    'ultraviolet radiation',
    'UV-A',
    'UV-B',
    'UV-C',
    'near infrared spectrum',
    'NIR',
    'VNIR',
    'visible near infrared',
    'shortwave infrared spectrum',
    'SWIR',
    'midwave infrared',
    'MWIR',
    'longwave infrared',
    'LWIR',
    'thermal infrared spectrum',
    'TIR',
    'far infrared',
    'FIR',
    'infrared spectrum',
    'infrared radiation',
    'microwave',
    'microwave spectrum',
    'radio waves',
    'radio frequency',
    'RF',
    'X-ray',
    'X-ray spectrum',
    'gamma ray',
    'gamma radiation',
    'spectral region',
    'wavelength interval',
    'bandwidth',
    'spectral bandwidth',
    'narrowband',
    'broadband',
    'spectral coverage',
    'wavelength coverage',
    'spectral sampling',
    'band center',
    'band width',
    'full width at half maximum',
    'FWHM',
    'spectral resolution',
    'wavelength resolution',
    'spectral binning',
    'band averaging',
    'spectral subset',
    'wavelength subset',
    'blue band',
    'green band',
    'red band',
    'red edge',
    'red edge band',
    'panchromatic',
    'panchromatic band',
    'multispectral bands',
    'hyperspectral bands',
    'continuous spectrum',
    'discrete spectrum',
    'spectral gaps',
    'atmospheric windows',
    'water absorption bands',
    'atmospheric absorption',
    'spectral filtering',
    'bandpass filter',
    'wavelength filter',
]


wiki = wikipediaapi.Wikipedia(
    user_agent='WikiCrawler/5.0 (https://example.com)',
    language='en'
)

output_file = 'wiki_data.jsonl'
progress_file = os.path.join(txt_save_dir, 'wiki_keywords.txt')

queue = initial_words.copy()
visited = set()
data_count = 0

# 설정값
MAX_PAGES = 1000       # 최대 다운로드 수 넉넉하게 변경
SUGGESTION_LIMIT = 10  # 서브 키워드 10개로 설정

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\[citation needed\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_wiki_suggestions(search_word, limit=10):
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "opensearch",
        "search": search_word,
        "limit": limit,
        "namespace": "0",
        "format": "json"
    }
    # [수정 1] 봇 차단 방지를 위한 User-Agent 헤더 명시
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            return response.json()[1] 
        else:
            print(f"  -> [경고] API 차단됨 (상태 코드: {response.status_code})")
    except Exception as e:
        print(f"  -> [오류] 연관 검색어 수집 실패 ({search_word}): {e}")
    return []

open(output_file, 'w', encoding='utf-8').close()
open(progress_file, 'w', encoding='utf-8').close()

print("🚀 꼬리물기 크롤링 시작...")

while queue and data_count < MAX_PAGES:
    word = queue.pop(0)
    
    if word.lower() in visited:
        continue
        
    visited.add(word.lower())
    
    print(f"\n[탐색 중] * {word} * (현재 수집: {data_count}개 / 남은 대기열: {len(queue)}개)")
    
    with open(progress_file, 'a', encoding='utf-8') as f:
        f.write(f"{word}\n")

    # 1. 문서 수집
    page_py = wiki.page(word)
    if page_py.exists():
        summary = page_py.summary
        full_text = page_py.text
        
        document = {
            'id': f"wiki_{word.replace(' ', '_')}",
            'query_word': word,
            'title': page_py.title,
            'summary': clean_text(summary),
            'text': clean_text(full_text)[:10000],
            'canonical_url': page_py.canonicalurl,
            'source': 'wikipedia',
            'language': 'en',
            'collected_at': datetime.now().isoformat()
        }
        
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(document, ensure_ascii=False) + '\n')
            
        data_count += 1
    else:
        print(f"  -> [알림] 페이지가 존재하지 않습니다.")

    # 2. 연관 검색어 파도타기
    suggestions = get_wiki_suggestions(word, limit=SUGGESTION_LIMIT)
    
    # [수정 2] 대소문자 무시하고 중복 처리 후, 무조건 대기열 맨 앞으로(0번 인덱스) 새치기
    for sug in reversed(suggestions):
        sug_lower = sug.lower()
        if sug_lower not in visited:
            # 기존 큐에 '소문자' 버전이 이미 있다면, 뒤에 있는 걸 삭제
            for existing_item in queue:
                if existing_item.lower() == sug_lower:
                    queue.remove(existing_item)
                    break 
            
            queue.insert(0, sug)
            print(f"  -> [우선 검색 대기열 추가] {sug}")

print("\n" + "="*60)
print("크롤링 완료!")
print(f"- 수집된 위키 문서: 총 {data_count}개")
print("="*60)