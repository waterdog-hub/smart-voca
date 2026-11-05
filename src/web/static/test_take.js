// 2026-11-04 - smart-voca - 시험 진행과 결과 화면 (화면 설계 §4.4)
// 파일 위치: src/web/static/test_take.js
// 문제와 답은 항상 textContent로 넣는다. 사용자가 입력한 글자가 HTML로 실행되지 않는다

"use strict";

const attemptId = document.getElementById("test-app").dataset.attemptId;
const TEST_URL = `/api/v1/tests/${attemptId}`;
const DRAFT_KEY = `smart-voca-test-${attemptId}`;
const PROMPTS = {
  en_ko: "다음 영어 단어의 뜻은?",
  ko_en: "다음 뜻에 해당하는 영어 단어는?",
};

const testState = { items: [], index: 0, answers: {}, submitting: false, results: [] };

function byTestId(id) {
  return document.getElementById(id);
}

// 저장소를 쓸 수 없는 환경에서도 시험은 볼 수 있어야 한다. 그때는 새로고침하면 답만 사라진다
function loadDraft() {
  try {
    return JSON.parse(window.sessionStorage.getItem(DRAFT_KEY)) ?? {};
  } catch {
    return {};
  }
}

function saveDraft() {
  try {
    window.sessionStorage.setItem(
      DRAFT_KEY, JSON.stringify({ index: testState.index, answers: testState.answers })
    );
  } catch {
    // 위와 같은 이유로 무시한다
  }
}

function clearDraft() {
  try {
    window.sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    // 위와 같은 이유로 무시한다
  }
}

function currentItem() {
  return testState.items[testState.index];
}

function isAnswered(item) {
  const answer = testState.answers[item.id];
  return answer !== undefined && String(answer).trim() !== "";
}

function renderChoices(item) {
  const list = byTestId("choice-list");
  list.querySelectorAll("label").forEach((label) => label.remove());
  item.choices.forEach((choice, index) => {
    const label = document.createElement("label");
    label.className = "choice";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "choice";
    input.value = String(index);
    input.checked = testState.answers[item.id] === index;
    input.addEventListener("change", () => selectChoice(index));
    const text = document.createElement("span");
    text.textContent = `${index + 1}) ${choice}`;
    label.append(input, text);
    list.append(label);
  });
}

function renderQuestion() {
  const item = currentItem();
  const total = testState.items.length;
  const answered = testState.items.filter(isAnswered).length;
  byTestId("question-progress-text").textContent = `시험 ${item.position}/${total}, 답한 문항 ${answered}개`;
  byTestId("question-progress").max = total;
  byTestId("question-progress").value = item.position;
  byTestId("question-prompt").textContent = PROMPTS[item.direction];
  byTestId("question-text").textContent = item.question;

  const isChoice = item.choices.length > 0;
  byTestId("choice-list").hidden = !isChoice;
  byTestId("text-answer").hidden = isChoice;
  byTestId("test-key-help").hidden = !isChoice;
  if (isChoice) {
    renderChoices(item);
  } else {
    const input = byTestId("text-answer-input");
    input.value = testState.answers[item.id] ?? "";
    input.focus({ preventScroll: true });
  }
  byTestId("prev-question").disabled = testState.index === 0;
  byTestId("next-question").textContent = testState.index === total - 1 ? "제출" : "다음";
}

function selectChoice(index) {
  testState.answers[currentItem().id] = index;
  saveDraft();
  // 다음 문항으로 넘어가지 않는다. 잘못 고른 답을 고칠 수 있어야 한다
  const radios = byTestId("choice-list").querySelectorAll("input");
  radios.forEach((radio, radioIndex) => {
    radio.checked = radioIndex === index;
  });
  const answered = testState.items.filter(isAnswered).length;
  byTestId("question-progress-text").textContent =
    `시험 ${currentItem().position}/${testState.items.length}, 답한 문항 ${answered}개`;
}

function keepTextAnswer() {
  const item = currentItem();
  if (item.choices.length === 0) {
    testState.answers[item.id] = byTestId("text-answer-input").value;
    saveDraft();
  }
}

function moveTo(index) {
  testState.index = index;
  saveDraft();
  renderQuestion();
}

function renderResult(result) {
  byTestId("question-area").hidden = true;
  byTestId("result-score").textContent =
    `${result.total}문항 중 ${result.score}개를 맞혔습니다 (${result.percent}%).`;
  testState.results = result.items;
  renderResultRows(false);
  byTestId("wrong-only").hidden = result.score === result.total;
  byTestId("test-result").hidden = false;
}

