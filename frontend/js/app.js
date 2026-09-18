const usernameEl = document.getElementById("current-username");
const logoutButton = document.getElementById("logout-button");
const refreshButton = document.getElementById("refresh-button");
const checkAllButton = document.getElementById("check-all-button");
const errorEl = document.getElementById("app-error");
const errorMessageEl = document.getElementById("app-error-message");
const errorRetryButton = document.getElementById("error-retry-button");

const loadingEl = document.getElementById("services-loading");
const emptyEl = document.getElementById("services-empty");
const emptyCopyEl = document.getElementById("services-empty-copy");
const tableWrapEl = document.getElementById("services-table-wrap");
const tbody = document.getElementById("services-body");
const mobileServicesList = document.getElementById("mobile-services-list");
const searchInput = document.getElementById("service-search");
const statusFilter = document.getElementById("status-filter");
const servicesCountEl = document.getElementById("services-count");

const metricTotalEl = document.getElementById("metric-total");
const metricActiveEl = document.getElementById("metric-active");
const metricInactiveEl = document.getElementById("metric-inactive");
const metricUncheckedEl = document.getElementById("metric-unchecked");

const distributionTotalEl = document.getElementById("distribution-total");
const distributionActiveBar = document.getElementById("distribution-active-bar");
const distributionInactiveBar = document.getElementById("distribution-inactive-bar");
const distributionActiveCount = document.getElementById("distribution-active-count");
const distributionInactiveCount = document.getElementById("distribution-inactive-count");
const validUnitsEl = document.getElementById("readiness-valid-units");
const checkedServicesEl = document.getElementById("readiness-checked");
const invalidUnitsEl = document.getElementById("readiness-invalid-units");

const mobileMenuButton = document.getElementById("mobile-menu-button");
const sidebarBackdrop = document.getElementById("sidebar-backdrop");
const actionDialog = document.getElementById("action-dialog");
const dialogTitle = document.getElementById("dialog-title");
const dialogCopy = document.getElementById("dialog-copy");

let servicesCache = [];

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML.replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function setError(message) {
  if (!message) {
    errorEl.classList.add("hidden");
    errorMessageEl.textContent = "";
    return;
  }
  errorMessageEl.textContent = message;
  errorEl.classList.remove("hidden");
}

function setRefreshLoading(loading) {
  refreshButton.disabled = loading;
  refreshButton.classList.toggle("is-loading", loading);
}

function getServiceState(service) {
  const live = service.status;
  if (!live) {
    return {
      key: service.is_active ? "active" : "inactive",
      label: service.is_active ? "Активен" : "Остановлен",
      tone: service.is_active ? "success" : "neutral",
      hint: "По данным БД · не проверено",
      running: service.is_active,
    };
  }
  if (!live.exists) {
    return { key: "missing", label: "Юнит не найден", tone: "danger", hint: "Проверено сейчас", running: false };
  }
  if (live.active_state === "active") {
    return { key: "active", label: "Работает", tone: "success", hint: live.sub_state || "running", running: true };
  }
  if (live.active_state === "failed") {
    return { key: "failed", label: "Ошибка", tone: "danger", hint: live.sub_state || "failed", running: false };
  }
  return {
    key: "inactive",
    label: "Остановлен",
    tone: "neutral",
    hint: live.sub_state || live.active_state || "Проверено сейчас",
    running: false,
  };
}

function pluralizeServices(count) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} сервис`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} сервиса`;
  return `${count} сервисов`;
}

function updateDashboardMetrics(services) {
  const states = services.map(getServiceState);
  const total = services.length;
  const active = states.filter((state) => state.running).length;
  const inactive = total - active;
  const unchecked = services.filter((service) => !service.status).length;
  const validUnits = services.filter((service) => Boolean(service.unit_name)).length;
  const checked = total - unchecked;

  [metricTotalEl, metricActiveEl, metricInactiveEl, metricUncheckedEl].forEach((element) => {
    element.classList.remove("skeleton-text");
  });
  metricTotalEl.textContent = total;
  metricActiveEl.textContent = active;
  metricInactiveEl.textContent = inactive;
  metricUncheckedEl.textContent = unchecked;

  distributionTotalEl.textContent = pluralizeServices(total);
  distributionActiveCount.textContent = active;
  distributionInactiveCount.textContent = inactive;
  const activePercent = total ? (active / total) * 100 : 0;
  distributionActiveBar.style.width = `${activePercent}%`;
  distributionInactiveBar.style.width = `${100 - activePercent}%`;

  validUnitsEl.textContent = `${validUnits} / ${total}`;
  checkedServicesEl.textContent = `${checked} / ${total}`;
  invalidUnitsEl.textContent = total - validUnits;
}

