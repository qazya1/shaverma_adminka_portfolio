// The frontend is a fully independent static site -- it knows nothing
// about the backend's internals, only its base URL. Change this if the
// backend is not running on the default dev host/port from .env.example.
const API_BASE = "http://127.0.0.1:8100/api/v1";
const LOCAL_DEMO_MODE = window.SHAVERMA_LOCAL_DEMO === true;

function getCookie(name) {
  const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : null;
}

async function apiRequest(path, options = {}) {
  if (LOCAL_DEMO_MODE) {
    return window.localDemoApiRequest(path, options);
  }

  const headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});

  const csrfToken = getCookie("admin_csrf");
  if (csrfToken && options.method && options.method.toUpperCase() !== "GET") {
    headers["X-CSRF-Token"] = csrfToken;
  }

  const response = await fetch(API_BASE + path, {
    method: options.method || "GET",
    credentials: "include", // send/receive the HttpOnly session cookie
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    data = null;
  }

  if (!response.ok) {
    const message = (data && data.detail) || "Request failed";
    throw new Error(message);
  }

  return data;
}

// Separate from apiRequest because a file upload needs a raw FormData
// body and must NOT set Content-Type itself (the browser sets the
// multipart boundary) -- apiRequest always JSON-encodes its body.
async function apiUpload(path, formData) {
  if (LOCAL_DEMO_MODE) {
    return window.localDemoApiRequest(path, { method: "POST", body: formData });
  }

  const headers = {};
  const csrfToken = getCookie("admin_csrf");
  if (csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  const response = await fetch(API_BASE + path, {
    method: "POST",
    credentials: "include",
    headers,
    body: formData,
  });

  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    data = null;
  }

  if (!response.ok) {
    throw new Error((data && data.detail) || "Upload failed");
  }

  return data;
}
