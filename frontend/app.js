const state = {
  token: localStorage.getItem("token") || null,
  currentUser: null,
  sessions: [],
  currentSession: null,
  ws: null,
  lockedFields: new Map(),
  lockOwner: null,
};

function log(message) {
  const el = document.getElementById("log");
  el.textContent = `[${new Date().toLocaleTimeString()}] ${message}\n${el.textContent}`.slice(0, 9000);
}

function authHeaders() {
  return state.token ? { Authorization: `Bearer ${state.token}` } : {};
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      // keep default
    }
    throw new Error(detail);
  }
  if (res.headers.get("content-type")?.includes("application/json")) {
    return res.json();
  }
  return res;
}

function setAuthStatus(text) {
  document.getElementById("auth-status").textContent = text;
}

async function refreshMe() {
  if (!state.token) {
    setAuthStatus("Not logged in");
    return;
  }
  try {
    const me = await api("/api/auth/me");
    state.currentUser = me;
    setAuthStatus(`Logged in as ${me.email}`);
  } catch (err) {
    state.token = null;
    localStorage.removeItem("token");
    setAuthStatus("Not logged in");
    log(`Auth reset: ${err.message}`);
  }
}

async function handleRegister(event) {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email: form.get("email"),
        password: form.get("password"),
      }),
    });
    log("Registration successful. You can login now.");
  } catch (err) {
    log(`Register failed: ${err.message}`);
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: form.get("email"),
        password: form.get("password"),
      }),
    });
    state.token = data.access_token;
    localStorage.setItem("token", state.token);
    await refreshMe();
    await refreshTemplates();
    await refreshSessions();
    log("Login successful.");
  } catch (err) {
    log(`Login failed: ${err.message}`);
  }
}

async function handleCreateTemplate(event) {
  event.preventDefault();
  if (!state.token) {
    log("Login required to create templates.");
    return;
  }
  const formData = new FormData(event.target);
  formData.set("schema_json", formData.get("schema"));
  formData.delete("schema");
  try {
    await api("/api/templates", {
      method: "POST",
      body: formData,
    });
    log("Template created.");
    await refreshTemplates();
  } catch (err) {
    log(`Template creation failed: ${err.message}`);
  }
}

async function refreshTemplates() {
  const list = document.getElementById("template-list");
  list.innerHTML = "";
  if (!state.token) {
    list.innerHTML = "<li>Login to list templates.</li>";
    return;
  }
  try {
    const templates = await api("/api/templates");
    for (const template of templates) {
      const li = document.createElement("li");
      const createBtn = document.createElement("button");
      createBtn.textContent = "Create Session";
      createBtn.className = "secondary";
      createBtn.onclick = async () => {
        const name = window.prompt("Session name", `${template.name} session`);
        if (!name) return;
        try {
          await api(`/api/templates/${template.id}/sessions`, {
            method: "POST",
            body: JSON.stringify({ name }),
          });
          log(`Session created from template ${template.name}.`);
          await refreshSessions();
        } catch (err) {
          log(`Session creation failed: ${err.message}`);
        }
      };
      li.textContent = `#${template.id} ${template.name} (${template.schema_json.length} mapping rules) `;
      li.appendChild(createBtn);
      list.appendChild(li);
    }
    if (!templates.length) list.innerHTML = "<li>No templates yet.</li>";
  } catch (err) {
    log(`Failed to load templates: ${err.message}`);
  }
}

async function refreshSessions() {
  const list = document.getElementById("session-list");
  list.innerHTML = "";
  if (!state.token) {
    list.innerHTML = "<li>Login to list sessions.</li>";
    return;
  }
  try {
    const sessions = await api("/api/sessions");
    state.sessions = sessions;
    for (const session of sessions) {
      const li = document.createElement("li");
      const openBtn = document.createElement("button");
      openBtn.textContent = "Open";
      openBtn.onclick = () => openAuthenticatedSession(session.id);

      const copyBtn = document.createElement("button");
      copyBtn.textContent = "Copy Share Link";
      copyBtn.className = "secondary";
      copyBtn.onclick = async () => {
        const url = `${window.location.origin}/?share=${session.share_token}`;
        await navigator.clipboard.writeText(url);
        log(`Copied share link: ${url}`);
      };

      li.textContent = `#${session.id} ${session.name} (expires ${new Date(session.expires_at).toLocaleString()}) `;
      li.appendChild(openBtn);
      li.appendChild(copyBtn);
      list.appendChild(li);
    }
    if (!sessions.length) list.innerHTML = "<li>No sessions yet.</li>";
  } catch (err) {
    log(`Failed to load sessions: ${err.message}`);
  }
}

function closeSocket() {
  if (state.ws) {
    state.ws.close();
    state.ws = null;
  }
}

function connectLockSocket({ sessionId, shareToken, guestName }) {
  closeSocket();
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  let path;
  if (shareToken) {
    const encodedName = encodeURIComponent(guestName || "guest");
    path = `/ws/locks/public/${shareToken}?name=${encodedName}`;
    state.lockOwner = `guest:${guestName || "guest"}`;
  } else {
    path = `/ws/locks/sessions/${sessionId}?token=${encodeURIComponent(state.token)}`;
    state.lockOwner = state.currentUser ? `user:${state.currentUser.id}` : "user:unknown";
  }
  state.ws = new WebSocket(`${protocol}://${window.location.host}${path}`);
  state.ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "lock" && msg.ok === false) {
        const input = document.querySelector(`[data-field="${CSS.escape(msg.field)}"]`);
        if (input) {
          input.classList.add("locked");
          input.disabled = true;
          log(`Field ${msg.field} is locked by another editor.`);
        }
      }
    } catch {
      // ignore malformed messages
    }
  };
}

