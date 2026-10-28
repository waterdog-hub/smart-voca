# smart-voca 설계서

**파일 위치**: `docs/설계_261021_smart-voca 설계서 v0.1.md`
**작성일**: 2026-10-21
**버전**: v0.1 (초안)
**설명**: 기획서 v0.6을 바탕으로 화면 구성, 모듈 구조, CSV 스키마, 진도 생성 알고리즘, 시험 로직을 정의한 설계서

---

## 1. 설계 개요

- 기획서 v0.6의 기능(F-01~F-07)과 확정 규칙을 구현 가능한 수준으로 구체화한다.
- 구조는 **화면(GUI)** 과 **핵심 로직(core)** 을 분리한다. 로직은 tkinter 없이도 테스트할 수 있게 한다.
- 설계 중 판단한 항목은 §9 "설계 결정"에 `배경 / 대안 / 결정 근거` 형식으로 기록한다.

## 2. 실행 환경과 기술 스택

| 항목 | 내용 |
|------|------|
| 운영체제 | Windows |
| 언어 | Python 3.x (표준 라이브러리 위주) |
| GUI | tkinter, ttk |
| 저장 | CSV (UTF-8 with BOM, `utf-8-sig`) |
| 테스트 | `unittest` (표준 라이브러리) |

> 테스트 실행 방법은 구현 시작 후 CLAUDE.md "테스트 및 배포" 섹션에 기록한다.

## 3. 폴더 및 파일 구조

```
smart-voca/
├── src/
│   ├── main.py                    # 프로그램 진입점 (앱 실행)
│   ├── config.py                  # 기본값 상수, 파일 경로
│   ├── models.py                  # Word, StudyRecord, DayPlanItem 데이터 클래스
│   ├── core/
│   │   ├── word_repository.py     # 단어 CSV 읽기·쓰기 (WordRepository)
│   │   ├── settings_repository.py # 설정 CSV 읽기·쓰기 (SettingsRepository)
│   │   ├── record_repository.py   # 학습 기록 CSV 읽기·쓰기 (RecordRepository)
│   │   ├── plan_repository.py     # 일차별 진도 CSV 읽기·쓰기 (PlanRepository)
│   │   ├── day_planner.py         # 일차별 진도 생성 (DayPlanner)
│   │   ├── quiz_builder.py        # 시험 문항 생성 (QuizBuilder)
│   │   └── answer_checker.py      # 정답 판정 (AnswerChecker)
│   └── gui/
│       ├── app_window.py          # 메인 창, 탭 전환 (AppWindow)
│       ├── word_list_tab.py       # 단어장 탭 (WordListTab)
│       ├── memorize_tab.py        # 암기 탭 (MemorizeTab)
│       ├── test_tab.py            # 시험 탭 (TestTab)
│       └── settings_tab.py        # 설정 탭 (SettingsTab)
├── tests/
│   ├── test_day_planner.py
│   ├── test_quiz_builder.py
│   ├── test_answer_checker.py
│   └── test_repositories.py
├── data/
│   ├── words.csv                  # 단어장 (사용자 데이터, 커밋 제외 대상 검토)
│   ├── settings.csv               # 설정
│   ├── study_record.csv           # 단어별 학습·오답 기록
│   └── day_plan.csv               # 일차별 진도
└── ai-agent/scripts/              # 프로젝트 전용 도구 (필요 시)
```

**구조 근거**
- `core/`는 화면과 분리해 단위 테스트가 가능하다.
- 파일마다 한 가지 책임만 가지게 나눠 500줄을 넘지 않도록 한다 (CLAUDE.md 개발 원칙 5).
- CSV 접근은 `*_repository.py`에만 둔다. 다른 모듈은 파일 형식을 몰라도 된다.

**코드 작성 규칙 적용**
- 모든 `.py` 파일 상단에 CLAUDE.md 형식의 헤더(작성일, 파일 위치, 목적)를 둔다.
- 함수·변수명은 영문 snake_case로 쓰고, 의미가 드러나게 짓는다. 주석과 docstring은 한글로 쓴다.

## 4. CSV 스키마

### 4.1 `data/words.csv` (단어장)

