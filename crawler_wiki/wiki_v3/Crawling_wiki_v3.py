import wikipediaapi
import requests
import re
import json
import sys
import os
import time  # 429 에러 방지를 위해 추가
from datetime import datetime

# Windows 콘솔 인코딩 문제 해결
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

txt_save_dir = 'wiki_texts'
if not os.path.exists(txt_save_dir):
    os.makedirs(txt_save_dir)

# 초기 검색어 리스트 (약 180개)
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

visited = set()
data_count = 0
SUGGESTION_LIMIT = 10 # 한 단어당 서브 키워드 10개 제한

def clean_text(text):
    if not text: return ""
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
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        # 429 방지를 위해 요청 전 아주 잠깐 대기
        time.sleep(0.5) 
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            return response.json()[1] 
        elif response.status_code == 429:
            print(f"  -> [경고] 과도한 요청으로 차단됨. 5초간 휴식...")
            time.sleep(5)
            return []
    except Exception as e:
        print(f"  -> [오류] 연관 검색어 수집 실패: {e}")
    return []

def save_document(word):
    global data_count
    word_lower = word.lower()
    if word_lower in visited: return False
    
    visited.add(word_lower)
    time.sleep(0.3) # API 호출 간격 조절
    
    page_py = wiki.page(word)
    if page_py.exists():
        doc = {
            'id': f"wiki_{word.replace(' ', '_')}",
            'query_word': word,
            'title': page_py.title,
            'summary': clean_text(page_py.summary),
            'text': clean_text(page_py.text)[:10000],
            'canonical_url': page_py.canonicalurl,
            'source': 'wikipedia',
            'language': 'en',
            'collected_at': datetime.now().isoformat()
        }
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')
        
        with open(progress_file, 'a', encoding='utf-8') as f:
            f.write(f"{word}\n")
            
        data_count += 1
        print(f"[{data_count}] 수집 완료: {word}")
        return True
    return False

# 파일 초기화
open(output_file, 'w', encoding='utf-8').close()
open(progress_file, 'w', encoding='utf-8').close()

print("🚀 2단계 고정형 크롤링 시작 (초기 키워드 180개 + 서브 키워드 각 10개)")

# [1단계] 초기 키워드 180개 처리 및 서브 키워드 목록 작성
sub_keywords_pool = []

for word in initial_words:
    if save_document(word):
        # 성공적으로 수집된 경우에만 서브 키워드 가져오기
        suggestions = get_wiki_suggestions(word, limit=SUGGESTION_LIMIT)
        for sug in suggestions:
            if sug.lower() not in visited and sug not in sub_keywords_pool:
                sub_keywords_pool.append(sug)
    
print(f"\n✅ 1단계 완료. 발견된 서브 키워드: {len(sub_keywords_pool)}개")
print("🚀 2단계 시작 (서브 키워드는 추가 탐색 없이 수집만 진행)")

# [2단계] 서브 키워드 수집 (여기서는 get_wiki_suggestions를 호출하지 않음)
for word in sub_keywords_pool:
    save_document(word)

print("\n" + "="*60)
print(f"🏁 모든 작업 완료! 총 {data_count}개 문서 수집됨.")
print("="*60)


