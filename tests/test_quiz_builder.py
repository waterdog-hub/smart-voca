#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-10-21 - smart-voca - 시험 문항 생성 단위 테스트
# 파일 위치: tests/test_quiz_builder.py

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.quiz_builder import QuizBuilder  # noqa: E402
from models import Word  # noqa: E402


def make_words(count):
    return [Word(word=f"word{index:02d}", meaning_list=[f"뜻{index:02d}", f"의미{index:02d}"])
            for index in range(count)]


class QuizBuilderTest(unittest.TestCase):

    def setUp(self):
        self.builder = QuizBuilder(rng=random.Random(7))

    def test_multiple_choice_has_four_unique_options_including_answer(self):
        words = make_words(10)
        quiz = self.builder.build_quiz(words, "multiple", "en_ko", 5)

        for item in quiz:
            self.assertEqual(len(item.choices), 4)
            self.assertEqual(len(set(item.choices)), 4)
            self.assertEqual(item.choices[item.correct_index], "/".join(
                next(word.meaning_list for word in words if word.word == item.word)))

    def test_multiple_choice_requires_four_words(self):
        with self.assertRaises(ValueError):
            self.builder.build_quiz(make_words(3), "multiple", "en_ko", 3)

    def test_ko_en_uses_words_as_options(self):
        words = make_words(10)
        quiz = self.builder.build_quiz(words, "multiple", "ko_en", 3)

        for item in quiz:
            self.assertEqual(item.direction, "ko_en")
            self.assertEqual(item.choices[item.correct_index], item.word)
            self.assertTrue(all(choice.startswith("word") for choice in item.choices))

    def test_both_direction_produces_both_directions(self):
        words = make_words(20)
        quiz = self.builder.build_quiz(words, "subjective", "both", 20)
        directions = {item.direction for item in quiz}

        self.assertEqual(directions, {"en_ko", "ko_en"})

    def test_subjective_item_has_no_choices(self):
        quiz = self.builder.build_quiz(make_words(5), "subjective", "en_ko", 5)
        self.assertTrue(all(item.choices == [] for item in quiz))

    def test_count_is_capped_by_word_total(self):
        quiz = self.builder.build_quiz(make_words(4), "subjective", "en_ko", 10)
        self.assertEqual(len(quiz), 4)

    def test_ko_en_distractors_never_share_meaning_with_answer(self):
        words = [
            Word(word="a", meaning_list=["하나의"]),
            Word(word="an", meaning_list=["하나의"]),
            Word(word="apple", meaning_list=["사과"]),
            Word(word="book", meaning_list=["책"]),
            Word(word="dog", meaning_list=["개"]),
            Word(word="tree", meaning_list=["나무"]),
        ]
        meanings_by_word = {word.word: set(word.meaning_list) for word in words}
        quiz = QuizBuilder(rng=random.Random(3)).build_quiz(words, "multiple", "ko_en", len(words))

        for item in quiz:
            for choice in item.choices:
                if choice != item.word:
                    self.assertFalse(meanings_by_word[choice] & meanings_by_word[item.word],
                                     f"{item.word} 문항에 같은 뜻 보기 {choice}가 있음")

    def test_subjective_ko_en_accepts_every_word_with_same_meaning(self):
        words = [
            Word(word="a", meaning_list=["하나의"]),
            Word(word="an", meaning_list=["하나의"]),
            Word(word="book", meaning_list=["책"]),
            Word(word="dog", meaning_list=["개"]),
        ]
        quiz = QuizBuilder(rng=random.Random(5)).build_quiz(words, "subjective", "ko_en", len(words))
        item = next(entry for entry in quiz if entry.word == "a")

        self.assertCountEqual(item.answers, ["a", "an"])


if __name__ == "__main__":
    unittest.main()
