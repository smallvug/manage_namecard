#!/usr/bin/env python3
"""
명함 사진 정리 프로그램

사용법:
  python manage.py

필요: ANTHROPIC_API_KEY 환경변수 설정
      pip install anthropic Pillow
"""

import shutil
import base64
from pathlib import Path
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from PIL import Image
from PIL.ExifTags import TAGS

load_dotenv()

DATA_DIR = Path("_data")
OUTPUT_DIR = Path("_processed")
IMG_EXTS = {".JPG", ".JPEG", ".PNG"}


def get_photo_date(path: Path) -> str:
    """EXIF에서 촬영 날짜 추출, 없으면 파일 수정 날짜 사용"""
    try:
        exif = Image.open(path)._getexif()
        if exif:
            for tag_id, val in exif.items():
                if TAGS.get(tag_id) == "DateTimeOriginal":
                    return datetime.strptime(val, "%Y:%m:%d %H:%M:%S").strftime("%Y.%m.%d")
    except Exception:
        pass
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y.%m.%d")


def to_base64(path: Path) -> tuple[str, str]:
    """이미지를 base64 인코딩, (data, media_type) 반환"""
    media_type = "image/png" if path.suffix.upper() == ".PNG" else "image/jpeg"
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return data, media_type


def analyze_namecard(client: anthropic.Anthropic, photos: list[Path]) -> str:
    """Claude Vision으로 명함 정보 분석, 폴더명 반환"""
    content = []
    for photo in photos:
        data, mt = to_base64(photo)
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": mt, "data": data},
        })

    content.append({
        "type": "text",
        "text": """명함을 분석해서 폴더명을 만들어주세요.

형식: [이름], [기관명], [직책]
규칙:
- 영문/중문 이름: 성(대문자) 이름  예) GLASS John, FEI Qiang
- 한국어 이름: 성 이름  예) 강 남규, 구 옥재
- 기관 내 부서/학과가 있으면 콤마로 추가
  예) FEI Qiang, Xian Jiaotong University, School of Chemical Engineering and Technology, Professor
- 직책이 없으면 기관명까지만

폴더명만 출력하세요. 다른 설명 없이.""",
    })

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text.strip()


def sanitize(name: str) -> str:
    """Windows 파일명에 사용할 수 없는 문자 제거"""
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "")
    return name.strip()


def next_file_num(folder: Path, date: str) -> int:
    """해당 날짜의 다음 명함 번호 반환"""
    n = 1
    prefix = f"[{date}] 명함 "
    for f in folder.iterdir():
        if f.name.startswith(prefix):
            try:
                rest = f.name[len(prefix):]
                n = max(n, int(rest.split(".")[0]) + 1)
            except ValueError:
                pass
    return n


def copy_photos(front: Path, back: Path | None, folder_name: str) -> Path:
    """사진을 _processed/[폴더명]/ 으로 복사"""
    dest = OUTPUT_DIR / folder_name
    dest.mkdir(parents=True, exist_ok=True)

    date = get_photo_date(front)
    num = next_file_num(dest, date)

    shutil.copy2(front, dest / f"[{date}] 명함 {num}{front.suffix.upper()}")
    if back:
        shutil.copy2(back, dest / f"[{date}] 명함 {num + 1}{back.suffix.upper()}")

    return dest


def resolve_back(images: list[Path], back_input: str) -> Path | None:
    """번호 또는 파일명으로 뒷면 사진 찾기"""
    try:
        idx = int(back_input) - 1
        if 0 <= idx < len(images):
            return images[idx]
    except ValueError:
        pass
    candidate = DATA_DIR / back_input
    if candidate.exists():
        return candidate
    return None


def main():
    images = sorted(p for p in DATA_DIR.iterdir() if p.suffix.upper() in IMG_EXTS)

    if not images:
        print("_data/ 폴더에 이미지가 없습니다.")
        return

    print(f"이미지 {len(images)}개 발견:")
    for idx, img in enumerate(images, 1):
        print(f"  {idx:2}. {img.name}")
    print()

    client = anthropic.Anthropic()
    OUTPUT_DIR.mkdir(exist_ok=True)

    used_as_back: set[Path] = set()
    processed = 0

    for i, front in enumerate(images):
        if front in used_as_back:
            continue

        print(f"── {i + 1}. {front.name}")
        print("  분석 중...", end="", flush=True)

        try:
            folder_name = sanitize(analyze_namecard(client, [front]))
        except Exception as e:
            print(f"\r  오류: {e}\n")
            continue

        print(f"\r  → {folder_name}")

        while True:
            cmd = input("  [Enter=저장  이름=수정  s=건너뜀]: ").strip()

            if cmd.lower() == "s":
                print("  건너뜀\n")
                break

            if cmd:
                folder_name = sanitize(cmd)

            if not folder_name:
                print("  폴더명이 비어있습니다.")
                continue

            # 뒷면 지정
            back_input = input("  뒷면 번호? (Enter=없음): ").strip()
            back = None
            if back_input:
                back = resolve_back(images, back_input)
                if back is None:
                    print(f"  '{back_input}' 파일을 찾을 수 없습니다.")
                    continue
                used_as_back.add(back)

            dest = copy_photos(front, back, folder_name)
            back_info = f" + {back.name}" if back else ""
            print(f"  저장: {dest}{back_info}\n")
            processed += 1
            break

    print(f"완료! ({processed}개 처리)")


if __name__ == "__main__":
    main()
