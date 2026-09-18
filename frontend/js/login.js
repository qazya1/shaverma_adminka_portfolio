let currentChallengeId = null;

const step1 = document.getElementById("step-1");
const step2 = document.getElementById("step-2");

const passwordForm = document.getElementById("password-form");
const passwordError = document.getElementById("password-error");

const otpForm = document.getElementById("otp-form");
const otpError = document.getElementById("otp-error");
const otpHint = document.getElementById("otp-hint");
const backButton = document.getElementById("back-button");
const localDemoNote = document.getElementById("local-demo-note");

if (LOCAL_DEMO_MODE) {
  localDemoNote.textContent = "Локальный режим: логин 1, пароль 1. Telegram-код не требуется.";
  localDemoNote.classList.remove("hidden");
  document.getElementById("username").value = "1";
  document.getElementById("password").value = "1";
}

function showStep(step) {
  step1.classList.remove("active");
  step2.classList.remove("active");
  step.classList.add("active");
}

function setError(el, message) {
  if (!message) {
    el.classList.remove("visible");
    el.textContent = "";
    return;
  }
  el.textContent = message;
  el.classList.add("visible");
}

passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setError(passwordError, null);

  const submitButton = passwordForm.querySelector("button[type=submit]");
  submitButton.disabled = true;

  try {
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;

    const data = await apiRequest("/auth/login/start", {
      method: "POST",
      body: { username, password },
    });

    if (data.local_demo) {
      window.location.href = "index.html";
      return;
    }

    currentChallengeId = data.challenge_id;
    otpHint.textContent = "Code sent via Telegram, expires " + new Date(data.expires_at).toLocaleTimeString();
    document.getElementById("otp-code").value = "";
    setError(otpError, null);
    showStep(step2);
  } catch (err) {
    setError(passwordError, err.message || "Login failed");
  } finally {
    submitButton.disabled = false;
  }
});

otpForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setError(otpError, null);

  const submitButton = otpForm.querySelector("button[type=submit]");
  submitButton.disabled = true;

  try {
    const code = document.getElementById("otp-code").value.trim();

    await apiRequest("/auth/login/verify", {
      method: "POST",
      body: { challenge_id: currentChallengeId, code },
    });

    window.location.href = "index.html";
  } catch (err) {
    setError(otpError, err.message || "Verification failed");
  } finally {
    submitButton.disabled = false;
  }
});

backButton.addEventListener("click", () => {
  currentChallengeId = null;
  setError(otpError, null);
  showStep(step1);
});
