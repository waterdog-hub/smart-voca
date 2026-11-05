// 2026-11-05 - smart-voca - 내 단어 화면의 검색, 정렬, 페이지. 쓰기는 단어장 화면으로 옮겼다 (결정 D-WB04)
// 파일 위치: src/web/static/words.js
// 단어 값은 항상 textContent로 넣는다. 글자가 HTML로 실행되지 않는다

"use strict";

const WORDS_API = "/api/v1/words";
const PAGE_SIZE = 50;
const SEARCH_DELAY_MS = 300;

const wordState = {
  keyword: "",
  sort: "word",
  order: "asc",
  offset: 0,
  total: 0,
  items: [],
  requestNumber: 0,
};

function byId(id) {
  return document.getElementById(id);
}

function formatDate(isoText) {
  // 서버는 UTC로 보내고 화면은 한국 시간으로 보여 준다 (API 설계 §1)
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" }).format(new Date(isoText));
}

async function loadWords() {
  // 응답이 늦게 온 이전 검색 결과가 새 결과를 덮어쓰지 않게 한다
  const requestNumber = ++wordState.requestNumber;
  const query = new URLSearchParams({
    q: wordState.keyword,
    sort: wordState.sort,
    order: wordState.order,
    limit: PAGE_SIZE,
    offset: wordState.offset,
  });
  byId("word-table-area").setAttribute("aria-busy", "true");
  const result = await requestJson(`${WORDS_API}?${query}`, { method: "GET" });
  if (requestNumber !== wordState.requestNumber) return;
  byId("word-table-area").setAttribute("aria-busy", "false");
  if (result.status === 401) {
    goToLogin();
    return;
  }
  if (!result.ok) {
    showMessage(describeError(result.error), "error");
    return;
  }
  wordState.items = result.data.items;
  wordState.total = result.data.total;
  renderWords();
}

function makeCell(label, text) {
  const cell = document.createElement("td");
  cell.dataset.label = label;
  cell.textContent = text;
  return cell;
}

function makeWordRow(item) {
  const row = document.createElement("tr");
  row.append(
    makeCell("단어", item.word),
    makeCell("뜻", item.meaning),
    makeCell("등록일", formatDate(item.created_at)),
  );
  return row;
}

function renderSortHeaders() {
  document.querySelectorAll("th[data-sort]").forEach((header) => {
    const isCurrent = header.dataset.sort === wordState.sort;
    if (isCurrent) header.setAttribute("aria-sort", wordState.order === "asc" ? "ascending" : "descending");
    else header.removeAttribute("aria-sort");
  });
}

function renderWords() {
  byId("word-rows").replaceChildren(...wordState.items.map(makeWordRow));
  const hasWords = wordState.total > 0;
  byId("word-table-area").hidden = !hasWords;
  byId("word-empty").hidden = hasWords;
  byId("word-empty-text").textContent = wordState.keyword
    ? "검색 결과가 없습니다."
    : "담은 단어가 없습니다. 단어장을 골라 담으세요.";
  // 검색 결과가 없을 때가 아니라 정말 단어가 없을 때만 단어장으로 안내한다
  byId("word-empty-link").hidden = hasWords || Boolean(wordState.keyword);
  byId("word-total").textContent = `총 ${wordState.total.toLocaleString("ko-KR")}개`;

  const firstNumber = hasWords ? wordState.offset + 1 : 0;
  const lastNumber = wordState.offset + wordState.items.length;
  byId("page-info").textContent = hasWords
    ? `${firstNumber.toLocaleString("ko-KR")}~${lastNumber.toLocaleString("ko-KR")}`
    : "";
  byId("page-prev").disabled = wordState.offset === 0;
  byId("page-next").disabled = lastNumber >= wordState.total;
  renderSortHeaders();
}

function setupListControls() {
  let searchTimer = null;
  byId("word-search").addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      wordState.keyword = event.target.value;
      wordState.offset = 0;
      loadWords();
    }, SEARCH_DELAY_MS);
  });
  document.querySelectorAll("th[data-sort] .sort-button").forEach((button) => {
    button.addEventListener("click", () => {
      const sort = button.closest("th").dataset.sort;
      wordState.order = wordState.sort === sort && wordState.order === "asc" ? "desc" : "asc";
      wordState.sort = sort;
      wordState.offset = 0;
      loadWords();
    });
  });
  byId("page-prev").addEventListener("click", () => {
    wordState.offset = Math.max(0, wordState.offset - PAGE_SIZE);
    loadWords();
  });
  byId("page-next").addEventListener("click", () => {
    wordState.offset += PAGE_SIZE;
    loadWords();
  });
}

setupListControls();
loadWords();
