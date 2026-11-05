// 2026-11-05 - smart-voca - 휴대폰 하단 탭 바의 "더보기" 열기·닫기 (이슈 #21)
// 파일 위치: src/web/static/nav.js
// 데스크톱에서는 더보기 버튼이 보이지 않고 메뉴 전체가 항상 펼쳐져 있다 (CSS).

"use strict";

const moreButton = document.getElementById("nav-more-button");
const morePanel = document.getElementById("nav-more-panel");

function setMoreOpen(open) {
  morePanel.classList.toggle("open", open);
  moreButton.setAttribute("aria-expanded", String(open));
}

if (moreButton && morePanel) {
  moreButton.addEventListener("click", () => setMoreOpen(!morePanel.classList.contains("open")));
  // 바깥을 누르거나 Esc를 누르면 닫는다
  document.addEventListener("click", (event) => {
    if (!morePanel.contains(event.target) && !moreButton.contains(event.target)) setMoreOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && morePanel.classList.contains("open")) {
      setMoreOpen(false);
      moreButton.focus();
    }
  });
}
