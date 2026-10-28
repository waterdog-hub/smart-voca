#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 시험 문항 생성 (객관식 보기, 방향 설정, 같은 뜻 단어 처리) (QuizBuilder)
# 파일 위치: src/core/quiz_builder.py

import random
from typing import List, Optional

from config import CHOICE_COUNT
from models import QuizItem, Word


class QuizBuilder:
    """단어장에서 시험 문항을 만든다.

    같은 뜻을 가진 단어(예: a, an 모두 '하나의')는 서로의 정답이 될 수 있다.
    그래서 'ko_en' 문항에서는 같은 뜻 단어를 오답 보기로 쓰지 않고, 주관식 정답에는 같은 뜻 단어를 모두 넣는다 (설계 D-21).
    """

    def __init__(self, rng: Optional[random.Random] = None):
        self._rng = rng or random.Random()

    def build_quiz(self, words: List[Word], test_format: str, test_direction: str, count: int) -> List[QuizItem]:
        """문항 목록을 만든다.

        test_format: multiple(객관식) / subjective(주관식)
        test_direction: en_ko / ko_en / both
        count는 단어 수보다 크면 단어 수만큼만 만든다.
        """
        if test_format == "multiple" and len(words) < CHOICE_COUNT:
            raise ValueError(f"객관식은 단어가 {CHOICE_COUNT}개 이상 필요합니다.")

        selected_words = self._rng.sample(words, min(count, len(words)))
        quiz_items: List[QuizItem] = []
        for word in selected_words:
            direction = self._choose_direction(test_direction)
            if test_format == "multiple":
                quiz_items.append(self._build_choice_item(word, words, direction))
            else:
                quiz_items.append(self._build_subjective_item(word, words, direction))
        return quiz_items

    def _choose_direction(self, test_direction: str) -> str:
        """both이면 문항마다 방향을 무작위로 고른다."""
        if test_direction == "both":
            return self._rng.choice(["en_ko", "ko_en"])
        return test_direction

    def _build_subjective_item(self, word: Word, words: List[Word], direction: str) -> QuizItem:
        """주관식 문항: 보기 없이 답을 입력받는다."""
        if direction == "en_ko":
            return QuizItem(word=word.word, question=word.word,
                            answers=list(word.meaning_list), direction=direction)
        return QuizItem(word=word.word, question=word.meaning_text,
                        answers=self._english_answers(word, words), direction=direction)

    def _build_choice_item(self, word: Word, words: List[Word], direction: str) -> QuizItem:
        """객관식 문항: 정답 1개와 오답 보기 3개를 섞는다."""
        correct_option = self._option_text(word, direction)
        distractor_options = self._distractor_options(word, words, direction, correct_option)

        choices = [correct_option] + distractor_options
        self._rng.shuffle(choices)
        correct_index = choices.index(correct_option)

        if direction == "en_ko":
            question = word.word
            answers = list(word.meaning_list)
        else:
            question = word.meaning_text
            answers = self._english_answers(word, words)

        return QuizItem(word=word.word, question=question, answers=answers,
                        direction=direction, choices=choices, correct_index=correct_index)

    def _option_text(self, word: Word, direction: str) -> str:
        """보기에 쓰는 글자. en_ko는 뜻, ko_en은 영어 단어다."""
        return word.meaning_text if direction == "en_ko" else word.word

    def _distractor_options(self, word: Word, words: List[Word], direction: str, correct_option: str) -> List[str]:
        """같은 단어장의 다른 단어에서 오답 보기를 뽑는다.
        중복 보기와 같은 뜻을 가진 단어는 오답 보기로 쓰지 않는다 (같은 뜻이면 정답이 둘이 되기 때문).
        """
        other_options = []
        for other in words:
            if other.word == word.word or shares_meaning(word, other):
                continue
            option = self._option_text(other, direction)
            if option != correct_option and option not in other_options:
                other_options.append(option)

        if len(other_options) < CHOICE_COUNT - 1:
            raise ValueError(f"'{word.word}' 문항의 보기를 만들 단어가 부족합니다.")
        return self._rng.sample(other_options, CHOICE_COUNT - 1)

    def _english_answers(self, word: Word, words: List[Word]) -> List[str]:
        """뜻을 보고 쓸 수 있는 영어 정답 목록: 원래 단어와 같은 뜻을 가진 단어 전부."""
        answers = [word.word]
        for other in words:
            if other.word != word.word and shares_meaning(word, other) and other.word not in answers:
                answers.append(other.word)
        return answers


def shares_meaning(first: Word, second: Word) -> bool:
    """두 단어가 뜻을 하나라도 공유하면 True다."""
    return bool(set(first.meaning_list) & set(second.meaning_list))
