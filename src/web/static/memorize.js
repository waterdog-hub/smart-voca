// 2026-11-04 - smart-voca - 암기 화면의 카드 진행, 단축키, 지난 일차 복습 (화면 설계 §4.2)
// 파일 위치: src/web/static/memorize.js
// 단어 값은 항상 textContent로 넣는다. 사용자가 입력한 글자가 HTML로 실행되지 않는다

"use strict";

const memorizeApp = document.getElementById("memorize-app");
const KEY_ACTIONS = {
  ArrowUp: revealMeaning,
  " ": revealMeaning,
  ArrowRight: rememberCard,
  1: rememberCard,
  ArrowLeft: repeatCardLater,
  2: repeatCardLater,
};

const cardState = {
  // 현재 일차는 서버에 저장하고, 지난 일차는 화면에서만 진행한다 (D-16)
  isCurrent: false,
  queue: [],
  total: 0,
  doneCount: 0,
  againCount: 0,
  revealed: false,
  busy: false,
};

function element(id) {
  return document.getElementById(id);
}

function renderProgress() {
  element("memorize-progress").max = Math.max(cardState.total, 1);
  element("memorize-progress").value = cardState.doneCount;
  element("memorize-progress-text").textContent =
    `${cardState.total}개 중 ${cardState.doneCount}개 완료, 남은 단어 ${cardState.queue.length}개`;
}

function renderSummary() {
  element("memorize-card").hidden = true;
  element("card-actions").hidden = true;
  element("key-help").hidden = true;
  element("summary-text").textContent = cardState.total === 0
    ? "이 일차에 남은 단어가 없습니다."
    : `외운 단어 ${cardState.doneCount}개, 이번에 다시 본 횟수 ${cardState.againCount}회입니다.`;
  element("memorize-summary").hidden = false;
}

function renderCard() {
  renderProgress();
  const card = cardState.queue[0];
  if (!card) {
    renderSummary();
    return;
  }
  element("card-word").textContent = card.word;
  element("card-meaning").textContent = card.meaning;
  element("card-meaning").hidden = !cardState.revealed;
  element("show-meaning").hidden = cardState.revealed;
  element("card-actions").hidden = !cardState.revealed;
  element("memorize-card").hidden = false;
  element("key-help").hidden = false;
}

function focusCard() {
  // 뜻 보기 버튼이 사라지면 포커스를 잃는다. 카드로 옮겨 키 입력과 화면 낭독이 이어지게 한다
  element("memorize-card").focus({ preventScroll: true });
}

function revealMeaning() {
  if (cardState.revealed || !cardState.queue.length) return;
  cardState.revealed = true;
  renderCard();
  focusCard();
}

async function saveCard(card, body) {
  if (!cardState.isCurrent) return true;
  if (!requireVerified()) return false;
  const result = await writeJson(`/api/v1/plan-items/${card.id}`, "PATCH", body);
  if (result === null) return false;
  if (result.status === 404 || result.status === 409) {
    // 다른 탭에서 단어를 지웠거나 다음 일차로 넘어갔다. 최신 상태로 다시 그린다
    window.location.reload();
    return false;
  }
  if (!result.ok) showMessage(describeError(result.error), "error");
  return result.ok;
}

async function finishCard(body, applyToQueue) {
  if (!cardState.revealed || cardState.busy || !cardState.queue.length) return;
  cardState.busy = true;
  document.getElementById("message").hidden = true;
  element("again-button").disabled = true;
  element("remember-button").disabled = true;
  try {
    if (await saveCard(cardState.queue[0], body)) {
      applyToQueue();
      cardState.revealed = false;
      renderCard();
      focusCard();
    }
  } finally {
    cardState.busy = false;
    element("again-button").disabled = false;
    element("remember-button").disabled = false;
  }
}

function rememberCard() {
  return finishCard({ done: true }, () => {
    cardState.queue.shift();
    cardState.doneCount += 1;
  });
}

function repeatCardLater() {
  return finishCard({ later: true }, () => {
    cardState.queue.push(cardState.queue.shift());
    cardState.againCount += 1;
  });
}

function handleCardKey(event) {
  if (event.repeat || event.ctrlKey || event.altKey || event.metaKey) return;
  // 입력칸과 일차 선택에서는 키의 원래 동작을 둔다 (D-UI02)
  if (event.target.closest("input, select, textarea")) return;
  // 버튼과 링크에 포커스가 있으면 Space는 그것을 누르는 키다. 한 번에 두 번 처리되지 않게 한다 (D-UI09)
  if (event.key === " " && event.target.closest("button, a")) return;
  const action = KEY_ACTIONS[event.key];
  if (!action) return;
  event.preventDefault();
  action();
}

async function startMemorizePage() {
  element("day-select").addEventListener("change", () => element("day-form").submit());
  if (!memorizeApp) return;
  cardState.isCurrent = memorizeApp.dataset.isCurrent === "true";

  element("show-meaning").addEventListener("click", revealMeaning);
  element("remember-button").addEventListener("click", rememberCard);
  element("again-button").addEventListener("click", repeatCardLater);
  document.addEventListener("keydown", handleCardKey);

  const result = await requestJson(`/api/v1/plans/${memorizeApp.dataset.day}`, { method: "GET" });
  if (result.status === 401) {
    goToLogin();
    return;
  }
  if (result.status === 404) {
    // 단어를 모두 지워 이 일차가 비었다 (D-18)
    cardState.total = 0;
    renderCard();
    return;
  }
  if (!result.ok) {
    showMessage(describeError(result.error), "error");
    return;
  }
  const items = result.data.items;
  // 첫 번째 미완료 카드가 곧 마지막으로 보던 카드다. 외움과 다시가 이미 서버에 저장되어 있다 (D-10)
  cardState.queue = cardState.isCurrent ? items.filter((item) => !item.done) : items;
  cardState.total = items.length;
  cardState.doneCount = items.length - (cardState.isCurrent ? cardState.queue.length : items.length);
  renderCard();
}

if (element("day-select")) startMemorizePage();
