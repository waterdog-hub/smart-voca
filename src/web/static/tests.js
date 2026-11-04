// 2026-11-04 - smart-voca - 시험 시작 화면의 입력 검사와 시작 요청 (화면 설계 §4.4)
// 파일 위치: src/web/static/tests.js

"use strict";

const startForm = document.getElementById("test-start-form");
const countInput = startForm.elements.count;
const formatSelect = startForm.elements.test_format;
const startButton = document.getElementById("test-start");
const REPLACE_CONFIRM = "진행 중인 시험을 그만두고 새로 시작할까요?";

function findCountProblem() {
  const text = countInput.value.trim();
  const valid = /^-?\d+$/.test(text)
    && Number(text) >= Number(countInput.min)
    && Number(text) <= Number(countInput.max);
  return valid ? null : `${countInput.min} 이상 ${countInput.max} 이하로 입력해 주세요.`;
}

function findWordShortage() {
  const wordCount = Number(startForm.dataset.wordCount);
  const multipleMinimum = Number(startForm.dataset.multipleMinimum);
  if (wordCount === 0) return "시험을 볼 단어가 없습니다. 먼저 단어장에 단어를 추가하세요.";
  if (formatSelect.value === "multiple" && wordCount < multipleMinimum) {
    return `객관식은 단어가 ${multipleMinimum}개 이상 필요합니다. 주관식을 고르거나 단어를 추가하세요.`;
  }
  return null;
}

// 시작할 수 없으면 버튼을 끄고 이유를 보여 준다 (화면 설계 §6)
function renderAvailability() {
  const shortage = findWordShortage();
  const notice = document.getElementById("test-not-possible");
  notice.textContent = shortage ?? "";
  notice.hidden = shortage === null;
  startButton.disabled = shortage !== null;
}

async function submitStart() {
  if (!isVerified()) return { ok: false, error: { message: NOT_VERIFIED_MESSAGE } };
  const problem = findCountProblem();
  if (problem) {
    return { ok: false, error: { message: "입력값을 확인해 주세요.", fields: { count: problem } } };
  }
  if (startForm.dataset.hasOpen === "true" && !window.confirm(REPLACE_CONFIRM)) return { ok: true };
  const result = await writeJson("/api/v1/tests", "POST", {
    test_format: formatSelect.value,
    test_direction: startForm.elements.test_direction.value,
    count: Number(countInput.value),
  });
  if (result === null) return { ok: true };
  if (result.ok) window.location.assign(`/tests/${result.data.id}`);
  return result;
}

function startTestStartPage() {
  if (!isVerified()) startButton.setAttribute("aria-disabled", "true");
  setupForm(startForm, submitStart);
  // setupForm은 응답 뒤 버튼을 다시 켠다. 단어가 부족하면 계속 꺼 둔다
  startForm.addEventListener("submit", () => queueMicrotask(renderAvailability));
  formatSelect.addEventListener("change", renderAvailability);
  renderAvailability();
}

startTestStartPage();
