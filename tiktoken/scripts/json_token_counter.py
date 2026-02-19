"""
JSON/JSONL 파일을 tiktoken으로 토큰 수를 계산하는 스크립트
"""

"""
# 단일 JSON 파일 처리
python scripts/json_token_counter.py "경로/파일.json"

# 단일 JSONL 파일 처리
python scripts/json_token_counter.py "경로/파일.jsonl"

# 여러 JSON/JSONL 파일 처리
python scripts/json_token_counter.py "파일1.json" "파일2.jsonl"

# 디렉토리 내 모든 JSON/JSONL 파일 처리
python scripts/json_token_counter.py "경로/디렉토리"

# 특정 필드만 추출하여 토큰 계산 (예: documents[].text 필드만)
python scripts/json_token_counter.py "파일.json" --field "documents[].text"

# JSON/JSONL 결과 저장
python scripts/json_token_counter.py "파일.json" --save-json "output.txt"

# 다른 인코딩 사용
python scripts/json_token_counter.py "파일.json" --encoding "cl100k_base"

# 사용 가능한 인코딩 목록 확인
python scripts/json_token_counter.py --list-encodings
"""
import argparse
import json
from pathlib import Path
from typing import Optional, Any

import tiktoken


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """텍스트의 토큰 수를 계산"""
    enc = tiktoken.get_encoding(encoding_name)
    tokens = enc.encode(text)
    return len(tokens)


def extract_field_from_json(data: Any, field_path: str) -> str:
    """
    JSON 데이터에서 특정 필드 경로로 값을 추출하여 문자열로 변환
    
    Args:
        data: JSON 데이터 (dict 또는 list)
        field_path: 필드 경로 (예: "documents[].text", "metadata.total_documents", "text")
    
    Returns:
        추출된 필드의 문자열 표현
    """
    # data가 리스트인 경우 (JSONL 등), 각 요소에서 필드 추출
    if isinstance(data, list):
        results = []
        for item in data:
            extracted = extract_field_from_json(item, field_path)
            if extracted:
                results.append(extracted)
        return "\n\n".join(results)
    
    # data가 dict가 아니면 빈 문자열 반환
    if not isinstance(data, dict):
        return ""
    
    parts = field_path.split(".")
    current = data
    
    for part in parts:
        if part.endswith("[]"):
            # 배열 필드인 경우 모든 요소를 처리
            field_name = part[:-2]
            if field_name:
                current = current.get(field_name, [])
            
            if not isinstance(current, list):
                return ""
            
            # 배열의 모든 요소에서 다음 필드를 추출
            results = []
            remaining_path = ".".join(parts[parts.index(part) + 1:])
            for item in current:
                if remaining_path:
                    extracted = extract_field_from_json(item, remaining_path)
                    if extracted:
                        results.append(extracted)
                else:
                    if isinstance(item, (dict, list)):
                        results.append(json.dumps(item, ensure_ascii=False))
                    else:
                        results.append(str(item))
            return "\n\n".join(results)
        else:
            # 일반 필드 접근
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return ""
    
    # 최종 결과를 문자열로 변환
    if current is None:
        return ""
    elif isinstance(current, (dict, list)):
        return json.dumps(current, ensure_ascii=False)
    else:
        return str(current)


def load_json_file(json_path: Path) -> Any:
    """JSON 파일을 로드 (JSON 또는 JSONL 자동 감지)"""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            # 확장자가 .jsonl이면 무조건 JSONL로 처리
            if json_path.suffix.lower() == ".jsonl":
                objects = []
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line:  # 빈 줄 건너뛰기
                        try:
                            obj = json.loads(line)
                            objects.append(obj)
                        except json.JSONDecodeError as e:
                            raise ValueError(f"JSONL 파싱 오류 (줄 {line_num}): {e}")
                return objects
            
            # .json 확장자이거나 확장자가 없는 경우
            # 먼저 일반 JSON으로 시도
            try:
                f.seek(0)
                return json.load(f)
            except json.JSONDecodeError as json_error:
                # JSON 파싱 실패 시, 확장자가 없으면 JSONL로 시도
                if not json_path.suffix:
                    f.seek(0)
                    objects = []
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if line:  # 빈 줄 건너뛰기
                            try:
                                obj = json.loads(line)
                                objects.append(obj)
                            except json.JSONDecodeError:
                                # JSONL도 실패하면 원래 JSON 오류 발생
                                raise ValueError(f"JSON 파싱 오류: {json_error}")
                    return objects
                else:
                    # .json 확장자면 JSON 오류만 발생
                    raise ValueError(f"JSON 파싱 오류: {json_error}")
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 오류: {e}")
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise IOError(f"파일 읽기 오류: {e}")


