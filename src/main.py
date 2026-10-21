#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 프로그램 진입점: 메인 창을 띄운다
# 파일 위치: src/main.py

from gui.app_window import AppWindow


def main() -> None:
    app = AppWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
