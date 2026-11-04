#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-11-04 - smart-voca - 시험 생성 (core.quiz_builder), 서버 채점 (core.answer_checker), 시험 기록 (API 설계 §6)
# 파일 위치: src/web/services/test_service.py

import json
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import CHOICE_COUNT
from core.answer_checker import AnswerChecker
from core.quiz_builder import QuizBuilder
from core.word_service import WordService
from models import QuizItem, Word as CoreWord
from web.db.base import utc_now
from web.db.tables import TEST_DIRECTIONS, TEST_FORMATS, TestAttempt, TestAttemptItem, TestSession
from web.errors import ApiError
from web.repositories import test_repository, word_repository
from web.services.plan_service import today_in_korea

ATTEMPT_LIFETIME = timedelta(hours=24)
MIN_QUESTION_COUNT = 1
MAX_QUESTION_COUNT = 200
DEFAULT_QUESTION_COUNT = 10
CHOICE_ERROR = "목록에서 골라 주세요."
ANSWER_ERROR = "답안 형식이 올바르지 않습니다. 새로고침해 주세요."
EXPIRED_MESSAGE = "시험 시간이 지나 폐기되었습니다. 새로 시작해 주세요."
ALREADY_SUBMITTED_MESSAGE = "이미 제출한 시험입니다."
NO_WORDS_MESSAGE = "시험을 볼 단어가 없습니다. 먼저 단어를 추가하세요."
ANSWER_SEPARATOR = " / "


@dataclass(frozen=True)
class QuestionResult:
    item: TestAttemptItem
    correct: bool
    your_answer: str | None
    correct_answer: str


@dataclass(frozen=True)
class SubmitResult:
    total: int
    score: int
    results: list[QuestionResult]


def accuracy_percent(score: int, total: int) -> int:
    # 데스크톱과 같은 계산이다 (D-19). CSV 저장소 모듈은 M11에 지울 수 있어 가져오지 않는다
    return round(score * 100 / total) if total else 0


def minimum_words(test_format: str) -> int:
    return CHOICE_COUNT if test_format == "multiple" else 1


def item_choices(item: TestAttemptItem) -> list[str]:
    return json.loads(item.choices) if item.choices else []


def _to_quiz_item(item: TestAttemptItem) -> QuizItem:
    # 저장한 문항을 core 형식으로 되돌려 데스크톱과 같은 판정 규칙을 쓴다
    return QuizItem(
        word="",
        question=item.question,
        answers=json.loads(item.answers),
        direction=item.direction,
        choices=item_choices(item),
        correct_index=-1 if item.correct_index is None else item.correct_index,
    )


def _correct_answer_text(item: TestAttemptItem) -> str:
    if item.choices:
        return item_choices(item)[item.correct_index]
    return ANSWER_SEPARATOR.join(json.loads(item.answers))


def _your_answer_text(item: TestAttemptItem, answer: int | str | None) -> str | None:
    if answer is None:
        return None
    return item_choices(item)[answer] if item.choices else answer


def _is_valid_answer(item: TestAttemptItem, answer: int | str) -> bool:
    if item.choices:
        return isinstance(answer, int) and 0 <= answer < len(item_choices(item))
    return isinstance(answer, str)