function renderEditor(formData, isPublic, shareToken = null, guestName = "guest") {
  state.currentSession = {
    id: formData.session_id,
    shareToken,
    isPublic,
    fields: formData.fields,
  };
  document.getElementById("editor-meta").textContent = `Session: ${formData.session_name} | fields: ${formData.fields.length} | mode: ${isPublic ? "public-link" : "account"}`;
  const form = document.getElementById("editor-form");
  form.innerHTML = "";

  connectLockSocket({ sessionId: formData.session_id, shareToken, guestName });

  for (const field of formData.fields) {
    const wrapper = document.createElement("div");
    wrapper.className = "field-row";
    const label = document.createElement("label");
    label.textContent = `${field.label} (${field.key}, ${field.type})`;

    const input = document.createElement("input");
    input.dataset.field = field.key;
    input.value = field.value ?? "";
    if (field.type === "date") input.type = "date";
    else if (field.type === "number") input.type = "number";
    else input.type = "text";

    if (field.type === "boolean") {
      const select = document.createElement("select");
      select.dataset.field = field.key;
      [
        ["", "(empty)"],
        ["true", "true"],
        ["false", "false"],
      ].forEach(([v, t]) => {
        const option = document.createElement("option");
        option.value = v;
        option.textContent = t;
        if (String(field.value).toLowerCase() === v) option.selected = true;
        select.appendChild(option);
      });
      select.addEventListener("focus", () => tryLock(select.dataset.field));
      select.addEventListener("blur", () => releaseLock(select.dataset.field));
      wrapper.appendChild(label);
      wrapper.appendChild(select);
      form.appendChild(wrapper);
      continue;
    }

    input.addEventListener("focus", () => tryLock(input.dataset.field));
    input.addEventListener("blur", () => releaseLock(input.dataset.field));
    wrapper.appendChild(label);
    wrapper.appendChild(input);
    form.appendChild(wrapper);
  }
}

function sendLockMessage(payload) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
  state.ws.send(JSON.stringify(payload));
}

function tryLock(fieldKey) {
  sendLockMessage({ action: "lock", field: fieldKey });
}

function releaseLock(fieldKey) {
  sendLockMessage({ action: "unlock", field: fieldKey });
}

async function openAuthenticatedSession(sessionId) {
  if (!state.token) {
    log("Login required.");
    return;
  }
  try {
    const data = await api(`/api/sessions/${sessionId}/form`);
    renderEditor(data, false);
    log(`Opened session ${sessionId}.`);
  } catch (err) {
    log(`Failed to open session: ${err.message}`);
  }
}

async function openPublicSession(shareToken, guestName = "guest") {
  try {
    const data = await api(`/api/public/sessions/${shareToken}`);
    renderEditor(data, true, shareToken, guestName);
    log(`Opened public session via token ${shareToken}.`);
  } catch (err) {
    log(`Failed to open public session: ${err.message}`);
  }
}

async function saveCurrentSession() {
  if (!state.currentSession) {
    log("No session opened.");
    return;
  }
  const fields = Array.from(document.querySelectorAll("[data-field]"));
  const payload = { values: {} };
  for (const field of fields) {
    payload.values[field.dataset.field] = field.value;
  }
  try {
    if (state.currentSession.isPublic) {
      await api(`/api/public/sessions/${state.currentSession.shareToken}/update`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    } else {
      await api(`/api/sessions/${state.currentSession.id}/update`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    log("Session saved.");
  } catch (err) {
    log(`Save failed: ${err.message}`);
  }
}

function downloadCurrentSession() {
  if (!state.currentSession || state.currentSession.isPublic) {
    log("Download requires authenticated session editor.");
    return;
  }
  window.open(`/api/sessions/${state.currentSession.id}/download`, "_blank");
}

function bindEvents() {
  document.getElementById("register-form").addEventListener("submit", handleRegister);
  document.getElementById("login-form").addEventListener("submit", handleLogin);
  document.getElementById("template-form").addEventListener("submit", handleCreateTemplate);
  document.getElementById("refresh-templates").addEventListener("click", refreshTemplates);
  document.getElementById("refresh-sessions").addEventListener("click", refreshSessions);
  document.getElementById("save-session").addEventListener("click", saveCurrentSession);
  document.getElementById("download-session").addEventListener("click", downloadCurrentSession);
  document.getElementById("public-open-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    const token = String(form.get("shareToken") || "").trim();
    const guestName = String(form.get("guestName") || "guest").trim();
    if (!token) return;
    await openPublicSession(token, guestName || "guest");
  });
}

async function init() {
  bindEvents();
  await refreshMe();
  await refreshTemplates();
  await refreshSessions();
  const share = new URL(window.location.href).searchParams.get("share");
  if (share) {
    await openPublicSession(share, "guest");
  }
}

init();
