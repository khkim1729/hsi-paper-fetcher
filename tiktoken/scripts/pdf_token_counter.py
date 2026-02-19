"""
PDF 파일을 PyMuPDF4LLM로 마크업 언어로 처리한 후 tiktoken으로 토큰 수를 계산하는 스크립트
"""

"""
# 단일 PDF 파일 처리
python /scripts/pdf_token_counter.py "경로/파일.pdf"

# 여러 PDF 파일 처리
python scripts/pdf_token_counter.py "파일1.pdf" "파일2.pdf"

# 디렉토리 내 모든 PDF 파일 처리
python scripts/pdf_token_counter.py "G:/내 드라이브/01_Gnewsoft_Crawling/02_IEEE_TAP/token_cal_p100"

# 마크다운 결과 저장
python scripts/pdf_token_counter.py "파일.pdf" --save-markdown "output.md"

# 다른 인코딩 사용
python scripts/pdf_token_counter.py "파일.pdf" --encoding "cl100k_base "

# 사용 가능한 인코딩 목록 확인
python scripts/pdf_token_counter.py --list-encodings
"""
import argparse
from pathlib import Path
from typing import Optional

import tiktoken


def _import_pymupdf_modules():
    """PyMuPDF 관련 모듈을 지연 import"""
    try:
        from pymupdf4llm import to_markdown
        import pymupdf as fitz  # PyMuPDF (pymupdf 패키지)
        return to_markdown, fitz
    except ImportError:
        try:
            # 대체 방법: pymupdf4llm만 설치된 경우
            from pymupdf4llm import to_markdown
            import fitz  # PyMuPDF
            return to_markdown, fitz
        except ImportError:
            raise ImportError(
                "PyMuPDF4LLM이 설치되지 않았습니다. 다음 명령어로 설치하세요:\n"
                "pip install pymupdf4llm pymupdf\n"
                "또는\n"
                "pip install pymupdf4llm"
            )


def process_pdf_to_markdown(pdf_path: Path) -> str:
    """PDF 파일을 마크업 언어(마크다운)로 변환"""
    to_markdown, fitz = _import_pymupdf_modules()
    doc = fitz.open(pdf_path)
    markdown_text = to_markdown(doc)
    doc.close()
    return markdown_text


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """텍스트의 토큰 수를 계산"""
    enc = tiktoken.get_encoding(encoding_name)
    tokens = enc.encode(text)
    return len(tokens)


def process_pdf_and_count_tokens(
    pdf_path: Path,
    encoding_name: str = "cl100k_base",
    save_markdown: Optional[Path] = None,
) -> tuple[str, int]:
    """
    PDF 파일을 처리하고 토큰 수를 계산
    
    Args:
        pdf_path: PDF 파일 경로
        encoding_name: tiktoken 인코딩 이름 (기본값: cl100k_base)
        save_markdown: 마크다운 결과를 저장할 경로 (선택사항)
    
    Returns:
        (markdown_text, token_count) 튜플
    """
    print(f"PDF 파일 처리 중: {pdf_path}")
    markdown_text = process_pdf_to_markdown(pdf_path)
    
    if save_markdown:
        save_markdown.parent.mkdir(parents=True, exist_ok=True)
        save_markdown.write_text(markdown_text, encoding="utf-8")
        print(f"마크다운 파일 저장: {save_markdown}")
    
    print(f"토큰 수 계산 중 (인코딩: {encoding_name})...")
    token_count = count_tokens(markdown_text, encoding_name)
    
    return markdown_text, token_count


