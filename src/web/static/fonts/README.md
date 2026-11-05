# 웹 글꼴

화면에 쓰는 글꼴 두 가지다 (이슈 #21). 모두 SIL Open Font License 1.1이며, 상업적 사용과 재배포가 허용된다. 글꼴 자체를 단독으로 파는 것은 허용되지 않는다.

| 파일 | 글꼴 | 저작권 | 쓰는 곳 | 라이선스 전문 |
|------|------|--------|---------|---------------|
| `Jua.woff2` | 주아 (BM JUA) | Copyright 2018 The BM JUA Project Authors (라이선스 문서에는 "The Jua Project Authors"로 적혀 있다) | 제목, 버튼, 메뉴, 숫자 | `OFL-Jua.txt` |
| `GowunDodum.woff2` | 고운돋움 | Copyright 2021 The Gowun Dodum Project Authors (https://github.com/yangheeryu/Gowun-Dodum) | 본문 | `OFL-GowunDodum.txt` |

## 수정 사항
원본에서 글자를 줄였다 (영문·숫자·문장 부호·화살표·한글 자모·한글 음절, 힌트 제거, woff2 압축). 글꼴 이름은 바꾸지 않았다. 두 글꼴의 라이선스 문서에는 예약된 글꼴 이름(Reserved Font Name)이 선언되어 있지 않다. 글꼴이 갖지 않은 글자(주아의 `·`, 화살표 등)는 다음 글꼴로 대신 보인다.

## 다시 만드는 법
원본은 구글 폰트 저장소의 `ofl/jua/Jua-Regular.ttf`, `ofl/gowundodum/GowunDodum-Regular.ttf`다. 한 폴더에 내려받은 뒤 프로젝트 루트에서 실행한다 (`fonttools`와 `brotli`는 `requirements-dev.txt`에 있다).

```
.venv\Scripts\python ai-agent/scripts/make_fonts.py 원본글꼴폴더
```
