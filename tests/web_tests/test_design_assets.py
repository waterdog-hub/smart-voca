#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 디자인 자원(글꼴, 마스코트, 아이콘, 커서, 테마)이 빠짐없이 연결되어 있는지 확인한다 (이슈 #21)
# 파일 위치: tests/web_tests/test_design_assets.py

import re
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from web_tests.support import PROJECT_ROOT, AuthTestCase

STATIC_DIR = PROJECT_ROOT / "src" / "web" / "static"
FONT_DIR = STATIC_DIR / "fonts"
MAX_FONT_BYTES = 600 * 1024  # 글꼴 한 파일의 한도. 첫 화면 로딩을 지키려는 기준이다
MAX_CURSOR_SIZE = 128  # 브라우저가 허용하는 커서 이미지의 최대 크기


def read_css() -> str:
    return (STATIC_DIR / "app.css").read_text(encoding="utf-8")


def css_static_urls() -> set[str]:
    return set(re.findall(r'url\("(/static/[^"]+)"\)', read_css()))


class StaticAssetsTest(AuthTestCase):
    def test_every_url_in_the_stylesheet_points_to_an_existing_file(self):
        urls = css_static_urls()
        self.assertGreaterEqual(len(urls), 8)
        for url in sorted(urls):
            with self.subTest(url=url):
                self.assertTrue((STATIC_DIR / url.removeprefix("/static/")).is_file())
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_design_files_are_served_with_the_right_types(self):
        expected = {
            "/static/mascot.svg": "image/svg+xml",
            "/static/cursor-paw.svg": "image/svg+xml",
            "/static/cursor-paw-click.svg": "image/svg+xml",
            "/static/book-pink.svg": "image/svg+xml",
            "/static/fonts/Jua.woff2": "font/woff2",
            "/static/fonts/GowunDodum.woff2": "font/woff2",
        }
        for url, content_type in expected.items():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.headers["content-type"].startswith(content_type))

    def test_svg_files_are_well_formed(self):
        for path in sorted(STATIC_DIR.glob("*.svg")):
            with self.subTest(file=path.name):
                root = ElementTree.fromstring(path.read_text(encoding="utf-8"))
                self.assertTrue(root.tag.endswith("svg"))

    def test_cursor_images_have_an_explicit_size_within_the_browser_limit(self):
        for name in ("cursor-paw.svg", "cursor-paw-click.svg"):
            with self.subTest(file=name):
                root = ElementTree.fromstring((STATIC_DIR / name).read_text(encoding="utf-8"))
                width, height = int(root.get("width")), int(root.get("height"))
                self.assertLessEqual(max(width, height), MAX_CURSOR_SIZE)

    def test_cursor_hotspots_are_inside_the_image(self):
        for hotspot in re.findall(r'cursor:\s*url\("[^"]+"\)\s+(\d+)\s+(\d+)', read_css()):
            self.assertTrue(all(0 <= int(value) < MAX_CURSOR_SIZE for value in hotspot))


class FontTest(unittest.TestCase):
    def test_font_files_are_real_woff2_and_small(self):
        for name in ("Jua.woff2", "GowunDodum.woff2"):
            with self.subTest(font=name):
                data = (FONT_DIR / name).read_bytes()
                self.assertEqual(data[:4], b"wOF2")
                self.assertLess(len(data), MAX_FONT_BYTES)

    def test_license_and_credits_ship_with_the_fonts(self):
        readme = (FONT_DIR / "README.md").read_text(encoding="utf-8")
        for needed in ("SIL Open Font License", "주아", "고운돋움", "Jua Project Authors", "Gowun Dodum Project Authors"):
            self.assertIn(needed, readme)
        for name in ("OFL-Jua.txt", "OFL-GowunDodum.txt"):
            text = (FONT_DIR / name).read_text(encoding="utf-8")
            self.assertIn("SIL OPEN FONT LICENSE Version 1.1", text)

    def test_stylesheet_declares_both_fonts_with_swap(self):
        css = read_css()
        for family in ("Jua", "Gowun Dodum"):
            block = re.search(r'@font-face\s*\{[^}]*font-family:\s*"%s"[^}]*\}' % family, css)
            self.assertIsNotNone(block, family)
            self.assertIn("font-display: swap", block.group(0))

    def test_headings_and_buttons_use_the_display_font_at_a_single_weight(self):
        css = read_css()
        group = css[css.rindex("h1, h2, h3, strong"):]
        for selector in ("button", ".button-link", ".stat-number", ".card-word"):
            self.assertIn(selector, group)
        self.assertIn("font-family: var(--font-display)", group)
        self.assertIn("font-weight: 400", group)

    def test_body_text_falls_back_to_system_fonts(self):
        match = re.search(r"--font-body:\s*([^;]+);", read_css())
        self.assertIsNotNone(match)
        self.assertIn("Malgun Gothic", match.group(1))
        self.assertIn("sans-serif", match.group(1))


class ThemeTest(AuthTestCase):
    def css_themes(self):
        return set(re.findall(r':root\[data-theme="(\w+)"\]', read_css()))

    def script_themes(self):
        match = re.search(r"const THEMES = \[([^\]]+)\]", (STATIC_DIR / "theme.js").read_text(encoding="utf-8"))
        return set(re.findall(r'"(\w+)"', match.group(1)))

    def test_stylesheet_and_script_know_the_same_themes(self):
        self.assertEqual(self.css_themes(), self.script_themes())
        self.assertEqual(len(self.css_themes()), 6)

    def test_settings_page_offers_every_theme(self):
        self.signup_and_login()
        html = self.client.get("/settings").text
        offered = set(re.findall(r'data-theme-choice="(\w+)"', html))
        self.assertEqual(offered, self.css_themes())
        self.assertIn('aria-pressed="false"', html)

    def test_each_theme_defines_every_color_variable(self):
        css = read_css()
        needed = ("--bg", "--bg-dot", "--accent", "--accent-dark", "--accent-ink", "--on-accent", "--accent-soft", "--accent-softer", "--line")
        for theme in sorted(self.css_themes()):
            block = re.search(r':root\[data-theme="%s"\]\s*\{([^}]*)\}' % theme, css).group(1)
            for variable in needed:
                with self.subTest(theme=theme, variable=variable):
                    self.assertRegex(block, re.escape(variable) + r":")

    def test_every_page_loads_the_theme_script_and_preloads_the_fonts(self):
        pages = ["/login", "/signup", "/"]
        self.signup_and_login()
        pages += ["/words", "/settings"]
        for path in pages:
            with self.subTest(path=path):
                html = self.client.get(path).text
                self.assertIn('<script src="/static/theme.js"></script>', html)
                self.assertIn('href="/static/fonts/Jua.woff2" as="font"', html)
                self.assertIn('href="/static/fonts/GowunDodum.woff2" as="font"', html)
                self.assertNotIn("<script>", html)

    def test_theme_script_runs_before_the_page_is_painted(self):
        # defer나 async가 붙으면 화면이 기본 색으로 먼저 그려졌다가 바뀐다
        html = self.client.get("/login").text
        tag = re.search(r'<script src="/static/theme.js"[^>]*>', html).group(0)
        self.assertNotIn("defer", tag)
        self.assertNotIn("async", tag)


if __name__ == "__main__":
    unittest.main()
