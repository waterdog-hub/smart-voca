# 발표 자료 만들기 도구

**파일 위치**: `ai-agent/claude/261104_웹서비스 전환/script/README.md`
**작성일**: 2026-11-05
**설명**: 발표용 화면 캡처, 시연 영상, PPT 초안을 다시 만드는 방법 (화면 디자인을 바꿨을 때 다시 돌린다)

## 준비 (한 번만)

프로젝트 가상환경과 별도로 도구용 가상환경을 만든다. PPT와 영상 도구를 프로젝트에 섞지 않기 위해서다.

```
py -3 -m venv C:\도구\발표도구
C:\도구\발표도구\Scripts\python -m pip install python-pptx imageio imageio-ffmpeg pillow numpy
```

QR 도구(`qrcode`, `Pillow`)는 프로젝트 개발용 패키지다 (`requirements-dev.txt`, `.venv\Scripts\python -m pip install -r requirements-dev.txt`).

## 순서 (프로젝트 루트에서)

| 순서 | 명령 | 하는 일 |
|------|------|---------|
| 1 | `.venv\Scripts\python "ai-agent/claude/261104_웹서비스 전환/script/capture_presentation_assets.py" "ai-agent/claude/261104_웹서비스 전환/발표/assets"` | 임시 DB에 예시 회원과 학습 기록을 만들고, 임시 서버와 헤드리스 브라우저로 PC·휴대폰 화면 17장을 찍고 시연 영상의 프레임을 모은다. 영상만 다시 찍으려면 끝에 `--video-only`. 개발 DB는 건드리지 않는다 |
| 2 | `C:\도구\발표도구\Scripts\python "ai-agent/claude/261104_웹서비스 전환/script/make_video.py" "ai-agent/claude/261104_웹서비스 전환/발표/assets" 2.0` | 프레임을 mp4로 만든다. 끝의 숫자는 재생 빠르기(2.0이면 2배속, 약 32초) |
| 3 | `C:\도구\발표도구\Scripts\python "ai-agent/claude/261104_웹서비스 전환/script/build_presentation.py" "ai-agent/claude/261104_웹서비스 전환/발표"` | 캡처, 영상, QR 그림으로 `smart-voca 발표 초안 v0.2.pptx`를 만든다. 슬라이드 노트의 대본은 발표 구성안 문서에서 읽는다 |
| 4 | `C:\도구\발표도구\Scripts\python "ai-agent/claude/261104_웹서비스 전환/script/preview_pptx.py" "발표/….pptx" 미리보기폴더` | PPT 안의 도형·글·그림을 같은 좌표로 다시 그려 슬라이드마다 PNG로 저장한다 (PowerPoint가 없는 PC에서 글 넘침과 배치를 대략 확인하는 용도) |

## 발표 당일 주소와 QR 바꾸기

시연 주소는 `demo_server.py start`를 실행할 때마다 바뀐다. 서버를 띄운 뒤 나온 주소로 다음을 한다.

```
.venv\Scripts\python ai-agent/scripts/make_qr.py https://나온주소 --out demo_qr.png
```

PowerPoint 3번째 슬라이드에서 주소 글자를 고치고, QR 그림을 오른쪽 클릭 → "그림 바꾸기"로 `demo_qr.png`를 넣는다. **휴대폰 카메라로 QR을 읽어 주소가 맞는지 확인한다.**

## 알아 둘 점

- 중간 재료(`assets/frames/`, `assets/screens/`)는 용량이 커서 Git에 넣지 않는다. 최종 결과물(PPT, `demo.mp4`, `assets/ppt/`의 줄인 그림)만 남긴다.
- PPT는 PowerPoint로 직접 열어 확인하지 못하고 `preview_pptx.py`의 근사 그림으로만 확인했다. 열어서 글 넘침, 영상 재생, 글꼴을 한 번 확인한다. 글꼴은 맑은 고딕이다.
- 시연 영상의 보카 발바닥 커서는 화면에 덧씌운 그림이다 (실제 커서는 화면 녹화에 찍히지 않는다).

## 변경 이력

- v0.1 (2026-11-05): 최초 작성.
