#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 발표 PPT 초안(.pptx)을 만든다 (캡처, 시연 영상, QR 포함)
# 파일 위치: ai-agent/claude/261104_웹서비스 전환/script/build_presentation.py
#
# 실행 (도구용 가상환경, python-pptx와 Pillow 필요): python build_presentation.py 발표폴더
#   발표폴더/assets/에 capture_presentation_assets.py와 make_video.py의 결과(screens/, demo.mp4, demo_poster.png)와
#   QR 그림(qr_placeholder.png)이 있어야 한다. 대본은 발표 구성안 문서에서 읽어 슬라이드 노트에 넣는다.
# 결과: 발표폴더/smart-voca 발표 초안 v0.1.pptx
# PowerPoint가 이 PC에 없어 화면으로 직접 확인하지 못한다. 대신 글꼴 크기로 상자에 글이 들어가는지 계산해 경고한다.

import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

WORK_DIR = Path(__file__).resolve().parent.parent
OUTLINE = WORK_DIR / "보고서_261105_최종 발표 구성안 v0.1.md"
FONT = "Malgun Gothic"
FONT_FILES = {False: r"C:\Windows\Fonts\malgun.ttf", True: r"C:\Windows\Fonts\malgunbd.ttf"}

# 화면 디자인과 같은 복숭아 테마 색
BG = "FFF5F8"
INK = "2D2433"
MUTED = "5F5668"
ACCENT = "D6336C"
ACCENT_DARK = "A61E4D"
ACCENT_SOFT = "FFE3EC"
ACCENT_LINE = "FFD0DF"
MINT = "DCF7EA"
MINT_LINE = "B6E8CF"
WARM = "FFF0D6"
WARM_LINE = "FFDCA3"
SKY = "E1F0FF"
SKY_LINE = "BCDCFA"
WHITE = "FFFFFF"

SLIDE_W, SLIDE_H = 13.333, 7.5
MARGIN = 0.7
warnings: list[str] = []


def rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color)


# ── 글이 상자에 들어가는지 계산 ────────────────────────────────
def estimate_height(text: str, width_in: float, size_pt: float, bold: bool, line_gap: float = 1.25) -> float:
    """상자 안쪽 폭에서 단어 단위로 줄바꿈했을 때 필요한 높이(인치)를 어림한다."""
    font_file = FONT_FILES[bold]
    font = ImageFont.truetype(font_file, 100)  # 100px 기준으로 재고 비율로 줄인다
    scale = size_pt / 100
    max_width = width_in * 72
    lines = 0
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        current = ""
        count = 1
        for word in words:
            trial = (current + " " + word).strip()
            if font.getlength(trial) * scale <= max_width or not current:
                current = trial
                # 한 단어가 한 줄보다 길면 글자 단위로 쪼개진다
                while font.getlength(current) * scale > max_width:
                    cut = len(current)
                    while cut > 1 and font.getlength(current[:cut]) * scale > max_width:
                        cut -= 1
                    current = current[cut:]
                    count += 1
            else:
                count += 1
                current = word
        lines += count
    return lines * size_pt * line_gap / 72


# ── 도형과 글 ──────────────────────────────────────────────────
def set_background(slide, color: str) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = rgb(color)


def add_box(slide, x, y, w, h, fill=WHITE, line=ACCENT_LINE, line_width=2.25, shape=MSO_SHAPE.ROUNDED_RECTANGLE,
            radius=0.12, dashed=False, name=None):
    box = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        box.adjustments[0] = radius
    box.fill.solid()
    box.fill.fore_color.rgb = rgb(fill)
    if line:
        box.line.color.rgb = rgb(line)
        box.line.width = Pt(line_width)
        if dashed:
            from pptx.enum.dml import MSO_LINE
            box.line.dash_style = MSO_LINE.DASH
    else:
        box.line.fill.background()
    box.shadow.inherit = False
    if name:
        box.name = name
    return box


