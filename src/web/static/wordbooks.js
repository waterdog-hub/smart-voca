// 2026-11-05 - smart-voca - 단어장 화면의 목록, 담기, 제외 (결정 D-WB08)
// 파일 위치: src/web/static/wordbooks.js
// 단어장 정보는 항상 textContent로 넣는다. 값이 HTML로 실행되지 않는다

"use strict";

const WORDBOOKS_API = "/api/v1/wordbooks";

function byId(id) {
  return document.getElementById(id);
}

function makeParagraph(className, text) {
  const paragraph = document.createElement("p");
  paragraph.className = className;
  paragraph.textContent = text;
  return paragraph;
}

function makeWordbookCard(book) {
  const card = document.createElement("li");
  card.className = "wordbook-card";
  card.dataset.wordbookId = String(book.id);
  card.dataset.added = String(book.added);

  const title = document.createElement("h2");
  title.textContent = book.title;
  if (book.added) {
    const badge = document.createElement("span");
    badge.className = "wordbook-badge";
    badge.textContent = "담음";
    title.append(" ", badge);
  }

  const sample = book.sample_words.length ? ` · 예: ${book.sample_words.join(", ")}` : "";
  const meta = makeParagraph("help", `단어 ${book.word_count.toLocaleString("ko-KR")}개${sample}`);
  const source = makeParagraph("help", `출처: ${book.source_note}`);

  const button = document.createElement("button");
  button.type = "button";
  button.className = book.added ? "secondary needs-verified" : "needs-verified";
  button.textContent = book.added ? "제외" : "담기";
  button.setAttribute("aria-label", `${book.title} ${button.textContent}`);
  // 비활성처럼 보이되 눌렀을 때 인증 안내를 띄우도록 disabled 대신 aria-disabled를 쓴다 (화면 설계 §4.1)
  if (!isVerified()) button.setAttribute("aria-disabled", "true");
  button.addEventListener("click", () => (book.added ? removeWordbook(book, button) : addWordbook(book, button)));

  card.append(title, makeParagraph("", book.description), meta, source, button);
  return card;
}

async function loadWordbooks() {
  byId("wordbook-list").setAttribute("aria-busy", "true");
  const result = await requestJson(WORDBOOKS_API, { method: "GET" });
  byId("wordbook-list").setAttribute("aria-busy", "false");
  if (result.status === 401) {
    goToLogin();
    return;
  }
  if (!result.ok) {
    showMessage(describeError(result.error), "error");
    return;
  }
  const books = result.data.items;
  byId("wordbook-list").replaceChildren(...books.map(makeWordbookCard));
  byId("wordbook-empty").hidden = books.length > 0;
  const addedCount = books.filter((book) => book.added).length;
  byId("wordbook-summary").textContent = books.length ? `담은 단어장 ${addedCount}개 / 전체 ${books.length}개` : "";
}

async function addWordbook(book, button) {
  if (!requireVerified()) return;
  button.disabled = true;
  const result = await writeJson(`${WORDBOOKS_API}/${book.id}/add`, "POST");
  if (result === null) return;
  if (!result.ok) {
    button.disabled = false;
    showMessage(describeError(result.error), "error");
    return;
  }
  const { added, already_had: alreadyHad } = result.data;
  const extra = alreadyHad ? `, 이미 있던 단어 ${alreadyHad}개는 건너뜀` : "";
  showMessage(`'${book.title}' 단어장을 담았습니다. 새 단어 ${added}개${extra}.`, "ok");
  await loadWordbooks();
}

async function removeWordbook(book, button) {
  if (!requireVerified()) return;
  const question =
    `'${book.title}' 단어장을 제외할까요?\n` +
    "다른 담은 단어장에 없는 단어는 학습과 진도에서 빠집니다. 학습 기록은 남고, 다시 담으면 이어집니다.";
  if (!window.confirm(question)) return;
  button.disabled = true;
  const result = await writeJson(`${WORDBOOKS_API}/${book.id}/remove`, "POST");
  if (result === null) return;
  if (!result.ok) {
    button.disabled = false;
    showMessage(describeError(result.error), "error");
    return;
  }
  const { removed, kept } = result.data;
  const extra = kept ? `, 다른 단어장에도 있어 남긴 단어 ${kept}개` : "";
  showMessage(`'${book.title}' 단어장을 제외했습니다. 학습에서 빠진 단어 ${removed}개${extra}.`, "ok");
  await loadWordbooks();
}

loadWordbooks();