| 열 | 타입 | 필수 | 설명 |
|----|------|------|------|
| word | 문자열 | O | 영문 단어 (공백 제거 후 저장) |
| meaning | 문자열 | O | 한글 뜻, 여러 개면 `/` 구분 |

- 첫 줄은 헤더 `word,meaning`이다.
- 같은 `word`가 두 번 나오면 **첫 항목만 유지**하고 나머지는 건너뛴다. 건너뛴 개수를 화면에 알린다.
- 빈 `word` 또는 빈 `meaning` 행은 건너뛰고 알린다.

```
word,meaning
apple,사과
run,달리다/운영하다
```

### 4.2 `data/settings.csv` (설정)

| key | 기본값 | 설명 |
|-----|--------|------|
| daily_new_count | 20 | 하루 신규 단어 수 |
| daily_review_count | 5 | 하루 복습 단어 수 |
| daily_wrong_count | 5 | 하루 오답 단어 최대 수 |
| wrong_threshold | 3 | 오답 단어 판정 기준 (이 횟수 이상이면 대상) |
| test_format | multiple | `multiple`(객관식) / `subjective`(주관식) |
| test_direction | en_ko | `en_ko` / `ko_en` / `both` |
| current_day | 0 | 마지막으로 생성된 일차 (0이면 아직 진도 없음) |

- 파일이 없거나 항목이 빠지면 `config.py`의 기본값을 쓴다.
- 값이 숫자 형식이 아니거나 허용 값이 아니면 기본값으로 되돌리고 화면에 알린다.

```
key,value
daily_new_count,20
daily_review_count,5
daily_wrong_count,5
wrong_threshold,3
test_format,multiple
test_direction,en_ko
current_day,0
```

### 4.3 `data/study_record.csv` (단어별 학습·오답 기록)

| 열 | 타입 | 설명 |
|----|------|------|
| word | 문자열 | 단어 (`words.csv`의 키) |
| memorized_count | 정수 | 암기 완료 누적 횟수 |
| first_memorized_day | 정수 | 처음 외운 일차 (0이면 미암기) |
| last_memorized_date | 날짜 `YYYY-MM-DD` | 마지막 암기 날짜 |
| wrong_count | 정수 | 시험 오답 누적 횟수 |
| last_wrong_date | 날짜 `YYYY-MM-DD` | 마지막 오답 날짜 |

- 단어 목록을 새로 불러오면 없는 단어에 대해 기본 행(0, 빈 날짜)을 만든다.

### 4.4 `data/day_plan.csv` (일차별 진도)

| 열 | 타입 | 설명 |
|----|------|------|
| day | 정수 | 일차 번호 (1부터) |
| word | 문자열 | 단어 |
| assigned_type | 문자열 | `new` / `review` / `wrong` |
| done | 0 또는 1 | 암기 완료 여부 |

- 한 번 생성된 일차의 진도는 다시 만들지 않는다. 같은 날 앱을 다시 켜도 기존 진도를 보여준다.

## 5. 데이터 모델 (`models.py`)

| 클래스 | 필드 | 설명 |
|--------|------|------|
| Word | word, meaning_list | `meaning_list`는 `/`로 나눈 뜻 목록 |
| StudyRecord | word, memorized_count, first_memorized_day, last_memorized_date, wrong_count, last_wrong_date | study_record.csv 한 행 |
| DayPlanItem | day, word, assigned_type, done | day_plan.csv 한 행 |
| Settings | daily_new_count, daily_review_count, daily_wrong_count, wrong_threshold, test_format, test_direction, current_day | 설정 한 벌 |

## 6. 핵심 로직

### 6.1 진도 생성 — `DayPlanner` (`core/day_planner.py`)

**메서드**
- `create_next_day_plan(words, records, previous_day_items, settings) -> list[DayPlanItem]`
  - 새 일차 번호는 `settings.current_day + 1`이다.
  - 결과를 `PlanRepository`에 저장하고 `current_day`를 갱신한다. (저장은 호출자가 담당)
- `pick_new_words(words, records, count) -> list[Word]`
  - `memorized_count == 0`인 단어를 `words.csv` 순서대로 `count`개 고른다.
