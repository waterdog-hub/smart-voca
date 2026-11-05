#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 오픈 글꼴(주아, 고운돋움)에서 필요한 글자만 남겨 웹용 woff2로 만든다 (이슈 #21)
# 파일 위치: ai-agent/scripts/make_fonts.py
#
# 실행 (프로젝트 루트): .venv\Scripts\python ai-agent/scripts/make_fonts.py 원본글꼴폴더
#   원본글꼴폴더에는 Jua-Regular.ttf와 GowunDodum-Regular.ttf가 있어야 한다 (구글 폰트 저장소 google/fonts의 ofl/ 아래).
# 결과: src/web/static/fonts/Jua.woff2, GowunDodum.woff2
# fonttools와 brotli가 필요하다 (requirements-dev.txt). 서비스 실행에는 필요 없다.
#
# 글꼴은 SIL Open Font License 1.1이다. 글자를 줄이는 것은 수정에 해당하므로 저작권 고지와 라이선스를
# 결과 폴더에 함께 둔다 (src/web/static/fonts/README.md). 두 글꼴 모두 예약된 글꼴 이름(Reserved Font Name)이 없다.

import sys
from pathlib import Path

from fontTools import subset

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "src" / "web" / "static" / "fonts"
FONTS = {"Jua-Regular.ttf": "Jua.woff2", "GowunDodum-Regular.ttf": "GowunDodum.woff2"}

# 글자 범위: 영문·숫자·기호, 문장 부호, 화살표와 표시 기호, 한글 자모, 한글 음절 전체 (회원 이름이나 뜻에 드문 글자가 있어도 같은 글꼴로 보이게 한다.
# 글꼴이 갖지 않은 글자는 건너뛰므로 결과는 글꼴이 가진 글자만 담는다)
EXTRA_RANGES = [
    (0x0020, 0x007E),  # 기본 라틴
    (0x00A0, 0x00FF),  # 라틴-1 (· × ÷ 등)
    (0x2010, 0x2027),  # 줄표, 따옴표, 말줄임표
    (0x2030, 0x203A),
    (0x2190, 0x2193),  # ← ↑ → ↓
    (0x2212, 0x2212),
    (0x25B2, 0x25B2),  # ▲ (정렬 표시)
    (0x25BC, 0x25BC),  # ▼
    (0x25CF, 0x25CF),
    (0x2713, 0x2714),  # ✓
    (0x3001, 0x3003),
    (0x3008, 0x3011),
    (0x3131, 0x3163),  # 한글 자모
]


HANGUL_SYLLABLES = (0xAC00, 0xD7A3)


def build_codepoints() -> list[int]:
    codepoints = set(range(HANGUL_SYLLABLES[0], HANGUL_SYLLABLES[1] + 1))
    for start, end in EXTRA_RANGES:
        codepoints.update(range(start, end + 1))
    return sorted(codepoints)


def subset_font(source: Path, target: Path, codepoints: list[int]) -> None:
    options = subset.Options()
    options.flavor = "woff2"
    options.hinting = False  # 화면 글꼴이라 힌트를 빼 용량을 줄인다
    options.layout_features = ["kern", "liga", "ccmp", "locl", "mark", "mkmk"]
    # 저작권(0), 상표(7 제외), 라이선스(13, 14) 이름 정보를 남긴다
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]
    options.notdef_outline = True
    font = subset.load_font(str(source), options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=codepoints)
    subsetter.subset(font)
    subset.save_font(font, str(target), options)
    font.close()


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: make_fonts.py 원본글꼴폴더")
        return 2
    source_dir = Path(sys.argv[1])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    codepoints = build_codepoints()
    print(f"남길 글자 {len(codepoints):,}개")
    for source_name, target_name in FONTS.items():
        source = source_dir / source_name
        if not source.exists():
            print(f"원본이 없습니다: {source}")
            return 1
        target = OUTPUT_DIR / target_name
        subset_font(source, target, codepoints)
        print(f"{target_name}: {source.stat().st_size / 1024:,.0f}KB -> {target.stat().st_size / 1024:,.0f}KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