function statusChip(state) {
  return `<span class="status-chip ${state.tone}"><span class="status-dot" aria-hidden="true"></span>${escapeHtml(state.label)}</span>`;
}

function matchesFilters(service) {
  const query = searchInput.value.trim().toLocaleLowerCase("ru");
  const selectedStatus = statusFilter.value;
  const state = getServiceState(service);
  const searchable = `${service.name} ${service.system_name} ${service.unit_name || ""}`.toLocaleLowerCase("ru");
  const matchesQuery = !query || searchable.includes(query);
  const matchesStatus = selectedStatus === "all"
    || (selectedStatus === "unchecked" ? !service.status : state.key === selectedStatus);
  return matchesQuery && matchesStatus;
}

function closeOtherMenus(currentDetails) {
  document.querySelectorAll("details.action-menu[open]").forEach((details) => {
    if (details !== currentDetails) details.removeAttribute("open");
  });
}

function getPrimaryServiceAction(state, hasUnit) {
  if (!hasUnit) return { action: "check-status", label: "Проверить", tone: "secondary", icon: "refresh", disabled: true };
  if (state.running) return { action: "stop", label: "Остановить", tone: "danger", icon: "power", disabled: false };
  return { action: "start", label: "Запустить", tone: "primary", icon: "power", disabled: false };
}