def main():
    parser = argparse.ArgumentParser(
        description="PDF 파일을 마크업 언어로 처리하고 토큰 수를 계산"
    )
    parser.add_argument(
        "pdf_path",
        type=Path,
        nargs="*",
        help="처리할 PDF 파일 경로 (여러 파일 지정 가능)"
    )
    parser.add_argument(
        "--encoding",
        type=str,
        default="cl100k_base",
        help="tiktoken 인코딩 이름 또는 모델 이름 (기본값: cl100k_base). "
             "예: cl100k_base, o200k_base, gpt2 또는 gpt-4, gpt-4o, gpt-3.5-turbo"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="OpenAI 모델 이름 (예: gpt-4, gpt-4o, gpt-3.5-turbo). 이 옵션을 사용하면 해당 모델의 인코딩을 자동으로 선택합니다."
    )
    parser.add_argument(
        "--save-markdown",
        type=Path,
        default=None,
        help="마크다운 결과를 저장할 디렉토리 경로 (선택사항). 여러 파일 처리 시 각 파일명.md로 저장"
    )
    parser.add_argument(
        "--list-encodings",
        action="store_true",
        help="사용 가능한 인코딩 목록을 출력하고 종료"
    )
    
    args = parser.parse_args()
    
    if args.list_encodings:
        print("사용 가능한 tiktoken 인코딩:")
        encodings = tiktoken.list_encoding_names()
        for enc in encodings:
            print(f"  - {enc}")
        
        print("\n주요 모델별 인코딩:")
        print("  - GPT-4, GPT-3.5-turbo → cl100k_base (가장 일반적, 권장)")
        print("  - GPT-4o, o1, o3 → o200k_base")
        print("  - GPT-2 → gpt2")
        print("\n모델 이름으로 자동 선택하려면 --model 옵션을 사용하세요.")
        print("예: --model gpt-4")
        return
    
    if not args.pdf_path:
        parser.error("PDF 파일 경로를 지정해주세요. --list-encodings 옵션을 사용하려면 --list-encodings만 지정하세요.")
    
    # 인코딩 결정: --model 옵션이 있으면 모델 이름으로 자동 선택
    encoding_name = args.encoding
    if args.model:
        try:
            encoding_name = tiktoken.encoding_name_for_model(args.model)
            print(f"모델 '{args.model}'에 맞는 인코딩: {encoding_name}")
        except KeyError:
            print(f"경고: 모델 '{args.model}'을 인식할 수 없습니다. 인코딩 '{args.encoding}'을 사용합니다.")
            encoding_name = args.encoding
    
    # PDF 처리를 위해 PyMuPDF 모듈 import 확인
    try:
        _import_pymupdf_modules()
    except ImportError as e:
        print(f"오류: {e}")
        print("\n설치 방법:")
        print("  pip install pymupdf4llm pymupdf")
        print("또는")
        print("  pip install pymupdf4llm")
        return
    
    pdf_files = []
    for pdf_path in args.pdf_path:
        if pdf_path.is_dir():
            # 디렉토리인 경우 모든 PDF 파일 찾기
            pdf_files.extend(pdf_path.glob("*.pdf"))
        elif pdf_path.exists():
            if pdf_path.suffix.lower() == ".pdf":
                pdf_files.append(pdf_path)
            else:
                print(f"경고: 파일이 PDF가 아닐 수 있습니다: {pdf_path}")
        else:
            print(f"경고: 파일을 찾을 수 없습니다: {pdf_path}")
    
    if not pdf_files:
        print("오류: 처리할 PDF 파일을 찾을 수 없습니다.")
        return
    
    print(f"\n총 {len(pdf_files)}개의 PDF 파일을 처리합니다.\n")
    
    total_tokens = 0
    results = []
    
    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"\n[{i}/{len(pdf_files)}] 처리 중: {pdf_path.name}")
        
        save_markdown = None
        if args.save_markdown:
            if args.save_markdown.is_dir() or len(pdf_files) > 1:
                # 여러 파일 처리 시 각 파일명으로 저장
                md_dir = args.save_markdown if args.save_markdown.is_dir() else args.save_markdown.parent
                md_dir.mkdir(parents=True, exist_ok=True)
                save_markdown = md_dir / f"{pdf_path.stem}.md"
            else:
                save_markdown = args.save_markdown
        
        try:
            markdown_text, token_count = process_pdf_and_count_tokens(
                pdf_path,
                encoding_name,
                save_markdown
            )
            
            total_tokens += token_count
            results.append({
                "file": pdf_path,
                "tokens": token_count,
                "chars": len(markdown_text)
            })
            
            print(f"  ✓ 토큰 수: {token_count:,}")
            
        except Exception as e:
            print(f"  ✗ 오류 발생: {e}")
            results.append({
                "file": pdf_path,
                "tokens": 0,
                "chars": 0,
                "error": str(e)
            })
    
    # 최종 요약 출력
    print("\n" + "="*60)
    print("처리 완료 - 요약:")
    print("="*60)
    for result in results:
        if "error" in result:
            print(f"  {result['file'].name}: 오류 - {result['error']}")
        else:
            print(f"  {result['file'].name}: {result['tokens']:,} 토큰 ({result['chars']:,} 문자)")
    print("-"*60)
    print(f"  사용된 인코딩: {encoding_name}")
    print(f"  총 토큰 수: {total_tokens:,}")
    print(f"  처리된 파일 수: {len([r for r in results if 'error' not in r])}/{len(results)}")
    print("="*60)


if __name__ == "__main__":
    main()

