const businessDemo = window.SHAVERMA_BUSINESS_DEMO;
const storeFilter = document.getElementById("business-store");
const periodButtons = [...document.querySelectorAll("[data-period]")];
const usernameEl = document.getElementById("current-username");
const logoutButton = document.getElementById("logout-button");
const mobileMenuButton = document.getElementById("mobile-menu-button");
const sidebarBackdrop = document.getElementById("sidebar-backdrop");

let selectedPeriod = "today";

function formatMoney(value) {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value) + " ₽";
}

function plural(value, one, few, many) {
  const mod10 = value % 10;
  const mod100 = value % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[character]));
}

function getPoint(pointId) {
  return businessDemo.points.find((point) => point.id === pointId);
}

function getVisibleData() {
  const period = businessDemo.periods[selectedPeriod];
  const selectedStore = storeFilter.value;
  const storeRows = selectedStore === "all"
    ? period.stores
    : period.stores.filter((row) => String(row.pointId) === selectedStore);
  const orders = storeRows.reduce((sum, row) => sum + row.orders, 0);
  const turnover = storeRows.reduce((sum, row) => sum + row.turnover, 0);
  const orderShare = period.metrics.orders ? orders / period.metrics.orders : 0;
  const deliveryRows = storeRows.filter((row) => getPoint(row.pointId)?.deliveryEnabled);
  const deliveryOrders = deliveryRows.reduce((sum, row) => sum + row.deliveryOrders, 0);
  const deliveryTurnover = deliveryRows.reduce((sum, row) => sum + row.deliveryTurnover, 0);
  const selected = selectedStore !== "all";

  return {
    period,
    storeRows,
    selected,
    metrics: {
      orders,
      turnover,
      active: Math.max(0, Math.round(period.metrics.active * orderShare)),
      averageCheck: orders ? Math.round(turnover / orders) : 0,
      cancelled: Math.round(period.metrics.cancelled * orderShare),
      tasks: Math.round(period.metrics.tasks * orderShare),
      storesOpen: storeRows.filter((row) => getPoint(row.pointId)?.active).length,
      deliveryOrders,
      deliveryTurnover,
      deliveryStores: deliveryRows.length,
    },
  };
}

function renderBars(trend, turnover) {
  const max = Math.max(...trend, 1);
  const total = trend.reduce((sum, item) => sum + item, 0) || 1;
  const chart = document.getElementById("turnover-bars");
  chart.innerHTML = trend.map((value) => {
    const height = Math.max(12, Math.round((value / max) * 100));
    const share = value / total;
    return `<span class="turnover-bar" style="height:${height}%" title="${formatMoney(Math.round(turnover * share))}"><i></i></span>`;
  }).join("");
}

function renderFlow(statuses, orderShare) {
  const total = statuses.reduce((sum, item) => sum + item.value, 0);
  const list = document.getElementById("order-flow-list");
  list.innerHTML = statuses.map((item) => {
    const value = Math.round(item.value * orderShare);
    return `<div class="order-flow-item ${item.tone}"><span><i></i>${escapeHtml(item.label)}</span><strong>${value}</strong><small>${total ? Math.round((item.value / total) * 100) : 0}%</small></div>`;
  }).join("");
}

function renderStores(rows) {
  const list = document.getElementById("business-store-list");
  const rankedRows = [...rows].sort((first, second) => second.turnover - first.turnover);
  const topTurnover = Math.max(...rankedRows.map((row) => row.turnover), 1);

  list.innerHTML = rankedRows.map((row, index) => {
    const point = getPoint(row.pointId);
    const rank = index + 1;
    const width = Math.max(5, Math.round((row.turnover / topTurnover) * 100));
    const deliveryValue = point.deliveryEnabled ? `${row.deliveryOrders} ${plural(row.deliveryOrders, "заказ", "заказа", "заказов")}` : "—";
    return `<article class="business-store-row">
      <div class="business-store-title">
        <span class="store-rank" aria-label="${rank}-е место">${String(rank).padStart(2, "0")}</span>
        <span class="service-avatar">${escapeHtml(point.name.slice(0, 1))}</span>
        <div class="business-store-copy"><strong>${escapeHtml(point.name)}</strong><small class="business-client">${escapeHtml(point.client)}</small><small>${escapeHtml(point.city)} · ${escapeHtml(point.address)}</small></div>
        <div class="store-state-group">${point.deliveryEnabled ? '<span class="delivery-state">Доставка</span>' : ""}<span class="store-state ${point.active ? "open" : "closed"}">${point.active ? "Открыт" : "Скрыт"}</span></div>
      </div>
      <div class="business-store-metrics"><div><span>Заказов</span><strong>${row.orders}</strong></div><div><span>Оборот</span><strong>${formatMoney(row.turnover)}</strong></div><div><span>Доставка</span><strong>${deliveryValue}</strong></div><div><span>Сотрудники</span><strong>${row.employees}</strong></div></div>
      <div class="store-turnover-track" aria-hidden="true"><span style="width:${width}%"></span></div>
    </article>`;
  }).join("");
}

