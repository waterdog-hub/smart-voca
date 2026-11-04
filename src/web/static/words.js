// 2026-11-04 - smart-voca - 단어장 화면의 검색, 정렬, 페이지, 추가, 수정, 삭제, 가져오기
// 파일 위치: src/web/static/words.js
// 단어 값은 항상 textContent로 넣는다. 사용자가 입력한 글자가 HTML로 실행되지 않는다

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
  selected: new Set(),
  editingId: null,
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
  // 마지막 페이지의 단어를 모두 지우면 빈 페이지가 되므로 앞 페이지로 돌아간다
  if (wordState.items.length === 0 && wordState.total > 0 && wordState.offset > 0) {
    wordState.offset = Math.max(0, wordState.offset - PAGE_SIZE);
    await loadWords();
    return;
  }
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

  const selectCell = document.createElement("td");
  selectCell.className = "select-col";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = wordState.selected.has(item.id);
  checkbox.setAttribute("aria-label", `${item.word} 선택`);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) wordState.selected.add(item.id);
    else wordState.selected.delete(item.id);
    renderSelection();
  });
  selectCell.append(checkbox);

  const editCell = document.createElement("td");
  editCell.className = "edit-col";
  const editButton = document.createElement("button");
  editButton.type = "button";
  editButton.className = "secondary needs-verified";
  editButton.textContent = "수정";
  editButton.setAttribute("aria-label", `${item.word} 수정`);
  if (!isVerified()) editButton.setAttribute("aria-disabled", "true");
  editButton.addEventListener("click", () => openEditPanel(item, editButton));
  editCell.append(editButton);

  row.append(
    selectCell,
    makeCell("단어", item.word),
    makeCell("뜻", item.meaning),
    makeCell("등록일", formatDate(item.created_at)),
    editCell,
  );
  return row;
}

function renderSelection() {
  const selectedOnPage = wordState.items.filter((item) => wordState.selected.has(item.id)).length;
  const selectAll = byId("select-all");
  selectAll.checked = wordState.items.length > 0 && selectedOnPage === wordState.items.length;
  selectAll.indeterminate = selectedOnPage > 0 && selectedOnPage < wordState.items.length;
  const deleteButton = byId("delete-selected");
  deleteButton.disabled = wordState.selected.size === 0;
  deleteButton.textContent =
    wordState.selected.size === 0 ? "선택 삭제" : `선택 삭제 (${wordState.selected.size})`;
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
  const isEmptyResult = !hasWords;
  byId("word-table-area").hidden = isEmptyResult;
  byId("word-empty").hidden = !isEmptyResult;
  byId("word-empty-text").textContent = wordState.keyword
    ? "검색 결과가 없습니다."
    : "단어를 추가하거나 CSV 파일을 가져오세요.";
  byId("word-total").textContent = `총 ${wordState.total.toLocaleString("ko-KR")}개`;

  const firstNumber = hasWords ? wordState.offset + 1 : 0;
  const lastNumber = wordState.offset + wordState.items.length;
  byId("page-info").textContent = hasWords
    ? `${firstNumber.toLocaleString("ko-KR")}~${lastNumber.toLocaleString("ko-KR")}`
    : "";
  byId("page-prev").disabled = wordState.offset === 0;
  byId("page-next").disabled = lastNumber >= wordState.total;
  renderSortHeaders();
  renderSelection();
}

function showWordFieldErrors(fields, prefix) {
  for (const [name, text] of Object.entries(fields ?? {})) {
    const element = byId(`${prefix}${name}-error`);
    if (!element) continue;
    element.textContent = text;
    element.hidden = false;
    const input = element.closest(".field").querySelector("input");
    input.setAttribute("aria-invalid", "true");
    input.setAttribute("aria-errormessage", element.id);
  }
}

function clearWordFieldErrors(form) {
  form.querySelectorAll("[aria-invalid]").forEach((input) => {
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-errormessage");
  });
  form.querySelectorAll(".field-error").forEach((element) => {
    element.textContent = "";
    element.hidden = true;
  });
}

function setupAddForm() {
  const form = byId("add-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!requireVerified()) return;
    clearWordFieldErrors(form);
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    const result = await writeJson(WORDS_API, "POST", {
      word: byId("add-word").value,
      meaning: byId("add-meaning").value,
    });
    button.disabled = false;
    if (result === null) return;
    if (!result.ok) {
      showWordFieldErrors(result.error.fields, "add-");
      showMessage(describeError(result.error), "error");
      return;
    }
    showMessage(`추가했습니다: ${result.data.word}`, "ok");
    form.reset();
    byId("add-word").focus();
    await loadWords();
  });
}

