// ArenaHub test client: plain JavaScript, no framework, served by FastAPI (same origin).
"use strict";

// ---------- State (kept in memory only) ----------
const state = {
  token: null,           // access token from POST /auth/login
  me: null,              // GET /auth/me
  fields: [],            // GET /fields
  bookings: new Map(),   // booking id -> booking, for this session
  pending: {},           // operation -> { fingerprint, key }: Idempotency-Keys awaiting an answer
};

const $ = (id) => document.getElementById(id);

// ---------- Helpers ----------
const pad = (n, len = 2) => String(n).padStart(len, "0");

function newIdempotencyKey() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}

// "2026-11-15T20:00" (from a datetime-local input) -> "2026-11-15T20:00:00-05:00"
function toOffsetTimestamp(localValue) {
  if (!localValue) return null;
  const d = new Date(localValue);
  if (Number.isNaN(d.getTime())) return null;
  const offset = -d.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const abs = Math.abs(offset);
  return `${pad(d.getFullYear(), 4)}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
         `T${pad(d.getHours())}:${pad(d.getMinutes())}:00${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

// Date -> value for a datetime-local input
function toLocalInputValue(d) {
  return `${pad(d.getFullYear(), 4)}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const formatLocal = (iso) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
const formatTime = (iso) => new Date(iso).toLocaleTimeString([], { timeStyle: "short" });

function fieldName(id) {
  const f = state.fields.find((x) => x.id === id);
  return f ? f.name : id;
}

// Small DOM helper: el("p", { className: "meta" }, "text", childNode, ...). Uses textContent only (no HTML injection).
function el(tag, props = {}, ...children) {
  const { dataset, ...rest } = props;
  const node = Object.assign(document.createElement(tag), rest);
  if (dataset) Object.assign(node.dataset, dataset); // "dataset" itself is read-only: copy into it
  for (const child of children) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// ---------- API ----------
async function api(method, path, { body, idempotencyKey, auth = true } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && state.token) headers.Authorization = `Bearer ${state.token}`;
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;

  const started = performance.now();
  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    logRequest(method, path, "network error", null, started);
    return { ok: false, status: 0, networkError: true, requestId: null,
             error: { code: "network_error", message: "Could not reach the server" } };
  }

  const requestId = response.headers.get("X-Request-ID");
  let data = null;
  const text = await response.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = null; }
  }
  logRequest(method, path, response.status, requestId, started);

  if (response.status === 401 && auth && state.token) {
    setSession(null, null);
    showMessage($("login-result"), "error", "Your session is no longer valid. Please log in again.");
  }
  if (response.ok) return { ok: true, status: response.status, data, requestId };
  return {
    ok: false,
    status: response.status,
    requestId,
    error: (data && data.error) || { code: "http_error", message: response.statusText || "Request failed" },
  };
}

// Same operation + same form values = a retry, so it reuses the same key.
function idempotencyKeyFor(operation, payload) {
  const fingerprint = JSON.stringify(payload);
  const pending = state.pending[operation];
  if (pending && pending.fingerprint === fingerprint) return { key: pending.key, reused: true };
  const key = newIdempotencyKey();
  state.pending[operation] = { fingerprint, key };
  return { key, reused: false };
}

// Forget the key only once the outcome is known. After a network error or a 5xx we don't know
// whether the server did the work, so the next attempt must reuse the key.
function settleIdempotency(operation, result) {
  if (result.networkError || result.status >= 500) return;
  delete state.pending[operation];
}

// ---------- Rendering ----------
function showMessage(target, kind, ...lines) {
  target.hidden = false;
  target.className = `result ${kind}`;
  target.replaceChildren(...lines.map((line) => (line instanceof Node ? line : el("div", {}, line))));
}

function showError(target, result, extra = null) {
  const { code, message } = result.error;
  const lines = [el("strong", {}, `${result.status || "—"} ${code}`), el("div", {}, message)];
  for (const d of result.error.details || []) lines.push(el("div", { className: "meta" }, `• ${d.field}: ${d.reason}`));
  if (extra) lines.push(el("div", { className: "meta" }, extra));
  if (result.requestId) lines.push(el("div", { className: "meta" }, `Request ID: ${result.requestId}`));
  showMessage(target, "error", ...lines);
}

function logRequest(method, path, status, requestId, started) {
  const ms = Math.round(performance.now() - started);
  const ok = typeof status === "number" && status < 400;
  const item = el("li", {},
    `${new Date().toLocaleTimeString()}  ${method} ${path}  `,
    el("span", { className: ok ? "status-ok" : "status-err" }, String(status)),
    `  ${ms} ms  id=${requestId || "-"}`);
  const log = $("request-log");
  log.prepend(item);
  while (log.children.length > 30) log.lastChild.remove();
}

function setSession(token, me) {
  state.token = token;
  state.me = me;
  const loggedIn = Boolean(token);
  $("session").textContent = loggedIn ? `Logged in as ${me ? me.email : "user"}` : "Not logged in";
  $("logout-btn").hidden = !loggedIn;
  $("reload-fields-btn").disabled = !loggedIn;
  if (!loggedIn) {
    // Keep the last booking ID handy so the owner-only rule can be tested with another account.
    const last = Array.from(state.bookings.keys()).pop();
    if (last) $("lookup-input").value = last;
    state.bookings.clear();
    state.pending = {};
    renderBookings();
  }
  renderManagerInfo();
}

function renderManagerInfo() {
  const info = $("manager-info");
  if (!state.token) {
    info.textContent = "Log in to see which facilities you manage.";
  } else if (!state.me) {
    info.textContent = "Could not load your profile (GET /auth/me). You can still try; the server decides.";
  } else if (state.me.managed_facility_ids.length === 0) {
    info.textContent = "You don't manage any facility: creating a block should be refused (403).";
  } else {
    info.textContent = `You manage ${state.me.managed_facility_ids.length} facility(ies). ` +
      "Blocking a field in another facility should be refused (403).";
  }
}

function renderFields() {
  const select = $("field-select");
  const previous = select.value;
  select.replaceChildren();
  if (state.fields.length === 0) {
    select.append(el("option", { value: "" }, "No fields"));
    select.disabled = true;
    return;
  }
  // One group per facility; full/standalone fields first, sub-fields indented under them.
  const facilities = [...new Set(state.fields.map((f) => f.facility_id))];
  facilities.forEach((facilityId, i) => {
    const group = el("optgroup", { label: `Facility ${i + 1}` });
    const inFacility = state.fields.filter((f) => f.facility_id === facilityId);
    for (const parent of inFacility.filter((f) => !f.parent_field_id)) {
      group.append(el("option", { value: parent.id }, `${parent.name} · ${parent.sport}`));
      for (const child of inFacility.filter((f) => f.parent_field_id === parent.id)) {
        group.append(el("option", { value: child.id }, `\u00A0\u00A0\u00A0└ ${child.name}`));
      }
    }
    select.append(group);
  });
  select.disabled = false;
  if (state.fields.some((f) => f.id === previous)) select.value = previous;
}

function renderBookings() {
  const body = $("bookings-body");
  body.replaceChildren();
  if (state.bookings.size === 0) {
    body.append(el("tr", {}, el("td", { colSpan: 6, className: "muted" }, "No bookings yet.")));
    return;
  }
  for (const b of state.bookings.values()) {
    const refresh = el("button", { type: "button", className: "secondary small" }, "Refresh");
    refresh.addEventListener("click", () => refreshBooking(b.id));
    const cancel = el("button", { type: "button", className: "secondary small" }, "Cancel");
    cancel.addEventListener("click", () => cancelBooking(b.id));
    const canCancel = b.status === "HELD" || b.status === "CONFIRMED";
    cancel.disabled = !canCancel;

    body.append(el("tr", {},
      el("td", {}, fieldName(b.field_id)),
      el("td", {}, `${formatLocal(b.start)} – ${formatTime(b.end)}`),
      el("td", {}, el("span", { className: `badge ${b.status}` }, b.status)),
      el("td", { className: "countdown", dataset: { expires: b.hold_expires_at || "", status: b.status } }, ""),
      el("td", {}, el("code", {}, b.id)),
      el("td", { className: "actions" }, refresh, cancel)));
  }
  updateCountdowns();
}

function updateCountdowns() {
  for (const cell of document.querySelectorAll("td.countdown")) {
    const { expires, status } = cell.dataset;
    if (status !== "HELD" || !expires) { cell.textContent = "—"; continue; }
    const left = Math.round((new Date(expires) - Date.now()) / 1000);
    cell.textContent = left > 0
      ? `in ${Math.floor(left / 60)}:${pad(left % 60)}`
      : "elapsed (press Refresh)";
  }
}

// ---------- Form values ----------
function selectedSlot(target) {
  const fieldId = $("field-select").value;
  const start = toOffsetTimestamp($("start-input").value);
  const end = toOffsetTimestamp($("end-input").value);
  if (!state.token) {
    showMessage(target, "error", "Log in first.");
    return null;
  }
  if (!fieldId) {
    showMessage(target, "error", "Choose a field.");
    return null;
  }
  if (!start || !end) {
    showMessage(target, "error", "Choose a start and an end time.");
    return null;
  }
  return { fieldId, start, end };
}

// ---------- Actions ----------
async function login(event) {
  event.preventDefault();
  const target = $("login-result");
  const result = await api("POST", "/auth/login", {
    auth: false,
    body: { email: $("login-email").value.trim(), password: $("login-password").value },
  });
  $("login-password").value = "";
  if (!result.ok) return showError(target, result);

  setSession(result.data.access_token, null);
  const me = await api("GET", "/auth/me");
  setSession(result.data.access_token, me.ok ? me.data : null);
  const minutes = Math.round((result.data.expires_in || 0) / 60);
  showMessage(target, "ok", `Logged in. The token expires in ${minutes} minutes.`);
  await loadFields();
}

async function loadFields() {
  const result = await api("GET", "/fields");
  if (!result.ok) {
    state.fields = [];
    renderFields();
    return showError($("availability-result"), result, "Could not load fields.");
  }
  state.fields = result.data.items;
  renderFields();
}

async function checkAvailability() {
  const target = $("availability-result");
  const slot = selectedSlot(target);
  if (!slot) return;
  const query = new URLSearchParams({ start: slot.start, end: slot.end }); // encodes "+" in offsets
  const result = await api("GET", `/fields/${encodeURIComponent(slot.fieldId)}/availability?${query}`);
  if (!result.ok) return showError(target, result);
  const a = result.data;
  showMessage(target, a.available ? "ok" : "error",
    el("strong", {}, a.available ? "Available" : "Not available"),
    `${fieldName(a.field_id)}: ${formatLocal(a.start)} – ${formatTime(a.end)}`,
    el("div", { className: "meta" }, `UTC: ${a.start} → ${a.end} · Request ID: ${result.requestId}`));
}

async function placeHold() {
  const target = $("hold-result");
  const slot = selectedSlot(target);
  if (!slot) return;
  const payload = { start: slot.start, end: slot.end };
  const { key, reused } = idempotencyKeyFor("hold", { fieldId: slot.fieldId, ...payload });

  const result = await api("POST", `/fields/${encodeURIComponent(slot.fieldId)}/bookings`, {
    body: payload,
    idempotencyKey: key,
  });
  settleIdempotency("hold", result);
  const keyNote = `Idempotency-Key: ${key}${reused ? " (reused: this was a retry)" : ""}`;

  if (!result.ok) {
    const retryNote = result.networkError || result.status >= 500
      ? "The outcome is unknown. Press \"Place hold\" again to retry safely with the same key."
      : null;
    return showError(target, result, [keyNote, retryNote].filter(Boolean).join("\n"));
  }
  const b = result.data;
  state.bookings.set(b.id, b);
  renderBookings();
  showMessage(target, "ok",
    el("strong", {}, `Hold placed: ${b.status}`),
    `${fieldName(b.field_id)}: ${formatLocal(b.start)} – ${formatTime(b.end)}`,
    `Hold expires at ${formatTime(b.hold_expires_at)}`,
    el("div", { className: "meta" }, `Booking ID: ${b.id}`),
    el("div", { className: "meta" }, keyNote));
}

async function refreshBooking(id) {
  const result = await api("GET", `/bookings/${encodeURIComponent(id)}`);
  if (!result.ok) return showError($("hold-result"), result, `Booking ${id}`);
  state.bookings.set(id, result.data);
  renderBookings();
}

async function cancelBooking(id) {
  const result = await api("DELETE", `/bookings/${encodeURIComponent(id)}`);
  if (!result.ok) return showError($("hold-result"), result, `Booking ${id}`);
  showMessage($("hold-result"), "ok", `Booking cancelled (${result.status}). The slot is released.`);
  await refreshBooking(id);
}

async function lookupBooking() {
  const target = $("lookup-result");
  const id = $("lookup-input").value.trim();
  if (!state.token) return showMessage(target, "error", "Log in first.");
  if (!id) return showMessage(target, "error", "Paste a booking ID.");
  const result = await api("GET", `/bookings/${encodeURIComponent(id)}`);
  if (!result.ok) return showError(target, result);
  const b = result.data;
  state.bookings.set(b.id, b);
  renderBookings();
  showMessage(target, "ok", el("strong", {}, `Found: ${b.status}`),
    `${fieldName(b.field_id)}: ${formatLocal(b.start)} – ${formatTime(b.end)}`);
}

async function createBlock() {
  const target = $("block-result");
  const slot = selectedSlot(target);
  if (!slot) return;
  const payload = { start: slot.start, end: slot.end };
  const { key, reused } = idempotencyKeyFor("block", { fieldId: slot.fieldId, ...payload });

  const result = await api("POST", `/fields/${encodeURIComponent(slot.fieldId)}/blocks`, {
    body: payload,
    idempotencyKey: key,
  });
  settleIdempotency("block", result);
  const keyNote = `Idempotency-Key: ${key}${reused ? " (reused: this was a retry)" : ""}`;
  if (!result.ok) return showError(target, result, keyNote);
  const b = result.data;
  showMessage(target, "ok",
    el("strong", {}, `Block created: ${b.status}`),
    `${fieldName(b.field_id)}: ${formatLocal(b.start)} – ${formatTime(b.end)}`,
    el("div", { className: "meta" }, `Block ID: ${b.id}`),
    el("div", { className: "meta" }, keyNote));
}

function logout() {
  setSession(null, null);
  state.fields = [];
  renderFields();
  $("field-select").replaceChildren(el("option", {}, "Log in to load fields"));
  showMessage($("login-result"), "ok", "Logged out.");
}

// ---------- Start-up ----------
function init() {
  // Default slot: the next full hour, for 90 minutes.
  const start = new Date();
  start.setMinutes(0, 0, 0);
  start.setHours(start.getHours() + 1);
  const end = new Date(start.getTime() + 90 * 60 * 1000);
  $("start-input").value = toLocalInputValue(start);
  $("end-input").value = toLocalInputValue(end);
  $("tz-label").textContent = `Your time zone: ${Intl.DateTimeFormat().resolvedOptions().timeZone}`;

  $("login-form").addEventListener("submit", login);
  $("logout-btn").addEventListener("click", logout);
  $("reload-fields-btn").addEventListener("click", loadFields);
  $("availability-btn").addEventListener("click", checkAvailability);
  $("hold-btn").addEventListener("click", placeHold);
  $("lookup-btn").addEventListener("click", lookupBooking);
  $("block-btn").addEventListener("click", createBlock);
  setInterval(updateCountdowns, 1000);
}

init();