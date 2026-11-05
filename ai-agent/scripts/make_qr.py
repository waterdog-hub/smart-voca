#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 시연 접속 주소를 QR 코드 그림으로 만든다 (발표용)
# 파일 위치: ai-agent/scripts/make_qr.py
#
# 실행 (프로젝트 루트): .venv\Scripts\python ai-agent/scripts/make_qr.py https://시연주소 [--out 파일.png] [--label 아래에 쓸 글]
# 시연 주소는 demo_server.py start를 실행할 때마다 바뀐다. 발표 직전에 나온 주소로 다시 만들어 PPT의 QR 그림을 바꾼다.
# 기본 출력은 현재 폴더의 demo_qr.png다. qrcode와 Pillow가 필요하다 (requirements-dev.txt).

import argparse
import sys
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_Q

KOREAN_FONTS = (r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf")
BOX_SIZE = 16  # 칸 하나의 픽셀. 멀리서도 읽히도록 크게 만든다
BORDER = 3  # 가장자리 흰 칸 수 (규격은 4칸이지만 슬라이드의 흰 카드 안에서 충분하다)


def make_qr(text: str, label: str | None) -> Image.Image:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_Q, box_size=BOX_SIZE, border=BORDER)
    qr.add_data(text)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#2d2433", back_color="white").convert("RGB")
    if not label:
        return image
    font = None
    for path in KOREAN_FONTS:
        if Path(path).exists():
            font = ImageFont.truetype(path, 34)
            break
    font = font or ImageFont.load_default()
    canvas = Image.new("RGB", (image.width, image.height + 70), "white")
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    width = draw.textlength(label, font=font)
    draw.text(((canvas.width - width) / 2, image.height + 10), label, fill="#2d2433", font=font)
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description="시연 접속 주소를 QR 코드로 만듭니다.")
    parser.add_argument("url", help="QR로 만들 주소 (예: https://abcd.ngrok-free.dev)")
    parser.add_argument("--out", default="demo_qr.png", help="저장할 파일 (기본: demo_qr.png)")
    parser.add_argument("--label", help="QR 아래에 쓸 글 (생략하면 쓰지 않는다)")
    arguments = parser.parse_args()
    if not arguments.url.strip():
        print("주소가 비어 있습니다.")
        return 2
    image = make_qr(arguments.url.strip(), arguments.label)
    out = Path(arguments.out)
    image.save(out)
    print(f"QR 코드를 만들었습니다: {out.resolve()} ({image.width}x{image.height})")
    print("휴대폰 카메라로 읽어 주소가 맞는지 확인한 뒤 PPT에 넣으세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
