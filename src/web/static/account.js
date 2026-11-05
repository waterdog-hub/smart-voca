// 2026-11-05 - smart-voca - 내 계정 화면: 표시 이름, 비밀번호 변경, 모든 기기 로그아웃, 탈퇴 (화면 설계 §4.6)
// 파일 위치: src/web/static/account.js

"use strict";

const ME_API = "/api/v1/me";
const DELETE_WORD = "탈퇴";

async function submitName(form) {
  if (!requireVerified()) return { ok: true };
  const result = await writeJson(ME_API, "PATCH", { display_name: form.elements.display_name.value });
  if (result === null) return { ok: true };
  if (!result.ok) return result;
  showMessage("표시 이름을 저장했습니다.", "ok");
  document.querySelector(".member-nav-user span").textContent = `${result.data.display_name} 님`;
  return result;
}

async function submitPassword(form) {
  const result = await writeJson(`${ME_API}/password`, "POST", {
    current_password: form.elements.current_password.value,
    new_password: form.elements.new_password.value,
  });
  if (result === null) return { ok: true };
  if (!result.ok) return result;
  form.reset();
  showMessage(result.data.message, "ok");
  return result;
}

async function submitDelete(form) {
  if (form.elements.confirm.value.trim() !== DELETE_WORD) {
    return {
      ok: false,
      error: {
        code: "VALIDATION_FAILED",
        message: "입력값을 확인해 주세요.",
        fields: { confirm: `"${DELETE_WORD}"를 정확히 입력해 주세요.` },
      },
    };
  }
  if (!window.confirm("정말 탈퇴할까요? 모든 학습 데이터가 삭제되며 되돌릴 수 없습니다.")) return { ok: true };
  const result = await writeJson(`${ME_API}/delete`, "POST", { password: form.elements.password.value });
  if (result === null) return { ok: true };
  if (result.ok) window.location.assign("/login?withdrawn=1");
  // 서버는 비밀번호 확인 오류를 current_password 칸으로 알리지만, 이 폼의 칸 이름은 password다
  const fields = result.error?.fields;
  if (fields?.current_password) {
    result.error.fields = { ...fields, password: fields.current_password };
  }
  return result;
}

function setupLogoutAll() {
  const button = document.getElementById("logout-all-button");
  button.addEventListener("click", async () => {
    button.disabled = true;
    const result = await callWithSession("/logout-all");
    if (result === null) return;
    if (result.ok) {
      window.location.assign("/login");
      return;
    }
    button.disabled = false;
    showMessage(describeError(result.error), "error");
  });
}

setupForm(document.getElementById("name-form"), submitName);
setupForm(document.getElementById("password-form"), submitPassword);
setupForm(document.getElementById("delete-form"), submitDelete);
setupLogoutAll();
