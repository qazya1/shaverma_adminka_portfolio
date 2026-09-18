const usernameEl = document.getElementById("current-username");
const logoutButton = document.getElementById("logout-button");
const errorEl = document.getElementById("app-error");
const createForm = document.getElementById("create-form");
const createButton = document.getElementById("create-button");
const labelInput = document.getElementById("f-label");
const nameInput = document.getElementById("f-name");
const systemNameInput = document.getElementById("f-system-name");
const activeInput = document.getElementById("f-is-active");
const telegramInput = document.getElementById("f-channel-telegram");
const maxInput = document.getElementById("f-channel-max");
const wizardIntro = document.getElementById("wizard-intro");
const stepWizard = document.getElementById("step-wizard");
const successStage = document.getElementById("success-stage");

const preview = {
  name: document.getElementById("preview-name"),
  avatar: document.getElementById("preview-avatar"),
  domain: document.getElementById("preview-domain"),
  systemName: document.getElementById("preview-system-name"),
  telegram: document.getElementById("preview-telegram"),
  max: document.getElementById("preview-max"),
  active: document.getElementById("preview-active"),
};

const summary = {
  name: document.getElementById("summary-name"),
  domain: document.getElementById("summary-domain"),
  systemName: document.getElementById("summary-system-name"),
  channels: document.getElementById("summary-channels"),
  active: document.getElementById("summary-active"),
};

const provisioningKeys = ["dirs", "backend_uploaded", "env_generated", "frontend_built", "nginx", "systemd"];
const provisionNumbers = { dirs: "01", backend_uploaded: "02", env_generated: "03", frontend_built: "04", nginx: "05", systemd: "06" };
let serviceId = new URLSearchParams(window.location.search).get("id");
let currentStep = 1;
let createdService = null;

// Seed (DB fill) is deliberately NOT one of provisioningKeys above -- it's
// optional and repeatable (unlike the 6 required steps), so it never
// gates showSuccess(); it's only offered once the service is already
// fully live, on the success screen itself, where .env (and therefore a
// working DATABASE_URL) is guaranteed to already exist.
const seedPanelEl = document.getElementById("seed-panel");
const seedEmptyHintEl = document.getElementById("seed-empty-hint");
const seedControlsEl = document.getElementById("seed-controls");
const seedPairSelect = document.getElementById("seed-pair-select");
const seedDataEditor = document.getElementById("seed-data-editor");
const seedSaveButton = document.getElementById("seed-save-button");
const seedRunButton = document.getElementById("seed-run-button");
const seedSaveStatusEl = document.getElementById("seed-save-status");
const seedRunOutputEl = document.getElementById("seed-run-output");
let currentSeedPairKey = "";

function serviceDomain() {
  const label = labelInput.value.trim();
  return label ? `https://${label}.example-service.рф` : "Появится после ввода";
}

function serviceName() {
  return nameInput.value.trim() || "Название заведения";
}

function updatePreview() {
  const name = serviceName();
  const domain = serviceDomain();
  const systemName = systemNameInput.value.trim() || "—";
  const active = activeInput.checked;
  const channels = [telegramInput.checked ? "Telegram" : null, maxInput.checked ? "MAX" : null].filter(Boolean);

  preview.name.textContent = name;
  preview.avatar.textContent = name.slice(0, 1).toUpperCase();
  preview.domain.textContent = domain;
  preview.systemName.textContent = systemName;
  preview.telegram.textContent = telegramInput.checked ? "Подключён" : "Не подключён";
  preview.max.textContent = maxInput.checked ? "Подключён" : "Не подключён";
  preview.active.textContent = active ? "Активен после запуска" : "Создаётся остановленным";

  summary.name.textContent = nameInput.value.trim() || "—";
  summary.domain.textContent = domain;
  summary.systemName.textContent = systemName;
  summary.channels.textContent = channels.length ? channels.join(" · ") : "Каналы не выбраны";
  summary.active.textContent = active ? "Активен" : "Остановлен";

  document.getElementById("url-preview").textContent = labelInput.value.trim()
    ? `Будет: ${domain}`
    : "Адрес появится здесь";
}

function setError(message) {
  if (!message) {
    errorEl.textContent = "";
    errorEl.classList.add("hidden");
    return;
  }
  errorEl.textContent = message;
  errorEl.classList.remove("hidden");
}

function markFieldValidity(input, valid) {
  input.classList.toggle("is-invalid", !valid);
  input.classList.toggle("is-valid", valid && input.value.trim().length > 0);
}

