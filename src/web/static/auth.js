// 2026-11-04 - smart-voca - 가입, 로그인, 인증, 비밀번호 재설정, 로그아웃 화면의 동작
// 파일 위치: src/web/static/auth.js

"use strict";

const NETWORK_ERROR = { code: "NETWORK", message: "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요." };
const UNKNOWN_ERROR = { code: "UNKNOWN", message: "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요." };
const NOT_VERIFIED_MESSAGE = "이메일 인증이 필요합니다. 메일의 링크를 먼저 눌러 주세요.";

// 학교 서버는 앱을 /2026/voca-<학번>/ 아래로 옮기면서 fetch("/…")와 location.href = "/…" 형태의 주소만 바꿔 준다.
// 그래서 주소는 항상 호출하는 자리에 문자열로 쓴다. 이 파일의 함수는 주소를 받지 않고 요청 옵션만 만든다 (Dockerfile 구성 R-04)
function jsonRequest(method, body, csrfToken) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  return {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

function formRequest(formData, csrfToken) {
  // 파일 업로드는 브라우저가 Content-Type과 경계 값을 직접 정한다
  return { method: "POST", headers: { "X-CSRF-Token": csrfToken }, credentials: "same-origin", body: formData };
}

// fetch(...)가 돌려준 약속을 받아 결과를 한 모양으로 정리한다
async function readJson(responsePromise) {
  let response;
  try {
    response = await responsePromise;
  } catch {
    return { ok: false, status: 0, error: NETWORK_ERROR };
  }
  // 프록시 오류처럼 본문이 JSON이 아닌 응답도 화면이 멈추지 않게 처리한다
  const data = await response.json().catch(() => null);
  return { ok: response.ok, status: response.status, data, error: data?.error ?? UNKNOWN_ERROR };
}

// 서버가 옮겨 준 앱의 시작 주소. base.html의 <link rel="home" href="/">를 서버가 바꿔 주므로 그 값을 읽는다
function appRoot() {
  const home = document.querySelector('link[rel="home"]');
  const root = new URL(home ? home.href : "/", window.location.href).pathname;
  return root.endsWith("/") ? root : `${root}/`;
}

// 브라우저 주소에서 앱 시작 주소를 뺀 앱 안의 경로 (예: /2026/voca-1/tests → /tests)
function appPath() {
  const root = appRoot();
  const path = window.location.pathname;
  return path.startsWith(root) ? `/${path.slice(root.length)}` : path;
}

// 세션이 끝나면 로그인 뒤 지금 화면으로 돌아오게 한다 (화면 설계 §5.3)
function goToLogin() {
  const next = new URLSearchParams({ next: appPath() + window.location.search });
  window.location.href = "/login?" + next;
}

// 다른 사이트로 보내는 데 악용되지 않도록 같은 사이트 주소만 따른다. 주소 판별은 브라우저 파서에 맡긴다
// next는 앱 안의 경로다. 이동할 때 앱 시작 주소를 앞에 붙인다
function nextPathAfterLogin() {
  const next = new URLSearchParams(window.location.search).get("next");
  const home = appRoot();
  if (!next || !next.startsWith("/") || next.startsWith("//")) return home;
  try {
    const target = new URL(next, window.location.origin);
    if (target.origin !== window.location.origin) return home;
    return home + (target.pathname + target.search).slice(1);
  } catch {
    return home;
  }
}

// 쿠키만으로 요청이 위조되지 않도록 쓰기 요청마다 세션의 CSRF 토큰을 함께 보낸다.
// makeRequest는 토큰을 받아 fetch("/api/…", …)를 부르는 함수다
async function withCsrf(makeRequest) {
  const session = await readJson(fetch("/api/v1/auth/session", jsonRequest("GET")));
  if (!session.ok || !session.data?.user) {
    goToLogin();
    return null;
  }
  return readJson(makeRequest(session.data.csrf_token));
}

function isVerified() {
  return document.querySelector("main").dataset.emailVerified === "true";
}

function requireVerified() {
  if (isVerified()) return true;
  showMessage(NOT_VERIFIED_MESSAGE, "error");
  return false;
}

function showMessage(text, kind) {
  const element = document.getElementById("message");
  element.textContent = text;
  element.className = `message ${kind}`;
  element.hidden = false;
}

function describeError(error) {
  // 잠금 해제까지 남은 시간을 알려 주면 사용자가 언제 다시 시도할지 알 수 있다
  if (error.retry_after) {
    const minutes = Math.ceil(error.retry_after / 60);
    const wait = error.retry_after < 60 ? `${error.retry_after}초` : `${minutes}분`;
    return `${error.message} (${wait} 후 가능)`;
  }
  return error.message;
}

function clearFieldErrors(form) {
  form.querySelectorAll(".field-error").forEach((element) => {
    element.textContent = "";
    element.hidden = true;
  });
  form.querySelectorAll("[aria-invalid]").forEach((input) => {
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-errormessage");
  });
}

function showFieldErrors(form, fields) {
  for (const [name, text] of Object.entries(fields ?? {})) {
    const input = form.elements[name];
    const errorElement = document.getElementById(`${name}-error`);
    if (!input || !errorElement) continue;
    errorElement.textContent = text;
    errorElement.hidden = false;
    input.setAttribute("aria-invalid", "true");
    input.setAttribute("aria-errormessage", errorElement.id);
  }
}

function setupForm(form, submit) {
  const button = form.querySelector('button[type="submit"]');
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearFieldErrors(form);
    document.getElementById("message").hidden = true;
    // 응답을 받기 전에 다시 누르면 메일이 두 번 가거나 시도 횟수가 늘어나므로 막는다
    button.disabled = true;
    try {
      const result = await submit(form);
      if (!result.ok) {
        showFieldErrors(form, result.error.fields);
        showMessage(describeError(result.error), "error");
      }
    } finally {
      button.disabled = false;
    }
  });
}