- `pick_review_words(previous_day_items, count, exclude) -> list[str]`
  - 전날 `assigned_type == new`인 단어 중 `exclude`에 없는 단어를 무작위로 `count`개 고른다.
- `pick_wrong_words(records, threshold, count, exclude) -> list[str]`
  - `wrong_count >= threshold`인 단어를 `wrong_count` 내림차순으로 `count`개 고른다. 동점은 단어장 순서로 정한다.
- `is_all_memorized(records) -> bool`
  - 모든 단어의 `memorized_count >= 1`이면 True다.

**일차별 구성 로직 (`create_next_day_plan`)**

```
if not is_all_memorized:
    new_words = pick_new_words(words, records, daily_new_count)
    review_words = pick_review_words(previous_day_items, daily_review_count, exclude=new_words)
    wrong_words = pick_wrong_words(records, wrong_threshold, daily_wrong_count, exclude=new + review)
else:
    new_words = []
    wrong_words = pick_wrong_words(records, wrong_threshold, daily_wrong_count, exclude=[])
    review_slots = daily_review_count + (daily_wrong_count - len(wrong_words))
    review_words = pick_review_words(previous_day_items, review_slots, exclude=wrong_words)
```

**규칙**
- 같은 단어는 한 일차 안에서 한 번만 들어간다. `exclude`로 막는다.
- 복습 대상(전날 신규)이 부족하면 있는 만큼만 넣는다. 전날 신규가 0개면 복습은 빈 목록이다.
- 단어가 `daily_new_count`보다 적으면 남은 만큼만 넣는다.

### 6.2 시험 문항 — `QuizBuilder` (`core/quiz_builder.py`)

- `build_quiz(words, format, direction, count, rng) -> list[QuizItem]`
  - `direction`이 `both`면 각 문항의 방향을 무작위로 정한다.
  - `en_ko`: 문제 = 영어 단어, 정답 = 뜻 목록
  - `ko_en`: 문제 = 뜻(첫 번째 뜻), 정답 = 영어 단어
- `multiple` 형식의 보기 구성
  - 정답 1개 + 오답 보기 3개 = 총 4지선다
  - 오답 보기는 같은 단어장의 다른 단어에서 뽑는다. 단어장이 4개 미만이면 시험을 만들지 않고 알린다.
  - 보기 순서는 무작위로 섞는다.
- `subjective` 형식은 보기 없이 입력만 받는다.
- 문항 수는 단어장에 있는 단어 수와 설정값 중 작은 값을 쓴다. (설정값은 시험 탭에서 고른다)

### 6.3 정답 판정 — `AnswerChecker` (`core/answer_checker.py`)

- `check_answer(quiz_item, user_answer) -> bool`
  - 입력의 앞뒤 공백을 제거하고 비교한다. 영어는 대소문자를 구분하지 않는다.
  - 정답 목록(`meaning_list`)의 항목 중 하나와 일치하면 정답이다. (뜻 여러 개 중 하나만 맞아도 정답)
  - 객관식은 선택한 보기 번호가 정답 보기 번호와 같은지 본다.
- 오답이면 `StudyRecord.wrong_count`를 1 올리고 `last_wrong_date`를 오늘로 바꾼다. 이 갱신은 `RecordRepository`를 통해 한다.

### 6.4 암기 처리 (F-05)

- 암기 탭에서 카드를 펼쳐 뜻을 확인하고 "외움"을 누르면 다음을 갱신한다.
  - `DayPlanItem.done = 1`
  - `StudyRecord.memorized_count += 1`, `first_memorized_day`(0이면 현재 일차), `last_memorized_date = 오늘`
- "다시"를 누르면 완료 처리하지 않는다.

## 7. 화면 설계 (GUI)

### 7.1 메인 창 구성

`AppWindow`가 `ttk.Notebook`으로 탭 4개를 띄운다.