let editReturnFocus = null;

function openEditPanel(item, returnFocusTo) {
  if (!requireVerified()) return;
  wordState.editingId = item.id;
  editReturnFocus = returnFocusTo;
  clearWordFieldErrors(byId("edit-form"));
  byId("edit-word").value = item.word;
  byId("edit-meaning").value = item.meaning;
  byId("edit-panel").hidden = false;
  byId("edit-word").focus();
}

function closeEditPanel() {
  wordState.editingId = null;
  byId("edit-panel").hidden = true;
  // 목록이 다시 그려져 원래 버튼이 사라졌다면 포커스를 옮기지 않는다
  if (editReturnFocus?.isConnected) editReturnFocus.focus();
  editReturnFocus = null;
}

function setupEditPanel() {
  const form = byId("edit-form");
  byId("edit-cancel").addEventListener("click", closeEditPanel);
  byId("edit-panel").addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeEditPanel();
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearWordFieldErrors(form);
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    const result = await writeJson(`${WORDS_API}/${wordState.editingId}`, "PATCH", {
      word: byId("edit-word").value,
      meaning: byId("edit-meaning").value,
    });
    button.disabled = false;
    if (result === null) return;
    if (!result.ok) {
      showWordFieldErrors(result.error.fields, "");
      showMessage(describeError(result.error), "error");
      if (result.status === 404) {
        closeEditPanel();
        await loadWords();
      }
      return;
    }
    showMessage(`수정했습니다: ${result.data.word}`, "ok");
    closeEditPanel();
    await loadWords();
  });
}

function setupDelete() {
  byId("delete-selected").addEventListener("click", async () => {
    if (!requireVerified()) return;
    const count = wordState.selected.size;
    if (!window.confirm(`선택한 단어 ${count}개를 삭제할까요? 진도에서도 빠집니다.`)) return;
    const deleteButton = byId("delete-selected");
    // 응답 전에 다시 누르면 삭제 개수 안내가 틀어지므로 막는다 (화면 설계 §6)
    deleteButton.disabled = true;
    const result = await writeJson(`${WORDS_API}/delete`, "POST", { ids: [...wordState.selected] });
    if (result === null) return;
    deleteButton.disabled = false;
    if (!result.ok) {
      showMessage(describeError(result.error), "error");
      return;
    }
    wordState.selected.clear();
    showMessage(`${result.data.deleted}개를 삭제했습니다.`, "ok");
    await loadWords();
  });
}

function showImportResult(data) {
  byId("import-summary").textContent =
    `추가 ${data.added}개, 중복 건너뜀 ${data.skipped_duplicate}개, 형식 오류 건너뜀 ${data.skipped_invalid}개`;
  const rows = data.invalid_rows.map((invalid) => {
    const line = document.createElement("li");
    line.textContent = `${invalid.row}번째 줄: ${invalid.reason}`;
    return line;
  });
  byId("import-invalid-rows").replaceChildren(...rows);
  byId("import-result").hidden = false;
}

function setupImport() {
  const fileInput = byId("import-file");
  const button = byId("import-button");
  button.addEventListener("click", () => {
    if (requireVerified()) fileInput.click();
  });
  byId("import-result-close").addEventListener("click", () => {
    byId("import-result").hidden = true;
    button.focus();
  });
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;
    const body = new FormData();
    body.append("file", file);
    button.disabled = true;
    const result = await writeForm(`${WORDS_API}/import`, body);
    button.disabled = false;
    // 같은 파일을 고쳐 다시 골라도 change가 발생하도록 비운다
    fileInput.value = "";
    if (result === null) return;
    if (!result.ok) {
      showMessage(describeError(result.error), "error");
      return;
    }
    showMessage("가져오기를 마쳤습니다.", "ok");
    showImportResult(result.data);
    wordState.offset = 0;
    await loadWords();
  });
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
  byId("select-all").addEventListener("change", (event) => {
    wordState.items.forEach((item) => {
      if (event.target.checked) wordState.selected.add(item.id);
      else wordState.selected.delete(item.id);
    });
    renderWords();
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

function startWordsPage() {
  // 비활성처럼 보이되 눌렀을 때 인증 안내를 띄우도록 disabled 대신 aria-disabled를 쓴다 (화면 설계 §4.1)
  if (!isVerified()) {
    document.querySelectorAll(".needs-verified").forEach((button) => {
      button.setAttribute("aria-disabled", "true");
    });
  }
  setupListControls();
  setupAddForm();
  setupEditPanel();
  setupDelete();
  setupImport();
  loadWords();
}

startWordsPage();
