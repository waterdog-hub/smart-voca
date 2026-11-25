// 2026-11-05 - smart-voca - 내 단어 화면의 검색, 정렬, 페이지, 직접 등록·수정·삭제, CSV 가져오기 (VOCA-FR-001~004)
// 파일 위치: src/web/static/words.js
// 단어 값은 항상 textContent로 넣는다. 글자가 HTML로 실행되지 않는다

"use strict";

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
  const result = await readJson(fetch(`/api/v1/words?${query}`, jsonRequest("GET")));
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

function makeButton(text, className, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = text;
  // 비활성처럼 보이되 눌렀을 때 인증 안내를 띄운다 (화면 설계 §4.1)
  if (!isVerified()) button.setAttribute("aria-disabled", "true");
  button.addEventListener("click", onClick);
  return button;
}

function makeWordRow(item) {
  const row = document.createElement("tr");
  const actions = document.createElement("td");
  actions.dataset.label = "관리";
  const box = document.createElement("div");
  box.className = "word-actions";
  box.append(
    makeButton("수정", "secondary", () => startEdit(row, item)),
    makeButton("삭제", "secondary", () => deleteWord(item)),
  );
  actions.append(box);
  row.append(
    makeCell("단어", item.word),
    makeCell("뜻", item.meaning),
    makeCell("등록일", formatDate(item.created_at)),
    actions,
  );
  return row;
}

function makeInputCell(label, value, maxLength) {
  const cell = document.createElement("td");
  cell.dataset.label = label;
  const input = document.createElement("input");
  input.type = "text";
  input.value = value;
  input.maxLength = maxLength;
  input.setAttribute("aria-label", label);
  cell.append(input);
  return [cell, input];
}

// 행을 입력칸으로 바꿔 그 자리에서 고친다
function startEdit(row, item) {
  if (!requireVerified()) return;
  const [wordCell, wordInput] = makeInputCell("단어", item.word, 100);
  const [meaningCell, meaningInput] = makeInputCell("뜻", item.meaning, 500);
  const actions = document.createElement("td");
  actions.dataset.label = "관리";
  const box = document.createElement("div");
  box.className = "word-actions";
  const save = makeButton("저장", "", async () => {
    save.disabled = true;
    const result = await withCsrf((token) => fetch(`/api/v1/words/${item.id}`, jsonRequest("PUT", {
      word: wordInput.value,
      meaning: meaningInput.value,
    }, token)));
    if (result === null) return;
    save.disabled = false;
    if (!result.ok) {
      const fields = Object.values(result.error.fields ?? {});
      showMessage(fields.length ? fields.join(" ") : describeError(result.error), "error");
      return;
    }
    showMessage(`'${result.data.word}'을(를) 고쳤습니다.`, "ok");
    loadWords();
  });
  box.append(save, makeButton("취소", "secondary", () => row.replaceWith(makeWordRow(item))));
  actions.append(box);
  row.replaceChildren(wordCell, meaningCell, makeCell("등록일", formatDate(item.created_at)), actions);
  wordInput.focus();
}

async function deleteWord(item) {
  if (!requireVerified()) return;
  if (!window.confirm(`'${item.word}'을(를) 삭제할까요? 진도에서 빠지고 학습 기록은 남습니다.`)) return;
  const result = await withCsrf((token) => fetch(`/api/v1/words/${item.id}`, jsonRequest("DELETE", undefined, token)));
  if (result === null) return;
  // 204 응답은 본문이 없어 data가 null이다
  if (!result.ok) {
    showMessage(describeError(result.error), "error");
    return;
  }
  showMessage(`'${item.word}'을(를) 삭제했습니다.`, "ok");
  loadWords();
}

async function submitAddWord(form) {
  if (!requireVerified()) return { ok: true };
  const result = await withCsrf((token) => fetch("/api/v1/words", jsonRequest("POST", {
    word: form.elements.word.value,
    meaning: form.elements.meaning.value,
  }, token)));
  if (result === null) return { ok: true };
  if (!result.ok) return result;
  form.reset();
  form.elements.word.focus();
  showMessage(`'${result.data.word}'을(를) 등록했습니다.`, "ok");
  loadWords();
  return result;
}

function showImportProblems(problems) {
  const list = byId("import-problems");
  list.replaceChildren(...problems.map((text) => {
    const item = document.createElement("li");
    item.textContent = text;
    return item;
  }));
  list.hidden = problems.length === 0;
}

async function submitImport(form) {
  if (!requireVerified()) return { ok: true };
  const file = form.elements.file.files[0];
  if (!file) {
    return { ok: false, error: { message: "가져올 CSV 파일을 고르세요.", fields: { file: "파일을 고르세요." } } };
  }
  const formData = new FormData();
  formData.append("file", file);
  const result = await withCsrf((token) => fetch("/api/v1/words/import", formRequest(formData, token)));
  if (result === null) return { ok: true };
  if (!result.ok) return result;
  const data = result.data;
  const parts = [`새 단어 ${data.added.toLocaleString("ko-KR")}개를 등록했습니다.`];
  if (data.skipped_existing) parts.push(`이미 있던 단어 ${data.skipped_existing}개는 건너뜀.`);
  if (data.skipped_duplicate) parts.push(`파일 안 중복 ${data.skipped_duplicate}개는 건너뜀.`);
  if (data.invalid_count) parts.push(`형식 오류 ${data.invalid_count}줄은 건너뜀.`);
  showMessage(parts.join(" "), "ok");
  showImportProblems(data.problems);
  form.reset();
  loadWords();
  return result;
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
    : "단어가 없습니다. 위에서 직접 등록하거나 CSV를 가져오거나, 단어장을 골라 담으세요.";
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
setupForm(byId("word-add-form"), submitAddWord);
setupForm(byId("word-import-form"), submitImport);
loadWords();