def add_text(slide, x, y, w, h, paragraphs, size=18, bold=False, color=INK, align=PP_ALIGN.LEFT,
             anchor=MSO_ANCHOR.TOP, name=None, space_after=0, check=True, margin=0.0):
    """paragraphs: 문자열 목록 또는 (문자열, 옵션 딕셔너리) 목록. 옵션: size, bold, color."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(margin)
    frame.margin_top = frame.margin_bottom = Inches(margin)
    frame.vertical_anchor = anchor
    needed = 0.0
    items = paragraphs if isinstance(paragraphs, list) else [paragraphs]
    for index, item in enumerate(items):
        text, options = (item, {}) if isinstance(item, str) else item
        p_size = options.get("size", size)
        p_bold = options.get("bold", bold)
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = options.get("align", align)
        paragraph.space_after = Pt(options.get("space_after", space_after))
        run = paragraph.add_run()
        run.text = text
        run.font.name = FONT
        run.font.size = Pt(p_size)
        run.font.bold = p_bold
        run.font.color.rgb = rgb(options.get("color", color))
        needed += estimate_height(text, w - 2 * margin, p_size, p_bold) + options.get("space_after", space_after) / 72
    if check and needed > h + 0.02:
        warnings.append(f"글이 넘칠 수 있음: '{items[0] if isinstance(items[0], str) else items[0][0]}'[:20] 필요 {needed:.2f}in > 상자 {h:.2f}in")
    if name:
        box.name = name
    return box


def add_title(slide, text):
    add_text(slide, MARGIN, 0.45, SLIDE_W - 2 * MARGIN, 0.85, text, size=36, bold=True, color=ACCENT_DARK,
             anchor=MSO_ANCHOR.MIDDLE, name="제목")


def add_picture(slide, path, x, y, w=None, h=None, alt="", rounded=False, name=None):
    kwargs = {}
    if w is not None:
        kwargs["width"] = Inches(w)
    if h is not None:
        kwargs["height"] = Inches(h)
    picture = slide.shapes.add_picture(str(path), Inches(x), Inches(y), **kwargs)
    if rounded:
        picture.auto_shape_type = MSO_SHAPE.ROUNDED_RECTANGLE
    picture._element.nvPicPr.cNvPr.set("descr", alt)
    if name:
        picture.name = name
    return picture


def add_notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def read_scripts() -> dict[str, str]:
    """구성안 문서에서 슬라이드별 대본을 읽는다."""
    text = OUTLINE.read_text(encoding="utf-8")
    result = {}
    for match in re.finditer(r"### (S\d)\.[^\n]*\n(?:.*\n)*?- \*\*대본\*\*: \"([^\n]*)\"", text):
        result[match.group(1)] = match.group(2)
    return result


# ── 자원 준비 ──────────────────────────────────────────────────
def rasterize_svg(svg: Path, target: Path, size: int) -> None:
    """Chrome으로 SVG를 투명 배경 PNG로 만든다."""
    chrome = next(p for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe") if Path(p).exists())
    html = target.with_suffix(".html")
    html.write_text(f"<body style='margin:0;background:transparent'><img src='{svg.as_uri()}' style='width:{size}px;height:{size}px'></body>",
                    encoding="utf-8")
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--allow-file-access-from-files", "--hide-scrollbars",
                    f"--screenshot={target}", f"--window-size={size},{size}", "--default-background-color=00000000",
                    html.as_uri()], check=True, capture_output=True)
    html.unlink()


def prepare_assets(assets: Path, static_dir: Path) -> dict[str, Path]:
    ppt = assets / "ppt"
    ppt.mkdir(exist_ok=True)
    out: dict[str, Path] = {}
    for name in ("mascot",):
        target = ppt / f"{name}.png"
        if not target.exists():
            rasterize_svg(static_dir / f"{name}.svg", target, 600)
        out[name] = target
    for color in ("pink", "mint", "sky", "yellow"):
        target = ppt / f"book-{color}.png"
        if not target.exists():
            rasterize_svg(static_dir / f"book-{color}.svg", target, 300)
        out[f"book-{color}"] = target
    screens = assets / "screens"
    for source in sorted(screens.glob("0*.png")):
        target = ppt / (source.stem + ".jpg")
        Image.open(source).convert("RGB").resize((1600, 900)).save(target, quality=88)
        out[source.stem] = target
    for source in sorted(screens.glob("1*.png")):
        target = ppt / (source.stem + ".jpg")
        image = Image.open(source).convert("RGB")
        image.resize((600, round(600 * image.height / image.width))).save(target, quality=90)
        out[source.stem] = target
    out["themes"] = make_theme_collage(screens, ppt / "themes.jpg")
    out["poster"] = assets / "demo_poster.png"
    out["video"] = assets / "demo.mp4"
    out["qr"] = assets / "qr_placeholder.png"
    return out


def make_theme_collage(screens: Path, target: Path) -> Path:
    names = (("peach", "복숭아 (기본)"), ("lavender", "라벤더"), ("mint", "민트"), ("sky", "하늘"), ("lemon", "레몬"), ("cocoa", "코코아"))
    tile_w, tile_h, gap, label_h = 800, 450, 28, 56
    cols, rows = 3, 2
    canvas = Image.new("RGB", (cols * tile_w + (cols + 1) * gap, rows * (tile_h + label_h) + (rows + 1) * gap), "#" + BG)
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(FONT_FILES[True], 34)
    for index, (key, label) in enumerate(names):
        image = Image.open(screens / f"theme_{key}.png").convert("RGB").resize((tile_w, tile_h))
        x = gap + (index % cols) * (tile_w + gap)
        y = gap + (index // cols) * (tile_h + label_h + gap)
        canvas.paste(image, (x, y))
        draw.rectangle([x - 1, y - 1, x + tile_w, y + tile_h], outline="#" + ACCENT_LINE, width=3)
        draw.text((x + 8, y + tile_h + 8), label, fill="#" + INK, font=font)
    canvas.save(target, quality=90)
    return target


# ── 슬라이드 ───────────────────────────────────────────────────
def build(folder: Path) -> Path:
    folder = folder.resolve()
    assets = folder / "assets"
    static_dir = Path(__file__).resolve().parents[4] / "src" / "web" / "static"
    pics = prepare_assets(assets, static_dir)
    scripts = read_scripts()
    presentation = Presentation()
    presentation.slide_width = Inches(SLIDE_W)
    presentation.slide_height = Inches(SLIDE_H)
    blank = presentation.slide_layouts[6]
    core = presentation.core_properties
    core.title = "smart-voca 발표"
    core.author = "smart-voca"
    core.subject = "영어 단어 암기·시험 학습 서비스"

    # 1. 표지와 문제
    s = presentation.slides.add_slide(blank)
    set_background(s, BG)
    add_box(s, 0.6, 0.8, 7.9, 5.9, fill=ACCENT_SOFT, line=ACCENT, line_width=3, dashed=True, radius=0.07, name="표지 카드")
    add_text(s, 1.1, 1.2, 7.0, 1.2, "smart-voca", size=60, bold=True, color=ACCENT_DARK, name="제목")
    add_text(s, 1.1, 2.45, 7.0, 0.6, "영어 단어 암기 · 시험 학습 서비스", size=26, bold=True, name="부제")
    add_text(s, 1.1, 3.4, 7.0, 2.3, [
        ("어디까지 외웠는지 관리하기 어렵다", {"space_after": 6}),
        ("자꾸 틀리는 단어를 다시 보기 어렵다", {"space_after": 6}),
        ("→ 진도를 자동으로 만들고, 시험으로 확인하고, 틀린 단어를 다시 내 준다", {"bold": True, "color": ACCENT_DARK}),
    ], size=20, name="문제")
    add_text(s, 1.1, 5.95, 7.0, 0.5, "2026.11.13 · 발표자: 은형주", size=16, color=MUTED, name="발표 정보")
    add_picture(s, pics["mascot"], 9.0, 1.6, w=3.9, alt="고양이 마스코트 보카", name="마스코트")
    add_text(s, 9.0, 5.7, 3.9, 0.5, "고양이 '보카'가 함께해요", size=18, bold=True, color=ACCENT_DARK, align=PP_ALIGN.CENTER, name="마스코트 설명")
    add_notes(s, scripts.get("S1", ""))

    # 2. 무엇을 만들었나
    s = presentation.slides.add_slide(blank)
    set_background(s, BG)
    add_title(s, "무엇을 만들었나")
    features = [
        ("단어장 고르기", "초급~심화 단어장을 골라 담기", MINT, MINT_LINE, "book-mint"),
        ("오늘의 암기", "신규·복습·오답을 자동 구성", WARM, WARM_LINE, "book-yellow"),
        ("시험과 채점", "객관식·주관식을 서버가 채점", SKY, SKY_LINE, "book-sky"),
        ("회원·휴대폰", "가입·변경·탈퇴, 폰에서도 동일", ACCENT_SOFT, ACCENT_LINE, "book-pink"),
    ]
    for index, (title, desc, fill, line, icon) in enumerate(features):
        x = MARGIN + index * 2.99
        add_box(s, x, 1.45, 2.8, 1.35, fill=fill, line=line, name=f"기능 카드 {index + 1}")
        add_picture(s, pics[icon], x + 0.12, 1.57, w=0.7, alt="", name=f"기능 아이콘 {index + 1}")
        add_text(s, x + 0.9, 1.55, 1.8, 0.45, title, size=18, bold=True, name=f"기능 이름 {index + 1}")
        add_text(s, x + 0.9, 2.02, 1.8, 0.7, desc, size=14, color=MUTED, name=f"기능 설명 {index + 1}")
    shots = [("02_pc_home", "홈 · 오늘의 티켓"), ("04_pc_memorize", "암기 카드"), ("05_pc_test_result", "시험 결과")]
    for index, (key, caption) in enumerate(shots):
        x = MARGIN + index * 4.1
        add_box(s, x - 0.06, 3.0, 3.9 + 0.12, 2.19 + 0.12, fill=WHITE, line=ACCENT_LINE, line_width=3, name=f"화면 틀 {index + 1}")
        add_picture(s, pics[key], x, 3.06, w=3.9, alt=caption, rounded=True, name=f"화면 {index + 1}")
        add_text(s, x, 5.35, 3.9, 0.4, caption, size=16, bold=True, color=ACCENT_DARK, align=PP_ALIGN.CENTER, name=f"화면 설명 {index + 1}")
    add_text(s, MARGIN, 6.1, SLIDE_W - 2 * MARGIN, 0.7, "가입 → 단어장 고르기 → 오늘의 진도 암기 → 시험 → 기록과 오답 복습",
             size=22, bold=True, color=INK, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name="흐름")
    add_notes(s, scripts.get("S2", ""))

    # 3. 시연 안내
    s = presentation.slides.add_slide(blank)
    set_background(s, BG)
    add_title(s, "직접 접속해 보세요")
    add_box(s, MARGIN, 1.6, 7.2, 1.35, fill=WHITE, line=ACCENT, line_width=3, name="주소 카드")
    add_text(s, MARGIN + 0.3, 1.6, 6.6, 1.35, "https://(발표 당일 주소)", size=30, bold=True, color=ACCENT_DARK,
             anchor=MSO_ANCHOR.MIDDLE, name="접속 주소")
    add_text(s, MARGIN, 3.3, 7.2, 2.9, [
        ("① 주소를 열고 Visit 버튼을 누르세요", {"space_after": 12}),
        ("② 가입은 아무 이메일 형식이면 됩니다 (예: a@b.com)", {"space_after": 12}),
        ("③ 실제 비밀번호와 개인정보는 쓰지 마세요", {"bold": True, "color": ACCENT_DARK}),
    ], size=22, name="접속 안내")
    add_box(s, 8.55, 1.45, 4.1, 4.1, fill=WHITE, line=ACCENT_LINE, line_width=3, name="QR 카드")
    add_picture(s, pics["qr"], 8.7, 1.6, w=3.8, alt="접속 주소 QR 코드(예시. 발표 직전에 교체)", name="QR 코드")
    add_text(s, 8.55, 5.7, 4.1, 0.9, "예시 QR입니다. 발표 직전에 만든 주소 QR로 바꾸세요", size=14, color=MUTED,
             align=PP_ALIGN.CENTER, name="QR 설명")
    add_notes(s, scripts.get("S3", "") + "\n\n[준비] 발표 직전에 서버를 띄운 뒤 나온 주소로 이 슬라이드의 주소 글자와 QR 그림을 바꾼다. QR은 .venv\\Scripts\\python ai-agent/scripts/make_qr.py 주소 --out qr.png 로 만들고, 그림을 오른쪽 클릭 → 그림 바꾸기로 교체한다.")

    # 4. 시연 영상 (플랜 B)
    s = presentation.slides.add_slide(blank)
    set_background(s, BG)
    add_title(s, "동작 영상 (라이브 시연이 안 될 때)")
    add_box(s, 1.85, 1.4, 9.64, 5.42, fill=WHITE, line=ACCENT_LINE, line_width=3, name="영상 틀")
    s.shapes.add_movie(str(pics["video"]), Inches(1.95), Inches(1.46), Inches(9.44), Inches(5.31),
                       poster_frame_image=str(pics["poster"]), mime_type="video/mp4")
    s.shapes[-1].name = "시연 영상"
    s.shapes[-1]._element.nvPicPr.cNvPr.set("descr", "단어장 담기, 암기, 시험까지 약 30초의 동작 영상")
    add_notes(s, "라이브 시연이 안 될 때 이 영상을 재생한다 (영상을 클릭하면 재생). 약 30초 분량: 단어장 담기 → 일차 만들기 → 암기 3장 → 시험 3문항 → 결과.\n"
                 "라이브 시연이 잘 되면 이 슬라이드는 건너뛰거나 숨김 처리한다 (슬라이드 쇼 → 슬라이드 숨기기).")

    # 5. AI와 어떻게 만들었나
    s = presentation.slides.add_slide(blank)
    set_background(s, BG)
    add_title(s, "AI와 어떻게 만들었나")
    steps = [("10/21~28", "데스크톱 앱 완성", MINT, MINT_LINE), ("11/4", "설계 문서 12개", WARM, WARM_LINE), ("11/5", "웹 서비스 구현", ACCENT_SOFT, ACCENT_LINE)]
    for index, (date, text, fill, line) in enumerate(steps):
        x = MARGIN + index * 4.1
        add_box(s, x, 1.45, 3.7, 1.35, fill=fill, line=line, name=f"단계 {index + 1}")
        add_text(s, x + 0.2, 1.52, 3.3, 0.5, date, size=18, bold=True, color=ACCENT_DARK, name=f"단계 날짜 {index + 1}")
        add_text(s, x + 0.2, 2.02, 3.3, 0.65, text, size=22, bold=True, name=f"단계 설명 {index + 1}")
        if index < 2:
            arrow = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + 3.74), Inches(1.95), Inches(0.32), Inches(0.35))
            arrow.fill.solid()
            arrow.fill.fore_color.rgb = rgb(ACCENT)
            arrow.line.fill.background()
            arrow.shadow.inherit = False
            arrow.name = f"화살표 {index + 1}"
    flow = ["결정과 이유 (이슈)", "설계 문서", "구현", "테스트", "내 승인", "커밋"]
    for index, label in enumerate(flow):
        x = MARGIN + index * 2.0
        add_box(s, x, 3.3, 1.8, 1.05, fill=WHITE, line=ACCENT, line_width=2.5, name=f"작업 순서 {index + 1}")
        add_text(s, x + 0.1, 3.3, 1.6, 1.05, label, size=16, bold=True, color=ACCENT_DARK, align=PP_ALIGN.CENTER,
                 anchor=MSO_ANCHOR.MIDDLE, name=f"작업 순서 글 {index + 1}")
    add_text(s, MARGIN, 4.55, SLIDE_W - 2 * MARGIN, 0.45, "큰 작업마다 이 순서를 지켰어요", size=18, color=MUTED, align=PP_ALIGN.CENTER, name="순서 설명")
    add_box(s, MARGIN, 5.2, SLIDE_W - 2 * MARGIN, 1.6, fill=ACCENT_SOFT, line=ACCENT_LINE, name="사례 카드")
    add_text(s, MARGIN + 0.35, 5.2, SLIDE_W - 2 * MARGIN - 0.7, 1.6, [
        ("사례: 단어를 직접 입력하던 방식 → 준비된 단어장에서 고르는 방식 (제 요청)", {"bold": True, "color": ACCENT_DARK, "space_after": 4}),
        "바꾼 이유와 영향 범위가 이슈와 설계 문서에 남아 있어요",
    ], size=20, anchor=MSO_ANCHOR.MIDDLE, name="사례")
    add_notes(s, scripts.get("S4", ""))

    # 6. 품질과 보안
    s = presentation.slides.add_slide(blank)
    set_background(s, BG)
    add_title(s, "품질과 보안")
    stats = [("546", "자동 테스트", MINT, MINT_LINE), ("238", "화면 점검 항목", WARM, WARM_LINE),
             ("34", "API 엔드포인트", SKY, SKY_LINE), ("15", "데이터 테이블", ACCENT_SOFT, ACCENT_LINE)]
    for index, (number, label, fill, line) in enumerate(stats):
        x = MARGIN + index * 2.99
        add_box(s, x, 1.45, 2.8, 1.9, fill=fill, line=line, name=f"숫자 카드 {index + 1}")
        add_text(s, x, 1.55, 2.8, 1.05, number, size=54, bold=True, color=ACCENT_DARK, align=PP_ALIGN.CENTER,
                 anchor=MSO_ANCHOR.MIDDLE, name=f"숫자 {index + 1}")
        add_text(s, x, 2.62, 2.8, 0.5, label, size=18, bold=True, align=PP_ALIGN.CENTER, name=f"숫자 설명 {index + 1}")
    add_box(s, MARGIN, 3.75, SLIDE_W - 2 * MARGIN, 3.0, fill=WHITE, line=ACCENT_LINE, name="보안 카드")
    add_text(s, MARGIN + 0.4, 3.9, SLIDE_W - 2 * MARGIN - 0.8, 2.7, [
        ("비밀번호는 해시로만 저장해요 (argon2)", {"space_after": 8}),
        ("다른 회원의 데이터는 볼 수 없어요 (테스트로 확인)", {"space_after": 8}),
        ("시험 정답은 제출하기 전에는 서버가 내보내지 않아요", {"space_after": 8}),
        "탈퇴하면 회원 데이터를 바로 지워요",
    ], size=22, anchor=MSO_ANCHOR.MIDDLE, name="보안")
    add_notes(s, scripts.get("S5", ""))

    # 7. 한계와 마무리
    s = presentation.slides.add_slide(blank)
    set_background(s, BG)
    add_title(s, "한계와 다음 단계")
    add_box(s, MARGIN, 1.45, 5.85, 3.9, fill=WARM, line=WARM_LINE, name="한계 카드")
    add_text(s, MARGIN + 0.35, 1.6, 5.15, 0.5, "아직 못 한 일", size=22, bold=True, color=ACCENT_DARK, name="한계 제목")
    add_text(s, MARGIN + 0.35, 2.2, 5.15, 3.0, [
        ("구글·카카오 로그인은 구현했지만 실제 제공자로는 확인하지 못했어요", {"space_after": 10}),
        ("많은 사람이 동시에 쓰는 부하 시험은 하지 않았어요", {"space_after": 10}),
        "단어 목록의 출처 확인이 남아 있어요",
    ], size=20, name="한계")
    add_box(s, 6.78, 1.45, 5.85, 3.9, fill=MINT, line=MINT_LINE, name="다음 단계 카드")
    add_text(s, 7.13, 1.6, 5.15, 0.5, "다음 단계", size=22, bold=True, color=ACCENT_DARK, name="다음 단계 제목")
    add_text(s, 7.13, 2.2, 5.15, 3.0, [
        ("호스팅(Render)과 메일(Resend)을 정해 두었고, 상용화 단계에서 적용해요", {"space_after": 10}),
        ("약관·개인정보 처리방침 페이지를 만들어요", {"space_after": 10}),
        "구글·카카오 앱을 등록해 실제 로그인을 확인해요",
    ], size=20, name="다음 단계")
    add_text(s, MARGIN, 5.75, SLIDE_W - 2 * MARGIN, 0.8, "감사합니다 · 질문 받겠습니다", size=34, bold=True, color=ACCENT_DARK,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name="마무리")
    add_notes(s, scripts.get("S6", ""))

    # 부록 1. 휴대폰 화면
    s = presentation.slides.add_slide(blank)
    set_background(s, BG)
    add_title(s, "부록 · 휴대폰에서도 같은 화면")
    phones = [("10_phone_home", "홈"), ("11_phone_nav_more", "하단 탭 바와 더보기"), ("12_phone_history", "시험 기록 카드")]
    for index, (key, caption) in enumerate(phones):
        height = 4.85
        image = Image.open(pics[key])
        width = height * image.width / image.height
        x = 1.75 + index * 3.95
        add_picture(s, pics[key], x + (2.5 - width) / 2 + 0.0, 1.4, h=height, alt=caption, rounded=True, name=f"휴대폰 화면 {index + 1}")
        add_text(s, x - 0.5, 6.35, 3.5, 0.45, caption, size=16, bold=True, color=ACCENT_DARK, align=PP_ALIGN.CENTER, name=f"휴대폰 설명 {index + 1}")
    add_notes(s, "질문이 나오면 보여 주는 부록. 휴대폰 폭(375px)에서 하단 탭 바로 바뀌고, 표는 카드로 바뀐다.")

    # 부록 2. 테마 색
    s = presentation.slides.add_slide(blank)
    set_background(s, BG)
    add_title(s, "부록 · 테마 색 6가지")
    collage = Image.open(pics["themes"])
    width = SLIDE_W - 2 * MARGIN
    height = width * collage.height / collage.width
    add_picture(s, pics["themes"], MARGIN, 1.45, w=width, alt="테마 색 6가지(복숭아, 라벤더, 민트, 하늘, 레몬, 코코아)", name="테마 모음")
    add_text(s, MARGIN, 1.45 + height + 0.15, width, 0.45, "설정 화면에서 고르고, 이 기기의 브라우저에만 저장돼요", size=16, color=MUTED,
             align=PP_ALIGN.CENTER, name="테마 설명")
    add_notes(s, "질문이 나오면 보여 주는 부록. 테마는 설정 화면에서 바꾸고 새로고침해도 유지된다.")

    # 부록 3. 예상 질문
    s = presentation.slides.add_slide(blank)
    set_background(s, BG)
    add_title(s, "부록 · 예상 질문")
    rows = [
        ("단어 출처와 저작권은?", "프로젝트의 표본 목록이며 출처 확인 전이라 시판 단어장은 넣지 않았어요"),
        ("초급·중급·고급 기준은?", "목록 순서 기준이에요. 실제 난이도순은 아니에요"),
        ("소셜 로그인은 되나요?", "구현과 가짜 제공자 테스트까지 했고, 실제 확인은 앱 등록 뒤예요"),
        ("보안은 어떻게 했나요?", "비밀번호 해시, 회원별 데이터 격리, 정답 비공개, 탈퇴 시 즉시 삭제예요"),
        ("몇 명까지 쓰나요?", "시연은 10명 이내예요. 부하 시험은 하지 않았어요"),
        ("AI는 무엇을 했나요?", "방향과 화면은 제가 정하고 승인했고, AI는 구현·테스트·문서를 맡았어요"),
    ]
    table_shape = s.shapes.add_table(len(rows) + 1, 2, Inches(MARGIN), Inches(1.4), Inches(SLIDE_W - 2 * MARGIN), Inches(5.3))
    table_shape.name = "예상 질문 표"
    table = table_shape.table
    table.columns[0].width = Inches(3.7)
    table.columns[1].width = Inches(SLIDE_W - 2 * MARGIN - 3.7)

    def fill_cell(cell, text, bold, color, background):
        cell.fill.solid()
        cell.fill.fore_color.rgb = rgb(background)
        frame = cell.text_frame
        frame.word_wrap = True
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        paragraph = frame.paragraphs[0]
        run = paragraph.add_run()
        run.text = text
        run.font.name = FONT
        run.font.size = Pt(16)
        run.font.bold = bold
        run.font.color.rgb = rgb(color)

    fill_cell(table.cell(0, 0), "질문", True, WHITE, ACCENT)
    fill_cell(table.cell(0, 1), "한 줄 답", True, WHITE, ACCENT)
    for index, (question, answer) in enumerate(rows, start=1):
        background = WHITE if index % 2 else ACCENT_SOFT
        fill_cell(table.cell(index, 0), question, True, ACCENT_DARK, background)
        fill_cell(table.cell(index, 1), answer, False, INK, background)
        need = estimate_height(answer, SLIDE_W - 2 * MARGIN - 3.7 - 0.2, 16, False)
        if need > 0.7:
            warnings.append(f"표 칸이 높아질 수 있음: {answer[:20]}")
    add_notes(s, "전체 질문과 답은 발표 구성안 문서 §6에 있다.")

    target = folder / "smart-voca 발표 초안 v0.1.pptx"
    presentation.save(str(target))
    return target


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: build_presentation.py 발표폴더")
        return 2
    target = build(Path(sys.argv[1]))
    print(f"만들었습니다: {target} ({target.stat().st_size / 1024 / 1024:.1f}MB)")
    for message in warnings:
        print("경고:", message)
    print("글 넘침 경고", len(warnings), "건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
