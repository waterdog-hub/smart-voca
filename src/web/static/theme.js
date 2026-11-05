// 2026-11-05 - smart-voca - 테마 색 고르기. 선택은 이 기기의 브라우저에만 저장한다 (이슈 #21)
// 파일 위치: src/web/static/theme.js
// 머리글에서 바로 실행해 화면이 그려지기 전에 색을 입힌다. 저장소를 못 쓰면 기본 색으로 보인다.

"use strict";

const THEME_KEY = "smart-voca-theme";
const THEMES = ["peach", "lavender", "mint", "sky", "lemon", "cocoa"];

function readSavedTheme() {
  try {
    const saved = window.localStorage.getItem(THEME_KEY);
    return THEMES.includes(saved) ? saved : null;
  } catch {
    return null;
  }
}

function applyTheme(name) {
  document.documentElement.dataset.theme = name;
}

const savedTheme = readSavedTheme();
if (savedTheme) applyTheme(savedTheme);

document.addEventListener("DOMContentLoaded", () => {
  const buttons = [...document.querySelectorAll("[data-theme-choice]")];
  const current = document.documentElement.dataset.theme || THEMES[0];
  const mark = (name) => buttons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.themeChoice === name)));
  mark(current);
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const name = button.dataset.themeChoice;
      if (!THEMES.includes(name)) return;
      applyTheme(name);
      mark(name);
      try {
        window.localStorage.setItem(THEME_KEY, name);
      } catch {
        // 저장하지 못해도 이번 화면에서는 바뀐다
      }
    });
  });
});