async function submitLogin(form) {
  const result = await readJson(fetch("/api/v1/auth/login", jsonRequest("POST", {
    email: form.elements.email.value,
    password: form.elements.password.value,
  })));
  if (result.ok) window.location.href = nextPathAfterLogin();
  return result;
}

async function submitSignup(form) {
  const result = await readJson(fetch("/api/v1/auth/signup", jsonRequest("POST", {
    email: form.elements.email.value,
    password: form.elements.password.value,
    display_name: form.elements.display_name.value,
    terms_agreed: form.elements.terms_agreed.checked,
    privacy_agreed: form.elements.privacy_agreed.checked,
  })));
  if (result.ok) window.location.href = "/signup/sent";
  return result;
}

async function submitForgot(form) {
  const result = await readJson(fetch("/api/v1/auth/password-reset/request", jsonRequest("POST", { email: form.elements.email.value })));
  if (result.ok) showMessage(result.data.message, "ok");
  return result;
}

// 재설정 링크의 토큰은 주소 조각에서 한 번 읽어 변수에만 둔다
let resetToken = null;

function readResetToken() {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
  if (token) resetToken = token;
  // 토큰이 방문 기록과 화면 공유에 남지 않도록 주소에서 지운다
  window.history.replaceState(null, "", window.location.pathname);
}

async function submitReset(form) {
  const newPassword = form.elements.new_password.value;
  if (newPassword !== form.elements.new_password_again.value) {
    return {
      ok: false,
      error: {
        code: "VALIDATION_FAILED",
        message: "입력값을 확인해 주세요.",
        fields: { new_password_again: "새 비밀번호가 서로 다릅니다." },
      },
    };
  }
  if (!resetToken) {
    return { ok: false, error: { code: "TOKEN_INVALID", message: "재설정 링크가 올바르지 않습니다. 메일의 링크를 다시 눌러 주세요." } };
  }
  const result = await readJson(fetch("/api/v1/auth/password-reset/confirm", jsonRequest("POST", { token: resetToken, new_password: newPassword })));
  if (result.ok) {
    resetToken = null;
    form.reset();
    showMessage(`${result.data.message}`, "ok");
    window.setTimeout(() => { window.location.href = "/login"; }, 1500);
  }
  return result;
}

async function submitSocialComplete(form) {
  const result = await readJson(fetch("/api/v1/auth/social/complete", jsonRequest("POST", { email: form.elements.email.value })));
  if (result.ok) showMessage(result.data.message, "ok");
  return result;
}

async function verifyEmailFromLink() {
  const status = document.getElementById("verify-status");
  status.textContent = "인증을 확인하는 중입니다.";
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
  // 토큰이 방문 기록과 화면 공유에 남지 않도록 주소에서 지운다
  window.history.replaceState(null, "", window.location.pathname);
  if (!token) {
    status.textContent = "인증 링크가 올바르지 않습니다. 메일의 링크를 다시 눌러 주세요.";
    return;
  }
  const result = await readJson(fetch("/api/v1/auth/verify-email", jsonRequest("POST", { token })));
  status.textContent = result.ok
    ? result.data.message
    : `${result.error.message} 로그인한 뒤 인증 메일을 다시 받을 수 있습니다.`;
}

function setupHome() {
  const logoutButton = document.getElementById("logout-button");
  logoutButton.addEventListener("click", async () => {
    logoutButton.disabled = true;
    const result = await withCsrf((token) => fetch("/api/v1/auth/logout", jsonRequest("POST", undefined, token)));
    if (result === null) return;
    if (result.ok) {
      window.location.href = "/login";
      return;
    }
    logoutButton.disabled = false;
    showMessage(describeError(result.error), "error");
  });

  const resendButton = document.getElementById("resend-button");
  if (!resendButton) return;
  resendButton.addEventListener("click", async () => {
    resendButton.disabled = true;
    const result = await withCsrf((token) => fetch("/api/v1/auth/resend-verification", jsonRequest("POST", undefined, token)));
    if (result === null) return;
    resendButton.disabled = false;
    if (result.ok) showMessage(result.data.message, "ok");
    else showMessage(describeError(result.error), "error");
  });
}

function start() {
  const page = document.querySelector("main")?.dataset.page;
  if (page === "login") setupForm(document.getElementById("login-form"), submitLogin);
  if (page === "signup") setupForm(document.getElementById("signup-form"), submitSignup);
  if (page === "signup-social") setupForm(document.getElementById("social-complete-form"), submitSocialComplete);
  if (page === "forgot-password") setupForm(document.getElementById("forgot-form"), submitForgot);
  if (page === "reset-password") {
    readResetToken();
    // 같은 탭에 새 링크를 붙여 넣으면 # 뒤만 바뀌어 페이지가 다시 열리지 않는다
    window.addEventListener("hashchange", readResetToken);
    setupForm(document.getElementById("reset-form"), submitReset);
  }
  if (page === "verify-email") {
    verifyEmailFromLink();
    // 같은 탭에 새 링크를 붙여 넣으면 # 뒤만 바뀌어 페이지가 다시 열리지 않는다
    window.addEventListener("hashchange", verifyEmailFromLink);
  }
  // 로그아웃과 인증 안내 띠는 회원 화면 공통 틀에 있다
  if (document.getElementById("logout-button")) setupHome();
}

start();
