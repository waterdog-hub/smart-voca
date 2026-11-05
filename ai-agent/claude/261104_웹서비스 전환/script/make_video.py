#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-05 - smart-voca - 캡처한 프레임으로 시연 영상(mp4)을 만든다
# 파일 위치: ai-agent/claude/261104_웹서비스 전환/script/make_video.py
#
# 실행 (도구용 가상환경, imageio와 imageio-ffmpeg 필요): python make_video.py 출력폴더 [빠르기]
#   출력폴더에는 capture_presentation_assets.py가 만든 frames/와 frames.json이 있어야 한다.
#   빠르기(기본 1.0)를 1.5처럼 주면 그만큼 빠르게 재생한다 (발표용 짧은 영상).
# 결과: 출력폴더/demo.mp4 (H.264, 1280x720, 15fps), 출력폴더/demo_poster.png (첫 장면 그림)

import json
import sys
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image

FPS = 15
SIZE = (1280, 720)


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("사용법: make_video.py 출력폴더 [빠르기]")
        return 2
    folder = Path(sys.argv[1])
    speed = float(sys.argv[2]) if len(sys.argv) == 3 else 1.0
    index = json.loads((folder / "frames.json").read_text(encoding="utf-8"))
    if not index:
        print("프레임이 없습니다.")
        return 1
    duration = index[-1]["t"] / speed
    total = int(duration * FPS) + 1
    writer = imageio.get_writer(str(folder / "demo.mp4"), fps=FPS, codec="libx264", quality=7, macro_block_size=1,
                                ffmpeg_params=["-pix_fmt", "yuv420p"])
    cache: dict[str, np.ndarray] = {}
    cursor = 0
    for number in range(total):
        moment = number / FPS * speed
        # 그 시각 이전의 마지막 프레임을 쓴다 (화면은 바뀔 때만 새로 찍히므로 같은 장면이 이어진다)
        while cursor + 1 < len(index) and index[cursor + 1]["t"] <= moment:
            cursor += 1
        name = index[cursor]["file"]
        if name not in cache:
            image = Image.open(folder / "frames" / name).convert("RGB")
            if image.size != SIZE:
                image = image.resize(SIZE)
            cache.clear()  # 한 장씩만 기억해 메모리를 아낀다
            cache[name] = np.asarray(image)
        writer.append_data(cache[name])
    writer.close()
    Image.open(folder / "frames" / index[min(5, len(index) - 1)]["file"]).convert("RGB").save(folder / "demo_poster.png")
    print(f"demo.mp4: {total}장, {duration:.1f}초, {(folder / 'demo.mp4').stat().st_size / 1024 / 1024:.1f}MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
