// 2026-11-04 - smart-voca - 홈과 암기 화면의 "다음 일차 만들기" 버튼
// 파일 위치: src/web/static/plans.js

"use strict";

function setupCreatePlanButtons() {
  document.querySelectorAll("[data-create-plan]").forEach((button) => {
    // 비활성처럼 보이되 눌렀을 때 인증 안내를 띄운다 (화면 설계 §4.1)
    if (!isVerified()) button.setAttribute("aria-disabled", "true");
    button.addEventListener("click", async () => {
      if (!requireVerified()) return;
      button.disabled = true;
      const result = await writeJson("/api/v1/plans", "POST");
      if (result === null) return;
      if (result.ok) {
        window.location.assign("/memorize");
        return;
      }
      button.disabled = false;
      showMessage(describeError(result.error), "error");
    });
  });
}

setupCreatePlanButtons();