class TestService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def find_open_attempt(self) -> TestAttempt | None:
        return test_repository.find_open_attempt(self.db, self.user_id, utc_now())

    def start(self, test_format: str, test_direction: str, count: int) -> TestAttempt:
        problems = {}
        if test_format not in TEST_FORMATS:
            problems["test_format"] = CHOICE_ERROR
        if test_direction not in TEST_DIRECTIONS:
            problems["test_direction"] = CHOICE_ERROR
        if not MIN_QUESTION_COUNT <= count <= MAX_QUESTION_COUNT:
            problems["count"] = f"{MIN_QUESTION_COUNT} 이상 {MAX_QUESTION_COUNT} 이하로 입력해 주세요."
        if problems:
            raise ApiError(400, "VALIDATION_FAILED", "입력값을 확인해 주세요.", fields=problems)

        words = word_repository.list_all_active_words(self.db, self.user_id)
        if not words:
            raise ApiError(422, "TEST_NOT_POSSIBLE", NO_WORDS_MESSAGE)
        word_ids = {word.word: word.id for word in words}
        core_words = [CoreWord(word.word, WordService.split_meanings(word.meaning)) for word in words]
        try:
            quiz = QuizBuilder().build_quiz(core_words, test_format, test_direction, count)
        except ValueError as error:
            # 객관식 보기를 만들 단어가 부족할 때 core가 던진다 (구현 계획 §2.3)
            raise ApiError(422, "TEST_NOT_POSSIBLE", str(error)) from error

        # 진행 중인 시험은 회원당 하나다. 화면이 먼저 확인을 받는다 (D-23)
        test_repository.expire_open_attempts(self.db, self.user_id)
        now = utc_now()
        attempt = TestAttempt(
            user_id=self.user_id,
            test_format=test_format,
            test_direction=test_direction,
            created_at=now,
            expires_at=now + ATTEMPT_LIFETIME,
        )
        self.db.add(attempt)
        self.db.flush()
        self.db.add_all(
            TestAttemptItem(
                attempt_id=attempt.id,
                position=position,
                word_id=word_ids[quiz_item.word],
                direction=quiz_item.direction,
                question=quiz_item.question,
                choices=json.dumps(quiz_item.choices, ensure_ascii=False) if quiz_item.choices else None,
                correct_index=quiz_item.correct_index if quiz_item.choices else None,
                answers=json.dumps(quiz_item.answers, ensure_ascii=False),
            )
            for position, quiz_item in enumerate(quiz, start=1)
        )
        self.db.commit()
        return attempt

    def _find_attempt(self, attempt_id: int) -> TestAttempt:
        attempt = test_repository.find_attempt(self.db, self.user_id, attempt_id)
        if attempt is None:
            raise ApiError(404, "NOT_FOUND", "찾을 수 없습니다.")
        return attempt

    def _raise_if_not_open(self, attempt: TestAttempt) -> None:
        if attempt.status == "submitted":
            raise ApiError(409, "TEST_ALREADY_SUBMITTED", ALREADY_SUBMITTED_MESSAGE)
        if attempt.status == "expired" or attempt.expires_at <= utc_now():
            raise ApiError(409, "TEST_EXPIRED", EXPIRED_MESSAGE)

    def get_open_attempt_items(self, attempt_id: int) -> tuple[TestAttempt, list[TestAttemptItem]]:
        attempt = self._find_attempt(attempt_id)
        self._raise_if_not_open(attempt)
        return attempt, test_repository.list_items(self.db, attempt.id)

    def describe_attempt(self, attempt_id: int) -> tuple[str, TestSession | None] | None:
        """화면이 쓸 시험 상태 (open, submitted, expired)와 결과를 돌려준다. 없으면 None이다."""
        attempt = test_repository.find_attempt(self.db, self.user_id, attempt_id)
        if attempt is None:
            return None
        if attempt.status == "submitted":
            return "submitted", test_repository.find_session_of_attempt(
                self.db, self.user_id, attempt.id
            )
        expired = attempt.status == "expired" or attempt.expires_at <= utc_now()
        return ("expired" if expired else "open"), None

    def submit(self, attempt_id: int, answers: dict[int, int | str]) -> SubmitResult:
        attempt = self._find_attempt(attempt_id)
        self._raise_if_not_open(attempt)
        items = test_repository.list_items(self.db, attempt.id)
        items_by_id = {item.id: item for item in items}
        # 다른 시험의 문항이나 형식이 틀린 답은 화면 오류이므로 일부만 채점하지 않고 거절한다
        for item_id, answer in answers.items():
            if item_id not in items_by_id or not _is_valid_answer(items_by_id[item_id], answer):
                raise ApiError(400, "VALIDATION_FAILED", ANSWER_ERROR)

        now = utc_now()
        if not test_repository.mark_submitted(self.db, self.user_id, attempt.id, now):
            self.db.rollback()
            raise ApiError(409, "TEST_ALREADY_SUBMITTED", ALREADY_SUBMITTED_MESSAGE)

        checker = AnswerChecker()
        today = today_in_korea()
        results = []
        for item in items:
            answer = answers.get(item.id)
            # 빈 칸은 답하지 않은 것으로 본다
            if isinstance(answer, str) and not answer.strip():
                answer = None
            correct = answer is not None and checker.check_answer(_to_quiz_item(item), answer)
            # 풀지 않은 단어는 틀린 증거가 아니다. 일찍 제출해도 오답 기록이 부풀지 않게 한다
            if answer is not None and not correct:
                test_repository.add_wrong(self.db, self.user_id, item.word_id, today)
            results.append(
                QuestionResult(item, correct, _your_answer_text(item, answer), _correct_answer_text(item))
            )
        score = sum(1 for result in results if result.correct)
        self.db.add(
            TestSession(
                user_id=self.user_id,
                attempt_id=attempt.id,
                taken_at=now,
                test_format=attempt.test_format,
                test_direction=attempt.test_direction,
                total=len(items),
                score=score,
            )
        )
        try:
            self.db.commit()
        except IntegrityError as error:
            # attempt_id 유일 제약이 두 번째 방어선이다 (데이터 모델 §3.7)
            self.db.rollback()
            raise ApiError(409, "TEST_ALREADY_SUBMITTED", ALREADY_SUBMITTED_MESSAGE) from error
        return SubmitResult(total=len(items), score=score, results=results)

    def history(self, limit: int, offset: int) -> tuple[list[TestSession], int, int]:
        """(이번 쪽의 기록, 전체 시험 횟수, 전체 정답률)을 돌려준다."""
        count, total, score = test_repository.summarize_sessions(self.db, self.user_id)
        sessions = test_repository.list_sessions(self.db, self.user_id, limit, offset)
        return sessions, count, accuracy_percent(score, total)