function renderServices() {
  const filtered = servicesCache.filter(matchesFilters);
  tbody.innerHTML = "";
  mobileServicesList.innerHTML = "";
  servicesCountEl.textContent = filtered.length === servicesCache.length
    ? String(servicesCache.length)
    : `${filtered.length} из ${servicesCache.length}`;

  if (filtered.length === 0) {
    emptyCopyEl.textContent = servicesCache.length
      ? "По выбранным фильтрам ничего не найдено. Измените запрос или состояние."
      : "Создайте первый сервис, чтобы начать управление.";
    emptyEl.classList.remove("hidden");
    tableWrapEl.classList.add("hidden");
    mobileServicesList.classList.add("hidden");
    return;
  }

  emptyEl.classList.add("hidden");
  tableWrapEl.classList.remove("hidden");
  mobileServicesList.classList.remove("hidden");

  for (const service of filtered) {
    const state = getServiceState(service);
    const hasUnit = service.unit_name != null;
    const primaryAction = getPrimaryServiceAction(state, hasUnit);
    const tr = document.createElement("tr");
    tr.dataset.serviceId = service.id;
    tr.innerHTML = `
      <td>
        <div class="service-identity">
          <span class="service-avatar">${escapeHtml(service.name.slice(0, 1).toUpperCase())}</span>
          <span><strong>${escapeHtml(service.name)}</strong><small>ID ${service.id}</small></span>
        </div>
      </td>
      <td><code class="technical-value">${escapeHtml(service.system_name)}</code></td>
      <td>${hasUnit
        ? `<span class="unit-value">${iconSvg("server", "icon icon-small")}<code>${escapeHtml(service.unit_name)}</code></span>`
        : `<span class="inline-warning">${iconSvg("alert", "icon icon-small")}Невалидный system_name</span>`}</td>
      <td>
        <div class="status-cell">${statusChip(state)}<small>${escapeHtml(state.hint)}</small></div>
      </td>
      <td class="action-cell">
        <button type="button" class="icon-button" data-id="${service.id}" data-action="check-status" title="Проверить статус" aria-label="Проверить статус: ${escapeHtml(service.name)}" ${hasUnit ? "" : "disabled"}>${iconSvg("refresh", "icon icon-small")}</button>
        ${hasUnit
          ? `<button type="button" class="icon-button ${primaryAction.tone === "primary" ? "tone-start" : "tone-stop"}" data-id="${service.id}" data-action="${primaryAction.action}" title="${escapeHtml(primaryAction.label)}" aria-label="${escapeHtml(primaryAction.label)}: ${escapeHtml(service.name)}">${iconSvg(primaryAction.icon, "icon icon-small")}</button>`
          : ""}
        <details class="action-menu">
          <summary class="icon-button" aria-label="Файлы и БД сервиса ${escapeHtml(service.name)}">${iconSvg("more")}</summary>
          <div class="action-menu-popover">
            <a href="service-env.html?id=${encodeURIComponent(service.id)}#env-panel">${iconSvg("file", "icon icon-small")}Редактировать .env</a>
            <a href="service-env.html?id=${encodeURIComponent(service.id)}#update-panel">${iconSvg("upload", "icon icon-small")}Обновить файлы</a>
            <a href="service-env.html?id=${encodeURIComponent(service.id)}#seed-panel">${iconSvg("database", "icon icon-small")}Заполнение БД</a>
          </div>
        </details>
      </td>`;
    tbody.appendChild(tr);

    const card = document.createElement("article");
    card.className = "mobile-service-card";
    card.dataset.serviceId = service.id;
    card.innerHTML = `
      <div class="mobile-service-card-top">
        <div class="service-identity">
          <span class="service-avatar">${escapeHtml(service.name.slice(0, 1).toUpperCase())}</span>
          <span><strong>${escapeHtml(service.name)}</strong><small>ID ${service.id}</small></span>
        </div>
        <div class="mobile-service-status">${statusChip(state)}<small>${escapeHtml(state.hint)}</small></div>
      </div>
      <div class="mobile-service-keys">
        <div><span>System name</span><code>${escapeHtml(service.system_name)}</code></div>
        <div><span>Systemd-юнит</span>${hasUnit
          ? `<code>${escapeHtml(service.unit_name)}</code>`
          : `<strong class="inline-warning">${iconSvg("alert", "icon icon-small")}Невалидный system_name</strong>`}</div>
      </div>
      <div class="mobile-service-actions">
        <button class="button ghost" type="button" data-id="${service.id}" data-action="check-status" title="Проверить статус" ${hasUnit ? "" : "disabled"}>${iconSvg("refresh", "icon icon-small")}</button>
        ${hasUnit
          ? `<button class="button ${primaryAction.tone}" type="button" data-id="${service.id}" data-action="${primaryAction.action}">${iconSvg(primaryAction.icon, "icon icon-small")}${primaryAction.label}</button>`
          : ""}
      </div>
      <details class="mobile-service-details">
        <summary>Файлы и БД ${iconSvg("chevronDown", "icon icon-small")}</summary>
        <div class="mobile-service-details-content">
          <a class="button ghost" href="service-env.html?id=${encodeURIComponent(service.id)}#env-panel">${iconSvg("file", "icon icon-small")}Редактировать .env</a>
          <a class="button ghost" href="service-env.html?id=${encodeURIComponent(service.id)}#update-panel">${iconSvg("upload", "icon icon-small")}Обновить файлы</a>
          <a class="button ghost" href="service-env.html?id=${encodeURIComponent(service.id)}#seed-panel">${iconSvg("database", "icon icon-small")}Заполнение БД</a>
        </div>
      </details>`;
    mobileServicesList.appendChild(card);
  }

  document.querySelectorAll("details.action-menu").forEach((details) => {
    details.addEventListener("toggle", () => {
      if (details.open) closeOtherMenus(details);
    });
  });
}

function showStopConfirmation(service) {
  dialogTitle.textContent = `Остановить «${service.name}»?`;
  dialogCopy.textContent = `${service.unit_name || service.system_name} перестанет отвечать до следующего запуска.`;
  actionDialog.returnValue = "cancel";
  actionDialog.showModal();
  return new Promise((resolve) => {
    actionDialog.addEventListener("close", () => resolve(actionDialog.returnValue === "confirm"), { once: true });
  });
}

async function loadCurrentAdmin() {
  try {
    const data = await apiRequest("/auth/me", { method: "GET" });
    usernameEl.textContent = data.admin.username;
    document.querySelector(".avatar").textContent = data.admin.username.slice(0, 1).toUpperCase();
  } catch (error) {
    window.location.href = "login.html";
  }
}

async function loadServices() {
  setError(null);
  setRefreshLoading(true);
  loadingEl.classList.remove("hidden");
  emptyEl.classList.add("hidden");
  tableWrapEl.classList.add("hidden");
  mobileServicesList.classList.add("hidden");
  try {
    servicesCache = await apiRequest("/services", { method: "GET" });
    updateDashboardMetrics(servicesCache);
    renderServices();
  } catch (error) {
    setError(error.message || "Не удалось получить список сервисов. Проверьте соединение и повторите попытку.");
  } finally {
    loadingEl.classList.add("hidden");
    setRefreshLoading(false);
  }
}