def process_json_and_count_tokens(
    json_path: Path,
    encoding_name: str = "cl100k_base",
    field_path: Optional[str] = None,
    save_json: Optional[Path] = None,
) -> tuple[str, int]:
    """
    JSON/JSONL 파일을 처리하고 토큰 수를 계산
    
    Args:
        json_path: JSON/JSONL 파일 경로
        encoding_name: tiktoken 인코딩 이름 (기본값: cl100k_base)
        field_path: 추출할 필드 경로 (None이면 전체 JSON 사용)
        save_json: 처리된 JSON 텍스트를 저장할 경로 (선택사항)
    
    Returns:
        (json_text, token_count) 튜플
    """
    file_type = "JSONL" if json_path.suffix.lower() == ".jsonl" else "JSON"
    print(f"{file_type} 파일 처리 중: {json_path}")
    data = load_json_file(json_path)
    
    # 필드 경로가 지정된 경우 해당 필드만 추출, 아니면 전체 JSON 사용
    if field_path:
        print(f"필드 추출 중: {field_path}")
        json_text = extract_field_from_json(data, field_path)
        if not json_text:
            raise ValueError(f"필드를 찾을 수 없습니다: {field_path}")
    else:
        # JSONL인 경우 각 객체를 한 줄씩, JSON인 경우 포맷팅
        if json_path.suffix.lower() == ".jsonl" and isinstance(data, list):
            # JSONL 형식: 각 객체를 한 줄로 출력
            json_text = "\n".join(json.dumps(obj, ensure_ascii=False) for obj in data)
        else:
            # 일반 JSON: 포맷팅하여 출력
            json_text = json.dumps(data, ensure_ascii=False, indent=2)
    
    if save_json:
        save_json.parent.mkdir(parents=True, exist_ok=True)
        save_json.write_text(json_text, encoding="utf-8")
        print(f"텍스트 저장: {save_json}")
    
    print(f"토큰 수 계산 중 (인코딩: {encoding_name})...")
    token_count = count_tokens(json_text, encoding_name)
    
    return json_text, token_count


def main():
    parser = argparse.ArgumentParser(
        description="JSON/JSONL 파일을 처리하고 토큰 수를 계산"
    )
    parser.add_argument(
        "json_path",
        type=Path,
        nargs="*",
        help="처리할 JSON/JSONL 파일 경로 (여러 파일 지정 가능)"
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
        "--field",
        type=str,
        default=None,
        help="추출할 필드 경로 (선택사항). 예: 'documents[].text', 'metadata.total_documents'. "
             "지정하지 않으면 전체 JSON을 사용합니다."
    )
    parser.add_argument(
        "--save-json",
        type=Path,
        default=None,
        help="처리된 JSON 텍스트를 저장할 디렉토리 경로 (선택사항). 여러 파일 처리 시 각 파일명.txt로 저장"
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
    
    if not args.json_path:
        parser.error("JSON/JSONL 파일 경로를 지정해주세요. --list-encodings 옵션을 사용하려면 --list-encodings만 지정하세요.")
    
    # 인코딩 결정: --model 옵션이 있으면 모델 이름으로 자동 선택
    encoding_name = args.encoding
    if args.model:
        try:
            encoding_name = tiktoken.encoding_name_for_model(args.model)
            print(f"모델 '{args.model}'에 맞는 인코딩: {encoding_name}")
        except KeyError:
            print(f"경고: 모델 '{args.model}'을 인식할 수 없습니다. 인코딩 '{args.encoding}'을 사용합니다.")
            encoding_name = args.encoding
    
    json_files = []
    for json_path in args.json_path:
        if json_path.is_dir():
            # 디렉토리인 경우 모든 JSON/JSONL 파일 찾기
            json_files.extend(json_path.glob("*.json"))
            json_files.extend(json_path.glob("*.jsonl"))
        elif json_path.exists():
            if json_path.suffix.lower() in [".json", ".jsonl"]:
                json_files.append(json_path)
            else:
                print(f"경고: 파일이 JSON/JSONL이 아닐 수 있습니다: {json_path}")
        else:
            print(f"경고: 파일을 찾을 수 없습니다: {json_path}")
    
    if not json_files:
        print("오류: 처리할 JSON/JSONL 파일을 찾을 수 없습니다.")
        return
    
    json_count = sum(1 for f in json_files if f.suffix.lower() == ".json")
    jsonl_count = sum(1 for f in json_files if f.suffix.lower() == ".jsonl")
    
    if json_count > 0 and jsonl_count > 0:
        print(f"\n총 {len(json_files)}개의 파일을 처리합니다 (JSON: {json_count}, JSONL: {jsonl_count}).\n")
    elif jsonl_count > 0:
        print(f"\n총 {len(json_files)}개의 JSONL 파일을 처리합니다.\n")
    else:
        print(f"\n총 {len(json_files)}개의 JSON 파일을 처리합니다.\n")
    
    total_tokens = 0
    results = []
    
    for i, json_path in enumerate(json_files, 1):
        print(f"\n[{i}/{len(json_files)}] 처리 중: {json_path.name}")
        
        save_json = None
        if args.save_json:
            if args.save_json.is_dir() or len(json_files) > 1:
                # 여러 파일 처리 시 각 파일명으로 저장
                txt_dir = args.save_json if args.save_json.is_dir() else args.save_json.parent
                txt_dir.mkdir(parents=True, exist_ok=True)
                save_json = txt_dir / f"{json_path.stem}.txt"
            else:
                save_json = args.save_json
        
        try:
            json_text, token_count = process_json_and_count_tokens(
                json_path,
                encoding_name,
                args.field,
                save_json
            )
            
            total_tokens += token_count
            results.append({
                "file": json_path,
                "tokens": token_count,
                "chars": len(json_text)
            })
            
            print(f"  ✓ 토큰 수: {token_count:,}")
            
        except Exception as e:
            print(f"  ✗ 오류 발생: {e}")
            results.append({
                "file": json_path,
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
    if args.field:
        print(f"  추출된 필드: {args.field}")
    print(f"  총 토큰 수: {total_tokens:,}")
    print(f"  처리된 파일 수: {len([r for r in results if 'error' not in r])}/{len(results)}")
    print("="*60)


if __name__ == "__main__":
    main()