function renderResultRows(wrongOnly) {
  const rows = byTestId("result-rows");
  rows.replaceChildren();
  for (const entry of testState.results) {
    if (wrongOnly && entry.correct) continue;
    const row = document.createElement("tr");
    const columns = [
      ["번호", entry.position],
      ["문제", entry.question],
      ["내 답", entry.your_answer ?? "(답 없음)"],
      ["정답", entry.correct_answer],
      // 색만으로 구분하지 않도록 글자로 적는다 (화면 설계 §7)
      ["결과", entry.correct ? "정답" : "오답"],
    ];
    for (const [label, text] of columns) {
      const cell = document.createElement("td");
      cell.dataset.label = label;
      cell.textContent = text;
      row.append(cell);
    }
    rows.append(row);
  }
}

function buildAnswerList() {
  return testState.items
    .filter(isAnswered)
    .map((item) => ({ item_id: item.id, answer: testState.answers[item.id] }));
}

async function submitTest() {
  if (testState.submitting) return;
  if (!requireVerified()) return;
  const unanswered = testState.items.filter((item) => !isAnswered(item)).length;
  const question = unanswered > 0
    ? `아직 답하지 않은 문항이 ${unanswered}개 있습니다. 제출할까요?`
    : "시험을 제출할까요?";
  if (!window.confirm(question)) return;

  testState.submitting = true;
  byTestId("next-question").disabled = true;
  const result = await writeJson(`${TEST_URL}/submit`, "POST", { answers: buildAnswerList() });
  if (result === null) return;
  testState.submitting = false;
  byTestId("next-question").disabled = false;
  if (result.status === 409) {
    // 다른 탭에서 제출했거나 시간이 지났다. 서버가 상태에 맞는 화면을 그린다
    clearDraft();
    window.location.reload();
    return;
  }
  if (!result.ok) {
    showMessage(describeError(result.error), "error");
    return;
  }
  clearDraft();
  renderResult(result.data);
}

function handleTestKey(event) {
  if (event.repeat || event.ctrlKey || event.altKey || event.metaKey) return;
  if (byTestId("question-area").hidden) return;
  // 주관식 입력칸의 숫자는 글자다 (D-UI02)
  if (event.target.closest('input[type="text"]')) return;
  // 숫자키로 고르면 포커스가 폼 밖에 있어 Enter가 폼에 닿지 않는다 (D-17). 버튼과 링크는 자기 동작을 둔다
  if (event.key === "Enter") {
    if (event.target.closest("button, a, input")) return;
    event.preventDefault();
    byTestId("question-form").requestSubmit();
    return;
  }
  const number = Number(event.key);
  const item = currentItem();
  if (!Number.isInteger(number) || number < 1 || number > item.choices.length) return;
  event.preventDefault();
  selectChoice(number - 1);
}

async function startTestPage() {
  const result = await requestJson(TEST_URL, { method: "GET" });
  if (result.status === 401) {
    goToLogin();
    return;
  }
  if (result.status === 409) {
    window.location.reload();
    return;
  }
  if (!result.ok) {
    showMessage(describeError(result.error), "error");
    return;
  }
  testState.items = result.data.items;
  const draft = loadDraft();
  testState.answers = draft.answers ?? {};
  const savedIndex = Number(draft.index);
  testState.index = savedIndex >= 0 && savedIndex < testState.items.length ? savedIndex : 0;

  byTestId("question-form").addEventListener("submit", (event) => {
    event.preventDefault();
    keepTextAnswer();
    if (testState.index === testState.items.length - 1) submitTest();
    else moveTo(testState.index + 1);
  });
  byTestId("prev-question").addEventListener("click", () => {
    keepTextAnswer();
    moveTo(testState.index - 1);
  });
  byTestId("text-answer-input").addEventListener("input", keepTextAnswer);
  byTestId("wrong-only").addEventListener("click", (event) => {
    const pressed = event.currentTarget.getAttribute("aria-pressed") !== "true";
    event.currentTarget.setAttribute("aria-pressed", String(pressed));
    event.currentTarget.textContent = pressed ? "전체 문항 보기" : "틀린 문항만 보기";
    renderResultRows(pressed);
  });
  document.addEventListener("keydown", handleTestKey);

  byTestId("question-area").hidden = false;
  renderQuestion();
}

startTestPage();
