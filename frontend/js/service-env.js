const params = new URLSearchParams(window.location.search);
const serviceId = params.get("id");

const usernameEl = document.getElementById("current-username");
const logoutButton = document.getElementById("logout-button");
const errorEl = document.getElementById("app-error");
const loadingEl = document.getElementById("loading");
const panelEl = document.getElementById("env-panel");
const pageTitleEl = document.getElementById("page-title");
const pathHintEl = document.getElementById("path-hint");
const bodyEl = document.getElementById("env-body");
const addFieldButton = document.getElementById("add-field-button");
const saveButton = document.getElementById("save-button");
const revealAllCheckbox = document.getElementById("reveal-all");
const updatePanelEl = document.getElementById("update-panel");
const updateFileInput = document.getElementById("update-file");
const updateButton = document.getElementById("update-button");
const updateResultEl = document.getElementById("update-result");
const seedPanelEl = document.getElementById("seed-panel");
const seedEmptyHintEl = document.getElementById("seed-empty-hint");
const seedControlsEl = document.getElementById("seed-controls");
const seedPairSelect = document.getElementById("seed-pair-select");
const seedDataEditor = document.getElementById("seed-data-editor");
const seedSaveButton = document.getElementById("seed-save-button");
const seedRunButton = document.getElementById("seed-run-button");
const seedSaveStatusEl = document.getElementById("seed-save-status");
const seedRunOutputEl = document.getElementById("seed-run-output");

let originalKeys = new Set();
let currentSeedPairKey = "";

function setError(message) {
  if (!message) {
    errorEl.classList.remove("visible");
    errorEl.textContent = "";
    return;
  }
  errorEl.textContent = message;
  errorEl.classList.add("visible");
}