| 탭 | 주요 요소 | 동작 |
|----|-----------|------|
| 단어장 | 단어 표(Treeview), 불러오기·저장 버튼, 단어 추가 입력 | CSV 불러오기·저장, 단어 추가·삭제 |
| 암기 | 오늘 일차 표시, 진도 목록, 카드(영어/뜻), 외움·다시 버튼, 진행률 | 카드 한 장씩 넘기며 암기 처리 |
| 시험 | 형식 선택(객관식/주관식), 방향 선택(영→한/한→영/양방향), 문항 수, 시작 버튼, 문항 표시 영역, 결과 요약 | 시험 진행, 채점, 오답 기록 |
| 설정 | 신규·복습·오답 수 입력, 오답 기준 입력, 시험 기본 형식·방향 | 저장 시 `settings.csv` 갱신 |

### 7.2 주요 화면 흐름

1. **첫 실행**: `words.csv`가 없으면 빈 단어장으로 시작하고 불러오기를 안내한다.
2. **암기 탭 진입**: 오늘 진도가 없으면 `DayPlanner`로 새 일차를 만든다. 있으면 기존 진도를 보여준다.
3. **시험 탭**: 설정한 형식·방향으로 문항을 만들고 한 문항씩 답을 받는다. 끝나면 정답 수와 오답 단어를 보여준다.
4. **설정 변경**: 저장하면 다음 진도 생성부터 적용된다. 이미 만든 일차 진도는 바뀌지 않는다.

### 7.3 입력 검증 메시지

| 상황 | 표시 |
|------|------|
| CSV 헤더가 `word,meaning`이 아님 | "단어 파일 형식이 맞지 않습니다. 첫 줄은 word,meaning이어야 합니다." |
| 중복 단어 | "중복된 단어 N개를 건너뛰었습니다." |
| 설정값이 숫자가 아님 | 해당 항목을 기본값으로 되돌리고 알림 |
| 단어가 4개 미만인데 객관식 시험 선택 | "객관식은 단어가 4개 이상 필요합니다." |

## 8. 테스트 계획

| 대상 | 테스트 항목 |
|------|-------------|
| DayPlanner | 1일차는 신규 20개만 나오는지, 2일차에 전날 신규 중 5개가 들어가는지, 같은 단어가 중복되지 않는지 |
| DayPlanner | 오답 3회 이상 단어만 들어가고, 횟수 많은 순으로 뽑히는지 |
| DayPlanner | 모두 외운 뒤 오답 대상이 부족하면 복습으로 채워지는지 (예: 오답 2개면 복습 8개) |
| QuizBuilder | 보기 4개, 정답 포함, 보기 중복 없음, 단어 4개 미만일 때 오류 |
| QuizBuilder | `both` 방향에서 두 방향이 모두 나오는지 |
| AnswerChecker | 대소문자·공백 무시, 뜻 여러 개 중 하나만 맞아도 정답 |
| Repositories | CSV 읽기·쓰기 왕복 후 데이터가 같은지, 헤더 오류 처리, 중복 단어 처리 |

테스트는 `core/`만 대상으로 하고 GUI는 수동으로 확인한다.

## 9. 설계 결정

### D-01 CSV 인코딩
- **배경**: 엑셀에서 CSV를 열면 한글이 깨지는 경우가 있다.
- **대안**: UTF-8, UTF-8 with BOM(`utf-8-sig`)
- **결정**: 쓰기는 `utf-8-sig`, 읽기도 `utf-8-sig`로 한다. BOM이 있어도 없어도 읽을 수 있다.

### D-02 신규 단어 순서
- **배경**: 신규 단어를 어떤 순서로 배정할지 정해야 한다.
- **대안**: 단어장 순서 / 무작위
- **결정**: 단어장 순서. 결과가 예측 가능해 테스트하기 쉽다.

### D-03 복습 단어 선정
- **배경**: 전날 외운 단어가 20개일 때 5개를 어떻게 고를지 정해야 한다.
- **대안**: 앞에서부터 5개 / 무작위 5개
- **결정**: 무작위. 같은 단어만 반복되는 것을 줄인다. 테스트에서는 난수 시드를 고정한다.

### D-04 오답 단어 선정 순서
- **배경**: 오답 3회 이상인 단어가 여러 개일 때 순서를 정해야 한다.
- **대안**: 단어장 순서 / 오답 많은 순
- **결정**: 오답 많은 순 (기획서 v0.6 Q-12). 동점은 단어장 순서.

