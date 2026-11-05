// 2026-11-04 - smart-voca - 가입, 로그인, 인증, 비밀번호 재설정, 로그아웃 화면의 동작
// 파일 위치: src/web/static/auth.js

"use strict";

const API_BASE = "/api/v1/auth";
const NETWORK_ERROR = { code: "NETWORK", message: "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요." };
const UNKNOWN_ERROR = { code: "UNKNOWN", message: "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요." };
const NOT_VERIFIED_MESSAGE = "이메일 인증이 필요합니다. 메일의 링크를 먼저 눌러 주세요.";

async function requestJson(url, { method = "POST", body, formData, csrfToken } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      credentials: "same-origin",
      // 파일 업로드는 브라우저가 Content-Type과 경계 값을 직접 정한다
      body: formData ?? (body === undefined ? undefined : JSON.stringify(body)),
    });
  } catch {
    return { ok: false, status: 0, error: NETWORK_ERROR };
  }
  // 프록시 오류처럼 본문이 JSON이 아닌 응답도 화면이 멈추지 않게 처리한다
  const data = await response.json().catch(() => null);
  return { ok: response.ok, status: response.status, data, error: data?.error ?? UNKNOWN_ERROR };
}

function callApi(path, options) {
  return requestJson(`${API_BASE}${path}`, options);
}

// 세션이 끝나면 로그인 뒤 지금 화면으로 돌아오게 한다 (화면 설계 §5.3)
function goToLogin() {
  const here = window.location.pathname + window.location.search;
  window.location.assign(`/login?${new URLSearchParams({ next: here })}`);
}

// 다른 사이트로 보내는 데 악용되지 않도록 같은 사이트 주소만 따른다. 주소 판별은 브라우저 파서에 맡긴다
function nextPathAfterLogin() {
  const next = new URLSearchParams(window.location.search).get("next");
  if (!next) return "/";
  try {
    const target = new URL(next, window.location.origin);
    return target.origin === window.location.origin ? target.pathname + target.search : "/";
  } catch {
    return "/";
  }
}

// 쿠키만으로 요청이 위조되지 않도록 쓰기 요청마다 세션의 CSRF 토큰을 함께 보낸다
async function sendWithSession(url, options) {
  const session = await callApi("/session", { method: "GET" });
  if (!session.ok || !session.data?.user) {
    goToLogin();
    return null;
  }
  return requestJson(url, { ...options, csrfToken: session.data.csrf_token });
}

function callWithSession(path) {
  return sendWithSession(`${API_BASE}${path}`);
}

function writeJson(url, method, body) {
  return sendWithSession(url, { method, body });
}

function writeForm(url, formData) {
  return sendWithSession(url, { method: "POST", formData });
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
  const result = await callApi("/login", {
    body: { email: form.elements.email.value, password: form.elements.password.value },
  });
  if (result.ok) window.location.assign(nextPathAfterLogin());
  return result;
}

async function submitSignup(form) {
  const result = await callApi("/signup", {
    body: {
      email: form.elements.email.value,
      password: form.elements.password.value,
      display_name: form.elements.display_name.value,
      terms_agreed: form.elements.terms_agreed.checked,
      privacy_agreed: form.elements.privacy_agreed.checked,
    },
  });
  if (result.ok) window.location.assign("/signup/sent");
  return result;
}

async function submitForgot(form) {
  const result = await callApi("/password-reset/request", { body: { email: form.elements.email.value } });
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
  const result = await callApi("/password-reset/confirm", { body: { token: resetToken, new_password: newPassword } });
  if (result.ok) {
    resetToken = null;
    form.reset();
    showMessage(`${result.data.message}`, "ok");
    window.setTimeout(() => window.location.assign("/login"), 1500);
  }
  return result;
}

async function submitSocialComplete(form) {
  const result = await callApi("/social/complete", { body: { email: form.elements.email.value } });
  if (result.ok) showMessage(result.data.message, "ok");
  return result;
}

async function verifyEmailFromLink() {
  const status = document.getElementById("verify-status");
  status.textContent = "인증을 확인하는 중입니다.";
  const token =new URLSearchParams(window.location.hash.slice(1)).get("token");
  // 토큰이 방문 기록과 화면 공유에 남지 않도록 주소에서 지운다
  window.history.replaceState(null, "", window.location.pathname);
  if (!token) {
    status.textContent = "인증 링크가 올바르지 않습니다. 메일의 링크를 다시 눌러 주세요.";
    return;
  }
  const result = await callApi("/verify-email", { body: { token } });
  status.textContent = result.ok
    ? result.data.message
    : `${result.error.message} 로그인한 뒤 인증 메일을 다시 받을 수 있습니다.`;
}

function setupHome() {
  const logoutButton = document.getElementById("logout-button");
  logoutButton.addEventListener("click", async () => {
    logoutButton.disabled = true;
    const result = await callWithSession("/logout");
    if (result === null) return;
    if (result.ok) {
      window.location.assign("/login");
      return;
    }
    logoutButton.disabled = false;
    showMessage(describeError(result.error), "error");
  });

  const resendButton = document.getElementById("resend-button");
  if (!resendButton) return;
  resendButton.addEventListener("click", async () => {
    resendButton.disabled = true;
    const result = await callWithSession("/resend-verification");
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
