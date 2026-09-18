(function () {
  "use strict";

  const isLocalHost = ["127.0.0.1", "localhost"].includes(window.location.hostname);
  window.SHAVERMA_LOCAL_DEMO = isLocalHost;

  if (!isLocalHost) {
    return;
  }

  const AUTH_KEY = "shaverma-adminka-local-auth";
  const DATA_KEY = "shaverma-adminka-local-data-v2";

  const emptyProvisionStatus = () => ({
    dirs: { done: false },
    backend_uploaded: { done: false },
    env_generated: { done: false },
    frontend_built: { done: false },
    nginx: { done: false },
    systemd: { done: false },
  });

  const defaultData = () => ({
    nextId: 6,
    services: [
      {
        id: 1,
        name: "Шаверма на Центральной",
        system_name: "shaverma_central",
        unit_name: "shaverma_central-backend.service",
        is_active: true,
        status: null,
      },
      {
        id: 2,
        name: "Шаверма Индия",
        system_name: "shaverma_india",
        unit_name: "shaverma_india-backend.service",
        is_active: false,
        status: null,
      },
      {
        id: 3,
        name: "Гриль на Лесной",
        system_name: "shaverma_lesnaya",
        unit_name: "shaverma_lesnaya-backend.service",
        is_active: true,
        status: null,
      },
      {
        id: 4,
        name: "Ночной проспект",
        system_name: "shaverma_night",
        unit_name: "shaverma_night-backend.service",
        is_active: false,
        status: null,
      },
      {
        id: 5,
        name: "Тестовый контур",
        system_name: "shaverma_test",
        unit_name: "shaverma_test-backend.service",
        is_active: true,
        status: null,
      },
    ],
    environments: {
      1: [
        { key: "APP_ENV", value: "production" },
        { key: "APP_PORT", value: "8001" },
        { key: "DATABASE_URL", value: "mysql+pymysql://central:demo@127.0.0.1/central" },
        { key: "TELEGRAM_BOT_TOKEN", value: "local-demo-token" },
      ],
      2: [
        { key: "APP_ENV", value: "production" },
        { key: "APP_PORT", value: "8002" },
        { key: "DATABASE_URL", value: "mysql+pymysql://india:demo@127.0.0.1/india" },
      ],
      3: [
        { key: "APP_ENV", value: "production" },
        { key: "APP_PORT", value: "8003" },
        { key: "DATABASE_URL", value: "mysql+pymysql://lesnaya:demo@127.0.0.1/lesnaya" },
      ],
      4: [
        { key: "APP_ENV", value: "production" },
        { key: "APP_PORT", value: "8004" },
        { key: "DATABASE_URL", value: "mysql+pymysql://night:demo@127.0.0.1/night" },
      ],
      5: [
        { key: "APP_ENV", value: "development" },
        { key: "APP_PORT", value: "8005" },
        { key: "DEBUG", value: "true" },
      ],
    },
    provisioning: {
      1: {
        dirs: { done: true },
        backend_uploaded: { done: true },
        env_generated: { done: true },
        frontend_built: { done: true },
        nginx: { done: true },
        systemd: { done: true },
      },
      2: emptyProvisionStatus(),
      3: {
        dirs: { done: true },
        backend_uploaded: { done: true },
        env_generated: { done: true },
        frontend_built: { done: true },
        nginx: { done: true },
        systemd: { done: true },
      },
      4: emptyProvisionStatus(),
      5: emptyProvisionStatus(),
    },
  });

  function loadData() {
    try {
      const saved = JSON.parse(localStorage.getItem(DATA_KEY));
      if (saved && Array.isArray(saved.services)) {
        return saved;
      }
    } catch (error) {
      console.warn("Не удалось прочитать локальные демо-данные", error);
    }

    const data = defaultData();
    localStorage.setItem(DATA_KEY, JSON.stringify(data));
    return data;
  }

  function saveData(data) {
    localStorage.setItem(DATA_KEY, JSON.stringify(data));
  }

  function requireAuth() {
    if (sessionStorage.getItem(AUTH_KEY) !== "1") {
      throw new Error("Требуется локальный вход");
    }
  }

  function getService(data, id) {
    const service = data.services.find((item) => String(item.id) === String(id));
    if (!service) {
      throw new Error("Сервис не найден");
    }
    return service;
  }

  function activeStatus(active) {
    return {
      exists: true,
      load_state: "loaded",
      active_state: active ? "active" : "inactive",
      sub_state: active ? "running" : "dead",
      unit_file_state: "enabled",
    };
  }

  function provisionStatus(data, id) {
    if (!data.provisioning[id]) {
      data.provisioning[id] = emptyProvisionStatus();
    }
    return data.provisioning[id];
  }

  async function localDemoRequest(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const body = options.body || {};

    await new Promise((resolve) => window.setTimeout(resolve, 120));

    if (path === "/auth/login/start" && method === "POST") {
      if (String(body.username) !== "1" || String(body.password) !== "1") {
        throw new Error("Неверные данные. Для локального входа используйте логин 1 и пароль 1.");
      }
      sessionStorage.setItem(AUTH_KEY, "1");
      return { local_demo: true };
    }

    if (path === "/auth/login/verify" && method === "POST") {
      sessionStorage.setItem(AUTH_KEY, "1");
      return { admin: { id: 1, username: "1", last_login_at: new Date().toISOString() } };
    }

    if (path === "/auth/logout" && method === "POST") {
      sessionStorage.removeItem(AUTH_KEY);
      return { detail: "logged out" };
    }

    requireAuth();

    if (path === "/auth/me" && method === "GET") {
      return { admin: { id: 1, username: "1", last_login_at: new Date().toISOString() } };
    }

    const data = loadData();

    if (path === "/services" && method === "GET") {
      return data.services;
    }

    if (path === "/services" && method === "POST") {
      const id = data.nextId++;
      const service = {
        id,
        name: body.name,
        system_name: body.system_name,
        unit_name: `${body.system_name}-backend.service`,
        is_active: Boolean(body.is_active),
        status: null,
      };
      data.services.push(service);
      data.environments[id] = [
        { key: "APP_ENV", value: "production" },
        { key: "SERVICE_NAME", value: body.system_name },
      ];
      data.provisioning[id] = emptyProvisionStatus();
      saveData(data);
      return {
        id,
        name: service.name,
        system_name: service.system_name,
        url: `https://${body.label}.example-service.рф`,
        backend_base_url: `https://${body.label}.example-service.рф/api`,
        is_active: service.is_active,
      };
    }

    let match = path.match(/^\/services\/(\d+)\/(start|stop|check-status)$/);
    if (match && method === "POST") {
      const service = getService(data, match[1]);
      if (match[2] === "start") service.is_active = true;
      if (match[2] === "stop") service.is_active = false;
      service.status = activeStatus(service.is_active);
      saveData(data);
      return service;
    }

    match = path.match(/^\/services\/(\d+)\/env$/);
    if (match) {
      const service = getService(data, match[1]);
      if (method === "POST") {
        data.environments[service.id] = Array.isArray(body.entries) ? body.entries : [];
        saveData(data);
      }
      const entries = data.environments[service.id] || [];
      return {
        service_id: service.id,
        name: service.name,
        system_name: service.system_name,
        path: `/opt/shaverma-instances/${service.system_name}/.env`,
        entries,
      };
    }

    match = path.match(/^\/services\/(\d+)\/provision\/status$/);
    if (match && method === "GET") {
      getService(data, match[1]);
      return provisionStatus(data, match[1]);
    }

    match = path.match(/^\/services\/(\d+)\/provision\/(dirs|upload|env|frontend|nginx|systemd)$/);
    if (match && method === "POST") {
      const service = getService(data, match[1]);
      const status = provisionStatus(data, service.id);
      const statusKey = {
        dirs: "dirs",
        upload: "backend_uploaded",
        env: "env_generated",
        frontend: "frontend_built",
        nginx: "nginx",
        systemd: "systemd",
      }[match[2]];
      status[statusKey] = { done: true };

      if (match[2] === "env") {
        data.environments[service.id] = [
          { key: "APP_ENV", value: "production" },
          { key: "DATABASE_URL", value: `mysql+pymysql://${body.database_user}:local-demo@127.0.0.1/${body.database_name}` },
          { key: "YOOKASSA_RECURRING_PAYMENTS_ENABLED", value: String(Boolean(body.yookassa_recurring_payments_enabled)) },
          {
            key: "TELEGRAM_WEB_APP_LOCAL_SDK_ENABLED",
            value: String(body.telegram_web_app_local_sdk_enabled !== false),
          },
        ];
      }

      if (match[2] === "systemd") {
        service.is_active = true;
        service.status = activeStatus(true);
      }

      saveData(data);
      if (match[2] === "nginx") return { port: 8000 + Number(service.id) };
      if (match[2] === "env") return { entries: data.environments[service.id] };
      return { detail: "Локальный демо-шаг выполнен" };
    }

    match = path.match(/^\/services\/(\d+)\/seed\/pairs$/);
    if (match && method === "GET") {
      // The demo never has real seed scripts on disk -- an empty list is
      // the accurate answer, not a limitation of the mock.
      return { pairs: [] };
    }

    throw new Error(`Локальный mock API не поддерживает: ${method} ${path}`);
  }

  window.localDemoApiRequest = localDemoRequest;
})();