function renderDeliveries(rows) {
  const list = document.getElementById("delivery-store-list");
  const enabledRows = rows
    .map((row) => ({ row, point: getPoint(row.pointId) }))
    .filter(({ point }) => point?.deliveryEnabled)
    .sort((first, second) => second.row.deliveryOrders - first.row.deliveryOrders);

  if (!enabledRows.length) {
    list.innerHTML = '<p class="delivery-empty">У выбранной точки доставка не подключена.</p>';
    return;
  }

  list.innerHTML = enabledRows.map(({ row, point }) => {
    const share = row.orders ? Math.round((row.deliveryOrders / row.orders) * 100) : 0;
    return `<article class="delivery-store-row"><div><strong>${escapeHtml(point.name)}</strong><small>${escapeHtml(point.client)} · ${share}% заказов</small></div><div class="delivery-store-values"><strong>${row.deliveryOrders}</strong><span>${formatMoney(row.deliveryTurnover)}</span></div></article>`;
  }).join("");
}

function render() {
  const { period, storeRows, metrics, selected } = getVisibleData();
  const share = period.metrics.orders ? metrics.orders / period.metrics.orders : 0;
  const periodCopy = selected ? "По выбранной точке клиента" : `За ${period.label.toLowerCase()}`;
  document.getElementById("metric-orders").textContent = metrics.orders;
  document.getElementById("metric-turnover").textContent = formatMoney(metrics.turnover);
  document.getElementById("metric-active-orders").textContent = metrics.active;
  document.getElementById("metric-average-check").textContent = formatMoney(metrics.averageCheck);
  document.getElementById("metric-orders-note").textContent = periodCopy;
  document.getElementById("metric-turnover-note").textContent = selected ? "Оборот выбранной точки" : "Не является нашей выручкой";
  document.getElementById("turnover-total").textContent = formatMoney(metrics.turnover);
  document.getElementById("active-flow-count").textContent = `${metrics.active} активных`;
  document.getElementById("attention-tasks").textContent = metrics.tasks;
  document.getElementById("attention-cancelled").textContent = metrics.cancelled;
  document.getElementById("stores-open-copy").textContent = `${metrics.storesOpen} ${plural(metrics.storesOpen, "открытая точка", "открытые точки", "открытых точек")}`;
  document.getElementById("delivery-orders").textContent = metrics.deliveryOrders;
  document.getElementById("delivery-turnover").textContent = formatMoney(metrics.deliveryTurnover);
  document.getElementById("delivery-stores-copy").textContent = `${metrics.deliveryStores} ${plural(metrics.deliveryStores, "точка", "точки", "точек")}`;
  renderBars(period.trend, metrics.turnover);
  renderFlow(period.statuses, share);
  renderStores(storeRows);
  renderDeliveries(storeRows);
}

function populateStores() {
  businessDemo.points.forEach((point) => {
    const option = document.createElement("option");
    option.value = point.id;
    option.textContent = `${point.name} · ${point.client}`;
    storeFilter.appendChild(option);
  });
}

function setSidebarOpen(open) {
  document.body.classList.toggle("sidebar-open", open);
  mobileMenuButton.setAttribute("aria-expanded", String(open));
}

periodButtons.forEach((button) => {
  button.addEventListener("click", () => {
    selectedPeriod = button.dataset.period;
    periodButtons.forEach((item) => item.classList.toggle("is-active", item === button));
    render();
  });
});

storeFilter.addEventListener("change", render);
mobileMenuButton.addEventListener("click", () => setSidebarOpen(!document.body.classList.contains("sidebar-open")));
sidebarBackdrop.addEventListener("click", () => setSidebarOpen(false));
document.addEventListener("keydown", (event) => { if (event.key === "Escape") setSidebarOpen(false); });

logoutButton.addEventListener("click", async () => {
  await apiRequest("/auth/logout", { method: "POST" });
  window.location.href = "login.html";
});

async function init() {
  if (!LOCAL_DEMO_MODE || !businessDemo) {
    document.querySelector(".business-main").innerHTML = "<div class=\"empty-state\"><h3>Бизнес-метрики пока не подключены</h3><p>Этот раздел доступен только в локальном mock-режиме до появления analytics API.</p></div>";
    return;
  }
  try {
    const data = await apiRequest("/auth/me", { method: "GET" });
    usernameEl.textContent = data.admin.username;
    document.querySelector(".avatar").textContent = data.admin.username.slice(0, 1).toUpperCase();
    populateStores();
    render();
  } catch (error) {
    window.location.href = "login.html";
  }
}

init();