function validateStep(step) {
  const screen = document.querySelector(`[data-wizard-step="${step}"]`);
  const requiredInputs = [...screen.querySelectorAll("input[required]")];
  const valid = requiredInputs.every((input) => {
    const isValid = input.checkValidity() && input.value.trim().length > 0;
    markFieldValidity(input, isValid);
    return isValid;
  });
  if (!valid) {
    setError("Заполните обязательные поля, чтобы продолжить.");
    const firstInvalid = requiredInputs.find((input) => input.classList.contains("is-invalid"));
    firstInvalid?.focus();
  }
  return valid;
}

function updateProgress(step) {
  document.querySelectorAll("[data-progress-step]").forEach((item) => {
    const itemStep = Number(item.dataset.progressStep);
    item.classList.toggle("active", itemStep === step);
    item.classList.toggle("complete", itemStep < step);
    const marker = item.querySelector("span");
    marker.innerHTML = itemStep < step ? iconSvg("check", "icon icon-small") : String(itemStep).padStart(2, "0");
  });
}

function setWizardStep(step) {
  if (step > currentStep && !validateStep(currentStep)) return;
  setError(null);
  currentStep = step;
  document.querySelectorAll("[data-wizard-step]").forEach((screen) => {
    const active = Number(screen.dataset.wizardStep) === step;
    screen.hidden = !active;
    screen.classList.toggle("active", active);
  });
  updateProgress(step);
  updatePreview();
  document.querySelector(`[data-wizard-step="${step}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function populateService(service) {
  if (!service) return;
  createdService = service;
  nameInput.value = service.name || nameInput.value;
  labelInput.value = service.label || labelInput.value;
  systemNameInput.value = service.system_name || systemNameInput.value;
  activeInput.checked = service.is_active !== false;
  const name = service.name || serviceName();
  document.getElementById("provision-avatar").textContent = name.slice(0, 1).toUpperCase();
  document.getElementById("provision-name").textContent = name;
  document.getElementById("provision-system-name").textContent = service.system_name || "—";
  updatePreview();
}

function showWizard() {
  createForm.classList.add("hidden");
  wizardIntro.classList.add("hidden");
  successStage.classList.add("hidden");
  stepWizard.classList.remove("hidden");

  const systemName = systemNameInput.value.trim();
  const dbNameField = document.getElementById("f-database-name");
  const dbUserField = document.getElementById("f-database-user");
  if (systemName && !dbNameField.value) dbNameField.value = systemName;
  if (systemName && !dbUserField.value) dbUserField.value = systemName;

  const name = serviceName();
  document.getElementById("provision-avatar").textContent = name.slice(0, 1).toUpperCase();
  document.getElementById("provision-name").textContent = name;
  document.getElementById("provision-system-name").textContent = systemName || "—";
}

function setProvisionState(key, done) {
  const item = document.querySelector(`[data-provision-key="${key}"]`);
  const marker = document.querySelector(`[data-provision-marker="${key}"]`);
  if (!item || !marker) return;
  item.classList.toggle("done", done);
  item.classList.toggle("pending", !done);
  marker.innerHTML = done ? iconSvg("check", "icon icon-small") : provisionNumbers[key];
}

function showSuccess() {
  const domain = serviceDomain();
  const name = serviceName();
  stepWizard.classList.add("hidden");
  successStage.classList.remove("hidden");
  document.getElementById("success-name").textContent = name;
  document.getElementById("success-domain").textContent = domain;
  const serviceLink = document.getElementById("success-service-link");
  serviceLink.href = domain.startsWith("https://") ? domain : "#";
  loadSeedPairs();
}

// --- Seed (DB fill), offered on the success screen ----------------------

function pairLabel(pairKey) {
  return pairKey ? pairKey : "(по умолчанию)";
}

function seedDataIsDirty() {
  return seedDataEditor.value !== seedDataEditor.dataset.loaded;
}

async function loadSeedPairs() {
  if (!serviceId) return;
  try {
    const data = await apiRequest(`/services/${serviceId}/seed/pairs`, { method: "GET" });

    if (!data.pairs || data.pairs.length === 0) {
      seedEmptyHintEl.classList.remove("hidden");
      seedControlsEl.classList.add("hidden");
      return;
    }

    seedEmptyHintEl.classList.add("hidden");
    seedControlsEl.classList.remove("hidden");
    seedPairSelect.innerHTML = "";
    for (const pairKey of data.pairs) {
      const option = document.createElement("option");
      option.value = pairKey;
      option.textContent = pairLabel(pairKey);
      seedPairSelect.appendChild(option);
    }
    await loadSeedData(seedPairSelect.value);
  } catch (error) {
    setError(error.message || "Не удалось получить список seed-скриптов.");
  }
}

async function loadSeedData(pairKey) {
  setError(null);
  seedRunOutputEl.classList.add("hidden");
  seedSaveStatusEl.textContent = "";
  try {
    const data = await apiRequest(`/services/${serviceId}/seed/data?pair_key=${encodeURIComponent(pairKey)}`, {
      method: "GET",
    });
    seedDataEditor.value = data.content;
    seedDataEditor.dataset.loaded = data.content;
    currentSeedPairKey = pairKey;
  } catch (error) {
    setError(error.message || "Не удалось загрузить seed_data.");
  }
}

seedPairSelect.addEventListener("change", () => {
  if (seedDataIsDirty() && !window.confirm("Несохранённые изменения будут потеряны. Продолжить?")) {
    seedPairSelect.value = currentSeedPairKey;
    return;
  }
  loadSeedData(seedPairSelect.value);
});

seedSaveButton.addEventListener("click", async () => {
  setError(null);
  seedSaveStatusEl.textContent = "";

  seedSaveButton.disabled = true;
  try {
    const data = await apiRequest(`/services/${serviceId}/seed/data`, {
      method: "POST",
      body: { pair_key: seedPairSelect.value, content: seedDataEditor.value },
    });
    seedDataEditor.value = data.content;
    seedDataEditor.dataset.loaded = data.content;
    seedSaveStatusEl.textContent = "Сохранено.";
  } catch (error) {
    setError(error.message || "Не удалось сохранить seed_data.");
  } finally {
    seedSaveButton.disabled = false;
  }
});

seedRunButton.addEventListener("click", async () => {
  setError(null);

  if (seedDataIsDirty()) {
    setError("Есть несохранённые изменения в seed_data — сначала сохраните их.");
    return;
  }

  const pairKey = seedPairSelect.value;
  const proceed = window.confirm(
    `Запустить заполнение БД парой «${pairLabel(pairKey)}»? Сама идемпотентность (можно ли безопасно запускать повторно) — на совести скрипта, это ничем не проверяется здесь.`
  );
  if (!proceed) {
    return;
  }

  seedRunButton.disabled = true;
  seedRunOutputEl.classList.remove("hidden", "is-failure");
  seedRunOutputEl.textContent = "Выполняется…";
  try {
    const data = await apiRequest(`/services/${serviceId}/seed/run`, {
      method: "POST",
      body: { pair_key: pairKey },
    });
    const succeeded = data.exit_code === 0 && !data.timed_out;
    seedRunOutputEl.classList.toggle("is-failure", !succeeded);

    const lines = [
      succeeded
        ? "Готово."
        : `Ошибка (код завершения: ${data.exit_code}${data.timed_out ? ", таймаут" : ""}).`,
    ];
    if (data.stdout) lines.push("--- stdout ---", data.stdout);
    if (data.stderr) lines.push("--- stderr ---", data.stderr);
    seedRunOutputEl.textContent = lines.join("\n");
  } catch (error) {
    seedRunOutputEl.classList.add("is-failure");
    seedRunOutputEl.textContent = error.message || "Не удалось выполнить запрос.";
  } finally {
    seedRunButton.disabled = false;
  }
});

async function refreshStatus() {
  if (!serviceId) return;
  try {
    const status = await apiRequest(`/services/${serviceId}/provision/status`, { method: "GET" });
    const allDone = provisioningKeys.every((key) => Boolean(status[key]?.done));
    provisioningKeys.forEach((key) => setProvisionState(key, Boolean(status[key]?.done)));
    if (allDone) showSuccess();
  } catch (error) {
    setError(error.message || "Не удалось обновить статус подготовки.");
  }
}

async function runStep(button, key, fn) {
  setError(null);
  const item = document.querySelector(`[data-provision-key="${key}"]`);
  item?.classList.add("is-running");
  button.disabled = true;
  button.classList.add("is-loading");
  try {
    return await fn();
  } catch (error) {
    setError(error.message || "Не удалось выполнить этап подготовки.");
    return null;
  } finally {
    item?.classList.remove("is-running");
    button.disabled = false;
    button.classList.remove("is-loading");
    await refreshStatus();
  }
}

async function loadCurrentAdmin() {
  try {
    const data = await apiRequest("/auth/me", { method: "GET" });
    usernameEl.textContent = data.admin.username;
  } catch (error) {
    window.location.href = "login.html";
  }
}

async function loadExistingService() {
  if (!serviceId) return;
  try {
    const services = await apiRequest("/services", { method: "GET" });
    populateService(services.find((service) => String(service.id) === String(serviceId)));
  } catch (error) {
    // The provisioning status endpoint remains the source of truth for a resumed flow.
  }
}

logoutButton.addEventListener("click", async () => {
  try {
    await apiRequest("/auth/logout", { method: "POST" });
    window.location.href = "login.html";
  } catch (error) {
    setError(error.message || "Не удалось завершить сессию.");
  }
});

[nameInput, labelInput, systemNameInput, activeInput, telegramInput, maxInput].forEach((input) => {
  input.addEventListener("input", updatePreview);
  input.addEventListener("change", updatePreview);
  input.addEventListener("blur", () => {
    if (input.required) markFieldValidity(input, input.checkValidity() && input.value.trim().length > 0);
  });
});

document.querySelectorAll("[data-step-target]").forEach((button) => {
  button.addEventListener("click", () => setWizardStep(Number(button.dataset.stepTarget)));
});

createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!validateStep(1)) {
    setWizardStep(1);
    return;
  }
  setError(null);
  createButton.disabled = true;
  createButton.classList.add("is-loading");

  const channels = [];
  if (telegramInput.checked) channels.push("telegram");
  if (maxInput.checked) channels.push("max");
  const payload = {
    label: labelInput.value.trim(),
    name: nameInput.value.trim(),
    system_name: systemNameInput.value.trim(),
    is_active: activeInput.checked,
    channels,
    bot_entry_key: document.getElementById("f-bot-entry-key").value.trim() || null,
    client_bot_entry_key: document.getElementById("f-client-bot-entry-key").value.trim() || null,
  };

  try {
    const service = await apiRequest("/services", { method: "POST", body: payload });
    serviceId = service.id;
    populateService(service);
    showWizard();
    await refreshStatus();
  } catch (error) {
    setError(error.message || "Не удалось создать сервис.");
  } finally {
    createButton.disabled = false;
    createButton.classList.remove("is-loading");
  }
});

document.getElementById("dirs-button").addEventListener("click", () => {
  const button = document.getElementById("dirs-button");
  runStep(button, "dirs", () => apiRequest(`/services/${serviceId}/provision/dirs`, { method: "POST" }));
});

document.getElementById("upload-button").addEventListener("click", () => {
  const button = document.getElementById("upload-button");
  const fileInput = document.getElementById("upload-file");
  if (!fileInput.files.length) {
    setError("Выберите zip-файл с папками frontend и backend.");
    return;
  }
  runStep(button, "backend_uploaded", () => {
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    return apiUpload(`/services/${serviceId}/provision/upload`, formData);
  });
});

document.getElementById("env-button").addEventListener("click", () => {
  const button = document.getElementById("env-button");
  const databaseName = document.getElementById("f-database-name").value.trim();
  const databaseUser = document.getElementById("f-database-user").value.trim();
  if (!databaseName || !databaseUser) {
    setError("Укажите имя базы данных и пользователя БД.");
    return;
  }
  runStep(button, "env_generated", async () => {
    await apiRequest(`/services/${serviceId}/provision/env`, {
      method: "POST",
      body: {
        database_name: databaseName,
        database_user: databaseUser,
        yookassa_recurring_payments_enabled: document.getElementById("f-yookassa-recurring").checked,
        yookassa_shop_id: document.getElementById("f-yookassa-shop-id").value.trim() || null,
        yookassa_secret_key: document.getElementById("f-yookassa-secret-key").value.trim() || null,
        telegram_web_app_local_sdk_enabled: document.getElementById("f-telegram-web-app-local-sdk").checked,
      },
    });
    const hint = document.getElementById("env-hint");
    hint.textContent = "Сгенерировано, включая БД и пароль к ней. ";
    const link = document.createElement("a");
    link.href = `service-env.html?id=${encodeURIComponent(serviceId)}`;
    link.textContent = "Открыть редактор .env";
    hint.appendChild(link);
  });
});

document.getElementById("frontend-button").addEventListener("click", () => {
  const button = document.getElementById("frontend-button");
  runStep(button, "frontend_built", () => apiRequest(`/services/${serviceId}/provision/frontend`, { method: "POST" }));
});

document.getElementById("nginx-button").addEventListener("click", () => {
  const button = document.getElementById("nginx-button");
  runStep(button, "nginx", async () => {
    const result = await apiRequest(`/services/${serviceId}/provision/nginx`, { method: "POST" });
    document.getElementById("f-port").value = result.port;
    document.getElementById("nginx-hint").textContent = `Выделен порт: ${result.port}`;
  });
});

document.getElementById("systemd-button").addEventListener("click", () => {
  const button = document.getElementById("systemd-button");
  const port = Number.parseInt(document.getElementById("f-port").value, 10);
  if (!port) {
    setError("Сначала настройте nginx или укажите порт вручную.");
    return;
  }
  runStep(button, "systemd", () => apiRequest(`/services/${serviceId}/provision/systemd`, { method: "POST", body: { port } }));
});

document.getElementById("refresh-status-button").addEventListener("click", refreshStatus);

updatePreview();
loadCurrentAdmin();
if (serviceId) {
  showWizard();
  loadExistingService().finally(refreshStatus);
}