function scrollToHashTarget() {
  // Deep-linked from the dashboard's "..." menu (e.g.
  // service-env.html?id=X#seed-panel) -- the browser's own anchor
  // navigation can't do this itself: #env-panel/#update-panel/#seed-panel
  // all start `hidden` (display: none) until this page's own JS reveals
  // them, and a hidden target is never scrolled to on initial load, nor
  // retried once it becomes visible later.
  const hash = window.location.hash;
  if (!hash) return;
  const target = document.querySelector(hash);
  target?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function escapeHtml(value) {
  // Used both as element text content and inside double-quoted HTML
  // attributes (value="...") below, so quotes must be escaped too --
  // textContent->innerHTML alone only escapes &, <, > (per the HTML
  // fragment serialization spec), which is not enough to stop an
  // attribute breakout via a literal " in an env key/value.
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML.replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function addRow(key, value) {
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><input type="text" class="env-key" value="${escapeHtml(key)}" placeholder="KEY_NAME" /></td>
    <td><input type="${revealAllCheckbox.checked ? "text" : "password"}" class="env-value" value="${escapeHtml(value)}" autocomplete="off" /></td>
    <td><button type="button" class="secondary remove-row">×</button></td>
  `;
  bodyEl.appendChild(tr);
}

function renderRows(entries) {
  bodyEl.innerHTML = "";
  for (const entry of entries) {
    addRow(entry.key, entry.value);
  }
}

function readRows() {
  const rows = [...bodyEl.querySelectorAll("tr")];
  return rows.map((row) => ({
    key: row.querySelector(".env-key").value.trim(),
    value: row.querySelector(".env-value").value,
  }));
}

async function loadCurrentAdmin() {
  try {
    const data = await apiRequest("/auth/me", { method: "GET" });
    usernameEl.textContent = data.admin.username;
  } catch (err) {
    window.location.href = "login.html";
  }
}

async function loadEnv() {
  setError(null);
  try {
    const data = await apiRequest(`/services/${serviceId}/env`, { method: "GET" });
    pageTitleEl.textContent = `.env — ${data.name}`;
    pathHintEl.textContent = data.path ? data.path : `${data.system_name}/.env`;
    renderRows(data.entries);
    originalKeys = new Set(data.entries.map((e) => e.key));
    loadingEl.classList.add("hidden");
    panelEl.classList.remove("hidden");
    updatePanelEl.classList.remove("hidden");
    await loadSeedPairs();
    scrollToHashTarget();
  } catch (err) {
    setError(err.message || "Failed to load environment file");
    loadingEl.classList.add("hidden");
  }
}

addFieldButton.addEventListener("click", () => {
  addRow("", "");
});

bodyEl.addEventListener("click", (event) => {
  const button = event.target.closest(".remove-row");
  if (!button) {
    return;
  }
  button.closest("tr").remove();
});

revealAllCheckbox.addEventListener("change", () => {
  const type = revealAllCheckbox.checked ? "text" : "password";
  bodyEl.querySelectorAll(".env-value").forEach((input) => {
    input.type = type;
  });
});

function validateRows(entries) {
  const keyPattern = /^[A-Za-z_][A-Za-z0-9_]*$/;
  const seen = new Set();
  for (const entry of entries) {
    if (!entry.key) {
      return "У одного из полей не заполнено имя.";
    }
    if (!keyPattern.test(entry.key)) {
      return `Некорректное имя переменной: ${entry.key}`;
    }
    if (seen.has(entry.key)) {
      return `Повторяющееся имя переменной: ${entry.key}`;
    }
    seen.add(entry.key);
    if (entry.value.includes("\n") || entry.value.includes("\r")) {
      return `Значение поля ${entry.key} не может содержать перенос строки.`;
    }
  }
  return null;
}

saveButton.addEventListener("click", async () => {
  setError(null);
  const entries = readRows();

  const validationError = validateRows(entries);
  if (validationError) {
    setError(validationError);
    return;
  }

  const newKeys = new Set(entries.map((e) => e.key));
  const removedKeys = [...originalKeys].filter((k) => !newKeys.has(k));
  if (removedKeys.length > 0) {
    const proceed = window.confirm(`Будут удалены переменные: ${removedKeys.join(", ")}. Продолжить?`);
    if (!proceed) {
      return;
    }
  }

  saveButton.disabled = true;
  try {
    const data = await apiRequest(`/services/${serviceId}/env`, {
      method: "POST",
      body: { entries },
    });
    renderRows(data.entries);
    originalKeys = new Set(data.entries.map((e) => e.key));
  } catch (err) {
    setError(err.message || "Failed to save environment file");
  } finally {
    saveButton.disabled = false;
  }
});

updateButton.addEventListener("click", async () => {
  setError(null);
  updateResultEl.textContent = "";
  const file = updateFileInput.files[0];
  if (!file) {
    setError("Выберите zip-файл для обновления.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  updateButton.disabled = true;
  updateResultEl.textContent = "Обновление…";
  try {
    const data = await apiUpload(`/services/${serviceId}/update`, formData);
    const parts = [];
    if (data.backend_updated) parts.push("backend обновлён");
    if (data.frontend_updated) parts.push("frontend собран и обновлён");
    if (data.backend_updated) {
      parts.push(data.restarted ? "служба перезапущена" : "перезапуск не удался — проверьте статус вручную");
    }
    updateResultEl.textContent = parts.join(", ") + ".";
    updateFileInput.value = "";
  } catch (err) {
    updateResultEl.textContent = "";
    setError(err.message || "Не удалось обновить файлы сервиса.");
  } finally {
    updateButton.disabled = false;
  }
});

// --- Seed (DB fill) panel -------------------------------------------

function pairLabel(pairKey) {
  return pairKey ? pairKey : "(по умолчанию)";
}

function seedDataIsDirty() {
  return seedDataEditor.value !== seedDataEditor.dataset.loaded;
}

async function loadSeedPairs() {
  try {
    const data = await apiRequest(`/services/${serviceId}/seed/pairs`, { method: "GET" });
    seedPanelEl.classList.remove("hidden");

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
  } catch (err) {
    setError(err.message || "Не удалось получить список seed-скриптов.");
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
  } catch (err) {
    setError(err.message || "Не удалось загрузить seed_data.");
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
  } catch (err) {
    setError(err.message || "Не удалось сохранить seed_data.");
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
  } catch (err) {
    seedRunOutputEl.classList.add("is-failure");
    seedRunOutputEl.textContent = err.message || "Не удалось выполнить запрос.";
  } finally {
    seedRunButton.disabled = false;
  }
});

logoutButton.addEventListener("click", async () => {
  setError(null);
  try {
    await apiRequest("/auth/logout", { method: "POST" });
    window.location.href = "login.html";
  } catch (err) {
    setError(err.message || "Logout failed");
  }
});

if (!serviceId) {
  setError("Не указан id сервиса.");
  loadingEl.classList.add("hidden");
} else {
  loadCurrentAdmin();
  loadEnv();
}
