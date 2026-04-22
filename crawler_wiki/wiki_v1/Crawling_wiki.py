import wikipediaapi
import re
import json
import sys
from datetime import datetime

# Windows 콘솔 인코딩 문제 해결
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

word_lst = [
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
    user_agent='WikiCrawler/1.0 (https://example.com)',
    language='en'
)

# 데이터 저장을 위한 리스트
data = []

# 출력 파일명 설정
output_file = 'wiki_data.jsonl'
output_json = 'wiki_data.json'

def clean_text(text):
    """텍스트 정리 함수"""
    if not text:
        return ""
    # 각주/참조 번호 제거
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\[citation needed\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?\]', '', text)
    # 연속된 공백 제거
    text = re.sub(r'\s+', ' ', text)
    # 앞뒤 공백 제거
    return text.strip()

for word in word_lst:
    page_py = wiki.page(word)
    
    # 페이지 존재 여부 확인
    if page_py.exists():
        # 요약본 가져오기
        summary = page_py.summary
        full_text = page_py.text
        
        # 텍스트 정리
        cleaned_summary = clean_text(summary)
        cleaned_text = clean_text(full_text)
        
        # 데이터 구조 생성
        document = {
            'id': f"wiki_{word.replace(' ', '_')}",
            'query_word': word,
            'title': page_py.title,
            'summary': cleaned_summary,
            'text': cleaned_text[:10000],  # 전체 텍스트는 처음 1만자만 저장
            'canonical_url': page_py.canonicalurl,
            'source': 'wikipedia',
            'language': 'en',
            'collected_at': datetime.now().isoformat(),
            'metadata': {
                'word_count': len(cleaned_summary.split()),
                'text_length': len(cleaned_text)
            }
        }
        
        # 데이터 리스트에 추가
        data.append(document)
        
        # 결과 출력
        print(f"* {word} *")
        print(f"제목: {page_py.title}")
        print(f"URL: {page_py.fullurl}")
        print(f"요약:")
        print(cleaned_summary[:200] + "..." if len(cleaned_summary) > 200 else cleaned_summary)
        print("-" * 80)
    else:
        print(f"* {word} *")
        print(f"페이지가 존재하지 않습니다.")
        print("-" * 80)

# JSONL 형식으로 저장 (각 문서가 한 줄)
print(f"\n데이터를 {output_file}에 저장 중...")
with open(output_file, 'w', encoding='utf-8') as f:
    for doc in data:
        f.write(json.dumps(doc, ensure_ascii=False) + '\n')

# JSON 형식으로도 저장 (전체 배열, 선택적)
print(f"데이터를 {output_json}에 저장 중...")
with open(output_json, 'w', encoding='utf-8') as f:
    json.dump({
        'metadata': {
            'total_documents': len(data),
            'collected_at': datetime.now().isoformat(),
            'source': 'wikipedia',
            'language': 'en'
        },
        'documents': data
    }, f, ensure_ascii=False, indent=2)

print(f"\n총 {len(data)}개의 문서가 저장되었습니다.")
print(f"- JSONL 형식: {output_file} (시스템 권장 형식)")
print(f"- JSON 형식: {output_json} (전체 데이터 확인용)")