async function runServiceAction(serviceId, action, trigger) {
  const service = servicesCache.find((item) => String(item.id) === String(serviceId));
  if (!service) return;

  if (action === "stop" && !(await showStopConfirmation(service))) return;

  setError(null);
  const row = trigger.closest("tr, .mobile-service-card");
  const rowButtons = row ? row.querySelectorAll("button, summary, a") : [];
  rowButtons.forEach((element) => element.setAttribute("aria-disabled", "true"));
  trigger.disabled = true;
  trigger.classList.add("is-loading");

  try {
    const updated = await apiRequest(`/services/${serviceId}/${action}`, { method: "POST" });
    const index = servicesCache.findIndex((item) => String(item.id) === String(serviceId));
    if (index !== -1) servicesCache[index] = updated;
    updateDashboardMetrics(servicesCache);
    renderServices();
  } catch (error) {
    setError(error.message || `Не удалось выполнить действие «${action}».`);
    rowButtons.forEach((element) => element.removeAttribute("aria-disabled"));
    trigger.disabled = false;
    trigger.classList.remove("is-loading");
  }
}

async function checkAllServices() {
  const targets = servicesCache.filter((service) => service.unit_name != null).map((service) => service.id);
  if (targets.length === 0) return;

  setError(null);
  checkAllButton.disabled = true;
  checkAllButton.classList.add("is-loading");
  try {
    // All in parallel, not one-by-one -- an admin-triggered, infrequent
    // action, not something worth a sequential wait for a handful (or a
    // few dozen) services. Promise.allSettled so one failing service
    // never stops the rest from being checked and reflected.
    const results = await Promise.allSettled(
      targets.map((id) => apiRequest(`/services/${id}/check-status`, { method: "POST" }))
    );

    let failed = 0;
    results.forEach((result, index) => {
      if (result.status === "fulfilled") {
        const cacheIndex = servicesCache.findIndex((item) => String(item.id) === String(targets[index]));
        if (cacheIndex !== -1) servicesCache[cacheIndex] = result.value;
      } else {
        failed += 1;
      }
    });

    updateDashboardMetrics(servicesCache);
    renderServices();
    if (failed > 0) {
      setError(`Не удалось проверить статус ${failed} из ${targets.length} сервисов.`);
    }
  } catch (error) {
    setError(error.message || "Не удалось проверить статус служб.");
  } finally {
    checkAllButton.disabled = false;
    checkAllButton.classList.remove("is-loading");
  }
}

function setSidebarOpen(open) {
  document.body.classList.toggle("sidebar-open", open);
  mobileMenuButton.setAttribute("aria-expanded", String(open));
}

logoutButton.addEventListener("click", async () => {
  setError(null);
  try {
    await apiRequest("/auth/logout", { method: "POST" });
    window.location.href = "login.html";
  } catch (error) {
    setError(error.message || "Не удалось завершить сессию.");
  }
});

tbody.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || button.disabled) return;
  const details = button.closest("details");
  if (details) details.removeAttribute("open");
  runServiceAction(button.dataset.id, button.dataset.action, button);
});

mobileServicesList.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || button.disabled) return;
  const details = button.closest("details");
  if (details) details.removeAttribute("open");
  runServiceAction(button.dataset.id, button.dataset.action, button);
});

searchInput.addEventListener("input", renderServices);
statusFilter.addEventListener("change", renderServices);
refreshButton.addEventListener("click", loadServices);
checkAllButton.addEventListener("click", checkAllServices);
errorRetryButton.addEventListener("click", loadServices);
mobileMenuButton.addEventListener("click", () => setSidebarOpen(!document.body.classList.contains("sidebar-open")));
sidebarBackdrop.addEventListener("click", () => setSidebarOpen(false));
document.addEventListener("click", (event) => {
  if (!event.target.closest("details.action-menu")) closeOtherMenus(null);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setSidebarOpen(false);
});

document.getElementById("environment-label").textContent = LOCAL_DEMO_MODE ? "Локальный mock" : "Рабочий контур";
loadCurrentAdmin();
loadServices();
