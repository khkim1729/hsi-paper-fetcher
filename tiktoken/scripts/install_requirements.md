# PDF 토큰 카운터 설치 가이드

## 필요한 패키지 설치

PDF 파일을 처리하기 위해 다음 패키지들이 필요합니다:

```bash
pip install pymupdf4llm pymupdf
```

또는

```bash
pip install pymupdf4llm
```

## 설치 문제 해결

만약 `ModuleNotFoundError: No module named 'frontend'` 오류가 발생하는 경우:

1. 기존 잘못된 패키지 제거:
```bash
pip uninstall fitz pymupdf -y
```

2. 올바른 패키지 설치:
```bash
pip install pymupdf4llm pymupdf
```

3. 설치 확인:
```bash
python -c "from pymupdf4llm import to_markdown; import pymupdf as fitz; print('설치 성공!')"
```

## 사용 방법

```bash
# 인코딩 목록 확인 (PDF 패키지 설치 없이도 가능)
python tiktoken/scripts/pdf_token_counter.py --list-encodings

# PDF 파일 처리
python tiktoken/scripts/pdf_token_counter.py "파일.pdf"
```


