### D-05 설정 파일 손상 처리
- **배경**: 사용자가 CSV를 직접 고칠 수 있으므로 잘못된 값이 들어올 수 있다.
- **대안**: 프로그램 종료 / 기본값으로 복구하고 알림
- **결정**: 기본값으로 복구하고 알림. 학습이 멈추지 않게 한다.

### D-06 시험 중 오답 기록 시점
- **배경**: 시험 도중 프로그램을 끄면 기록이 날아갈 수 있다.
- **대안**: 문항마다 즉시 저장 / 시험 끝나고 한 번에 저장
- **결정**: 문항마다 즉시 저장. 기록 손실을 줄인다.

### D-07 복습 후보 기준 (구현 중 변경, §6.1 수정)
- **배경**: §6.1은 복습 후보를 "전날 신규(assigned_type=new)"로 정했다. 전날이 모두 복습·오답으로 구성된 날에는 후보가 없어 빈칸을 채울 수 없다.
- **대안**: 전날 신규만 / 전날 진도 중 외운(done) 단어
- **결정**: 전날 진도 중 외운(done) 단어. 전날 신규가 없어도 복습을 채울 수 있다.

### D-08 일차 전진 방식 (구현 중 변경, §7.2 수정)
- **배경**: §7.2는 "오늘 진도가 없으면 새 일차 생성"이라고 했다. day_plan.csv에 날짜 열이 없어 날짜로 판단할 수 없다.
- **대안**: 날짜 기준 자동 생성 / 현재 일차를 모두 외운 뒤 사용자가 '다음 일차 만들기' 버튼을 누름
- **결정**: 버튼 방식. 현재 일차를 모두 외우면 버튼이 활성화된다. 날짜 열은 추가하지 않는다.

### D-09 단어 삭제 시 학습 기록 (T-01 임시 처리)
- **배경**: T-01 미정 상태에서 단어 삭제 기능을 구현해야 했다.
- **대안**: 기록도 함께 삭제 / 기록 유지
- **결정**: 기록을 유지한다. 나중에 같은 단어를 다시 추가하면 이전 기록이 살아난다. 사용자 확인으로 확정(T-01).

### D-10 암기 카드 위치 저장 (T-03 확정)
- **배경**: 앱을 껐다 켰을 때 암기 카드 위치를 기억하기로 했다.
- **대안**: 위치를 담는 설정 항목 추가 / 일차 진도 파일의 순서로 표현
- **결정**: 일차 진도 파일의 순서로 표현한다. '다시'를 누르면 그 항목을 같은 일차 안의 맨 뒤로 옮기고 `day_plan.csv`에 저장한다. 새 파일이나 설정 항목은 추가하지 않는다.

### D-11 같은 날 여러 번 시험 시 오답 집계 (T-02 확정)
- **배경**: 같은 날 시험을 여러 번 보면 오답이 중복으로 쌓인다.
- **대안**: 시험마다 집계 / 하루 한 번만 집계
- **결정**: 시험마다 집계한다. 자주 틀리는 단어가 더 빨리 오답 대상이 된다. 사용자 확인으로 확정.

## 10. 미정 사항

| 번호 | 항목 | 비고 |
|------|------|------|
| T-01 | 단어 삭제 시 학습 기록 처리 | **확정**: 기록 유지 (D-09) |
| T-02 | 같은 날 여러 번 시험 시 오답 집계 | **확정**: 시험마다 집계 (D-11) |
| T-03 | 앱 종료 시 암기 카드 위치 저장 | **확정**: 저장함 (D-10) |
| T-04 | 테스트 실행 명령 | **완료**: CLAUDE.md에 `py -3 -m unittest discover -s tests` 기록 |

미정 사항은 없습니다. 일정과 제출 형식은 실습 과제 조건으로 별도 확인이 필요합니다(기획서 Q-10, Q-11).

## 11. 변경 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| v0.1 | 2026-10-21 | 초안 작성 (구조, CSV 스키마, 진도·시험 로직, 화면, 설계 결정) |
