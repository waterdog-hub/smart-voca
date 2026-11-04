// 2026-11-04 - smart-voca - 설정 화면의 불러오기, 즉시 검사, 저장, 되돌리기 (화면 설계 §4.5)
// 파일 위치: src/web/static/settings.js
// 최소값과 최대값은 서버가 입력칸 속성으로 넘긴다. 규칙을 여기에 다시 적지 않는다

"use strict";

const SETTINGS_API = "/api/v1/settings";
const SETTINGS_SAVED_MESSAGE = "설정을 저장했습니다. 하루 분량은 다음 일차 진도부터 적용됩니다.";
const SETTINGS_INVALID_MESSAGE = "입력값을 확인해 주세요.";

const settingsForm = document.getElementById("settings-form");
const countInputs = [...settingsForm.querySelectorAll('input[type="number"]')];
const choiceInputs = [...settingsForm.querySelectorAll("select")];
let savedSettings = null;

function findCountProblem(input) {
  const text = input.value.trim();
  const inRange = /^-?\d+$/.test(text)
    && Number(text) >= Number(input.min)
    && Number(text) <= Number(input.max);
  return inRange ? null : `${input.min} 이상 ${input.max} 이하로 입력해 주세요.`;
}

function findAllCountProblems() {
  const problems = {};
  for (const input of countInputs) {
    const problem = findCountProblem(input);
    if (problem) problems[input.name] = problem;
  }
  return problems;
}

function clearCountError(input) {
  document.getElementById(`${input.name}-error`).hidden = true;
  input.removeAttribute("aria-invalid");
  input.removeAttribute("aria-errormessage");
}

// 저장을 누르기 전에 칸 아래에 바로 안내한다 (화면 설계 §4.5)
function checkCountInput(input) {
  clearCountError(input);
  const problem = findCountProblem(input);
  if (problem) showFieldErrors(settingsForm, { [input.name]: problem });
}

function fillSettings(values) {
  for (const input of [...countInputs, ...choiceInputs]) {
    input.value = values[input.name];
  }
}

function readSettings() {
  const values = {};
  for (const input of countInputs) values[input.name] = Number(input.value);
  for (const input of choiceInputs) values[input.name] = input.value;
  return values;
}

async function submitSettings() {
  if (!isVerified()) return { ok: false, error: { message: NOT_VERIFIED_MESSAGE } };
  const problems = findAllCountProblems();
  if (Object.keys(problems).length > 0) {
    return { ok: false, error: { message: SETTINGS_INVALID_MESSAGE, fields: problems } };
  }
  const result = await writeJson(SETTINGS_API, "PUT", readSettings());
  // 세션이 끝나 로그인 화면으로 이동하는 중이다
  if (result === null) return { ok: true };
  if (result.ok) {
    savedSettings = result.data;
    fillSettings(savedSettings);
    showMessage(SETTINGS_SAVED_MESSAGE, "ok");
  }
  return result;
}

function revertSettings() {
  fillSettings(savedSettings);
  clearFieldErrors(settingsForm);
  document.getElementById("message").hidden = true;
}

async function startSettingsPage() {
  const saveButton = document.getElementById("settings-save");
  const revertButton = document.getElementById("settings-revert");
  // 비활성처럼 보이되 눌렀을 때 인증 안내를 띄운다 (화면 설계 §4.1)
  if (!isVerified()) saveButton.setAttribute("aria-disabled", "true");

  const result = await requestJson(SETTINGS_API, { method: "GET" });
  if (result.status === 401) {
    window.location.assign("/login");
    return;
  }
  if (!result.ok) {
    showMessage(describeError(result.error), "error");
    return;
  }
  savedSettings = result.data;
  fillSettings(savedSettings);

  countInputs.forEach((input) => {
    input.addEventListener("input", () => checkCountInput(input));
  });
  revertButton.addEventListener("click", revertSettings);
  setupForm(settingsForm, submitSettings);
  // 값을 받기 전에 저장하면 빈 칸을 보내게 되므로 불러온 뒤에 버튼을 켠다
  saveButton.disabled = false;
  revertButton.disabled = false;
}

startSettingsPage();
