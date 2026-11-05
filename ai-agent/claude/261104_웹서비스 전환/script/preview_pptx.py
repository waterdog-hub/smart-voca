#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - .pptx 안의 도형·글·그림을 같은 좌표로 다시 그려 슬라이드 모습을 미리 확인한다 (근사)
# 파일 위치: ai-agent/claude/261104_웹서비스 전환/script/preview_pptx.py
#
# 실행 (도구용 가상환경, python-pptx와 Pillow 필요): python preview_pptx.py deck.pptx 출력폴더
# PowerPoint나 LibreOffice가 없는 PC에서 글 넘침, 겹침, 배치를 대략 확인하는 용도다. 실제 PowerPoint의 줄바꿈과는 조금 다를 수 있다.

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN

PX_PER_INCH = 120
FONT_FILES = {False: r"C:\Windows\Fonts\malgun.ttf", True: r"C:\Windows\Fonts\malgunbd.ttf"}
EMU = 914400


def px(emu: int) -> int:
    return round(emu / EMU * PX_PER_INCH)


def color_of(fill_or_line, default=None):
    try:
        return "#" + str(fill_or_line.fore_color.rgb)
    except Exception:
        try:
            return "#" + str(fill_or_line.color.rgb)
        except Exception:
            return default


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split(" "):
            trial = (current + " " + word).strip()
            if font.getlength(trial) <= max_width or not current:
                current = trial
                while font.getlength(current) > max_width and len(current) > 1:
                    cut = len(current)
                    while cut > 1 and font.getlength(current[:cut]) > max_width:
                        cut -= 1
                    lines.append(current[:cut])
                    current = current[cut:]
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def draw_text_frame(draw: ImageDraw.ImageDraw, shape, left, top, width, height) -> None:
    frame = shape.text_frame
    inset_l = px(frame.margin_left or 0)
    inset_t = px(frame.margin_top or 0)
    blocks = []
    total = 0.0
    for paragraph in frame.paragraphs:
        text = "".join(run.text for run in paragraph.runs)
        if not paragraph.runs:
            continue
        run = paragraph.runs[0]
        size_px = run.font.size.pt * PX_PER_INCH / 72 if run.font.size else 18 * PX_PER_INCH / 72
        font = ImageFont.truetype(FONT_FILES[bool(run.font.bold)], round(size_px))
        color = "#" + str(run.font.color.rgb) if run.font.color and run.font.color.type else "#000000"
        lines = wrap(text, font, width - 2 * inset_l)
        after = (paragraph.space_after.pt if paragraph.space_after is not None else 0) * PX_PER_INCH / 72
        block_height = len(lines) * size_px * 1.25 + after
        blocks.append((lines, font, color, size_px, paragraph.alignment, after))
        total += block_height
    anchor = frame.vertical_anchor
    y = top + inset_t
    if anchor is not None and int(anchor) == 3:  # MIDDLE
        y = top + (height - total) / 2
    for lines, font, color, size_px, alignment, after in blocks:
        for line in lines:
            line_width = font.getlength(line)
            if alignment == PP_ALIGN.CENTER:
                x = left + (width - line_width) / 2
            elif alignment == PP_ALIGN.RIGHT:
                x = left + width - inset_l - line_width
            else:
                x = left + inset_l
            draw.text((x, y), line, fill=color, font=font)
            y += size_px * 1.25
        y += after
    if y > top + height + 6 and anchor is None:
        draw.rectangle([left, top, left + width, top + height], outline="#ff0000", width=2)  # 넘침 표시


def render(presentation: Presentation, index: int, target: Path) -> None:
    slide = presentation.slides[index]
    width = round(presentation.slide_width / EMU * PX_PER_INCH)
    height = round(presentation.slide_height / EMU * PX_PER_INCH)
    background = "#ffffff"
    try:
        background = "#" + str(slide.background.fill.fore_color.rgb)
    except Exception:
        pass
    canvas = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(canvas)
    for shape in slide.shapes:
        left, top, w, h = px(shape.left), px(shape.top), px(shape.width), px(shape.height)
        kind = shape.shape_type
        if kind == MSO_SHAPE_TYPE.PICTURE:
            image = Image.open(io.BytesIO(shape.image.blob)).convert("RGBA").resize((w, h))
            canvas.paste(image, (left, top), image)
        elif kind == MSO_SHAPE_TYPE.MEDIA:
            poster = getattr(shape, "poster_frame", None)
            if poster is not None:
                image = Image.open(io.BytesIO(poster.blob)).convert("RGB").resize((w, h))
                canvas.paste(image, (left, top))
            draw.polygon([(left + w / 2 - 30, top + h / 2 - 40), (left + w / 2 - 30, top + h / 2 + 40), (left + w / 2 + 50, top + h / 2)], fill="#ffffff")
        elif kind == MSO_SHAPE_TYPE.TABLE:
            table = shape.table
            y = top
            for row in table.rows:
                x = left
                row_h = px(row.height)
                for column_index, cell in enumerate(row.cells):
                    col_w = px(table.columns[column_index].width)
                    fill = color_of(cell.fill, "#ffffff")
                    draw.rectangle([x, y, x + col_w, y + row_h], fill=fill, outline="#ffd0df")
                    run = cell.text_frame.paragraphs[0].runs[0] if cell.text_frame.paragraphs[0].runs else None
                    if run is not None:
                        size_px = run.font.size.pt * PX_PER_INCH / 72
                        font = ImageFont.truetype(FONT_FILES[bool(run.font.bold)], round(size_px))
                        lines = wrap(run.text, font, col_w - 24)
                        ty = y + (row_h - len(lines) * size_px * 1.25) / 2
                        for line in lines:
                            draw.text((x + 12, ty), line, fill="#" + str(run.font.color.rgb), font=font)
                            ty += size_px * 1.25
                    x += col_w
                y += row_h
        elif kind in (MSO_SHAPE_TYPE.AUTO_SHAPE,):
            fill = color_of(shape.fill)
            line = color_of(shape.line)
            line_w = max(1, round((shape.line.width or 0) / 12700 * PX_PER_INCH / 72)) if line else 0
            name = shape.auto_shape_type
            if "ROUNDED" in str(name):
                radius = int(min(w, h) * (shape.adjustments[0] if len(shape.adjustments) else 0.16))
                draw.rounded_rectangle([left, top, left + w, top + h], radius=radius, fill=fill, outline=line, width=line_w)
            elif "ARROW" in str(name):
                draw.polygon([(left, top + h * 0.25), (left + w * 0.55, top + h * 0.25), (left + w * 0.55, top), (left + w, top + h / 2),
                              (left + w * 0.55, top + h), (left + w * 0.55, top + h * 0.75), (left, top + h * 0.75)], fill=fill)
            else:
                draw.rectangle([left, top, left + w, top + h], fill=fill, outline=line, width=line_w)
            if shape.has_text_frame and shape.text_frame.text.strip():
                draw_text_frame(draw, shape, left, top, w, h)
        elif kind == MSO_SHAPE_TYPE.TEXT_BOX:
            draw_text_frame(draw, shape, left, top, w, h)
    canvas.save(target)


def main() -> int:
    if len(sys.argv) != 3:
        print("사용법: preview_pptx.py deck.pptx 출력폴더")
        return 2
    deck = Presentation(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for index in range(len(deck.slides)):
        render(deck, index, out / f"slide_{index + 1:02d}.png")
    print(f"{len(deck.slides)}장을 {out}에 그렸습니다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
