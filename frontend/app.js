// ArenaHub test client: plain JavaScript, no framework, served by FastAPI (same origin).
"use strict"; // Turn on strict mode to catch common mistakes.

// ---------- State (kept in memory only) ----------
const state = { // Everything the page remembers; lost on reload.
  token: null,           // access token from POST /auth/login
  me: null,              // GET /auth/me
  fields: [],            // GET /fields
  bookings: new Map(),   // booking id -> booking, for this session
  pending: {},           // operation -> { fingerprint, key }: Idempotency-Keys awaiting an answer
}; // Finish the state.

const $ = (id) => document.getElementById(id); // Short helper to find an element by its ID.

// ---------- Helpers ----------
const pad = (n, len = 2) => String(n).padStart(len, "0"); // Left-pad a number with zeros, e.g. 5 -> "05".

function newIdempotencyKey() { // Make a fresh retry key.
  if (crypto.randomUUID) return crypto.randomUUID(); // Use the built-in UUID when available.
  const b = crypto.getRandomValues(new Uint8Array(16)); // Otherwise take 16 random bytes.
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join(""); // Turn them into hex text.
} // Finish newIdempotencyKey.

// "2026-11-15T20:00" (from a datetime-local input) -> "2026-11-15T20:00:00-05:00"
function toOffsetTimestamp(localValue) { // Add the browser's timezone offset to a local time.
  if (!localValue) return null; // Empty input means no value.
  const d = new Date(localValue); // Parse it as local time.
  if (Number.isNaN(d.getTime())) return null; // Unparseable input means no value.
  const offset = -d.getTimezoneOffset(); // Minutes ahead of UTC (the browser reports it reversed).
  const sign = offset >= 0 ? "+" : "-"; // Plus east of UTC, minus west.
  const abs = Math.abs(offset); // Offset size in minutes.
  return `${pad(d.getFullYear(), 4)}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` + // Date part: YYYY-MM-DD.
         `T${pad(d.getHours())}:${pad(d.getMinutes())}:00${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`; // Time part plus the +/-HH:MM offset.
} // Finish toOffsetTimestamp.

// Date -> value for a datetime-local input
function toLocalInputValue(d) { // Format a Date the way datetime-local inputs expect.
  return `${pad(d.getFullYear(), 4)}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; // YYYY-MM-DDTHH:MM in local time.
} // Finish toLocalInputValue.

const formatLocal = (iso) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); // Date and time in the user's locale.
const formatTime = (iso) => new Date(iso).toLocaleTimeString([], { timeStyle: "short" }); // Time only, in the user's locale.

function fieldName(id) { // Turn a field ID into its display name.
  const f = state.fields.find((x) => x.id === id); // Look it up in the loaded fields.
  return f ? f.name : id; // Fall back to the raw ID.
} // Finish fieldName.

// Small DOM helper: el("p", { className: "meta" }, "text", childNode, ...). Uses textContent only (no HTML injection).
function el(tag, props = {}, ...children) { // Create an element with properties and children.
  const { dataset, ...rest } = props; // Pull "dataset" out; it needs special handling.
  const node = Object.assign(document.createElement(tag), rest); // Create the element and copy the other properties.
  if (dataset) Object.assign(node.dataset, dataset); // "dataset" itself is read-only: copy into it
  for (const child of children) { // Add each child in order.
    if (child === null || child === undefined) continue; // Skip empty children.
    node.append(child instanceof Node ? child : document.createTextNode(String(child))); // Elements as-is; everything else as plain text.
  } // Finish the loop.
  return node; // The finished element.
} // Finish el.

// ---------- API ----------
async function api(method, path, { body, idempotencyKey, auth = true } = {}) { // Call the API and return a simple result object.
  const headers = { Accept: "application/json" }; // We want JSON back.
  if (body !== undefined) headers["Content-Type"] = "application/json"; // Tell the server we send JSON.
  if (auth && state.token) headers.Authorization = `Bearer ${state.token}`; // Attach the login token when needed.
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey; // Attach the retry key when given.

  const started = performance.now(); // Start the timer for the request log.
  let response; // Filled in below.
  try { // The network can fail.
    response = await fetch(path, { // Send the request.
      method, // GET, POST, ...
      headers, // The headers built above.
      body: body === undefined ? undefined : JSON.stringify(body), // Send JSON only when there is a body.
    }); // Finish the fetch.
  } catch { // The server could not be reached.
    logRequest(method, path, "network error", null, started); // Record the failure in the log.
    return { ok: false, status: 0, networkError: true, requestId: null, // Report a failed result...
             error: { code: "network_error", message: "Could not reach the server" } }; // ...with a readable error.
  } // Finish the try/catch.

  const requestId = response.headers.get("X-Request-ID"); // The server's correlation ID.
  let data = null; // Parsed JSON, if any.
  const text = await response.text(); // Read the body as text first.
  if (text) { // There is a body.
    try { data = JSON.parse(text); } catch { data = null; } // Parse it; ignore invalid JSON.
  } // Finish the body check.
  logRequest(method, path, response.status, requestId, started); // Record the request in the log.

  if (response.status === 401 && auth && state.token) { // The token is no longer accepted.
    setSession(null, null); // Log the user out locally.
    showMessage($("login-result"), "error", "Your session is no longer valid. Please log in again."); // Tell them why.
  } // Finish the 401 handling.
  if (response.ok) return { ok: true, status: response.status, data, requestId }; // Success: return the data.
  return { // Failure: return the error details.
    ok: false, // Mark it as failed.
    status: response.status, // HTTP status code.
    requestId, // For finding it in the server logs.
    error: (data && data.error) || { code: "http_error", message: response.statusText || "Request failed" }, // The API's error, or a generic one.
  }; // Finish the failed result.
} // Finish api.

// Same operation + same form values = a retry, so it reuses the same key.
function idempotencyKeyFor(operation, payload) { // Decide which retry key to send.
  const fingerprint = JSON.stringify(payload); // Identify the request by its contents.
  const pending = state.pending[operation]; // A key still waiting for an answer, if any.
  if (pending && pending.fingerprint === fingerprint) return { key: pending.key, reused: true }; // Same request again: reuse the key.
  const key = newIdempotencyKey(); // Different request: make a new key.
  state.pending[operation] = { fingerprint, key }; // Remember it until we know the outcome.
  return { key, reused: false }; // A fresh key.
} // Finish idempotencyKeyFor.

// Forget the key only once the outcome is known. After a network error or a 5xx we don't know
// whether the server did the work, so the next attempt must reuse the key.
function settleIdempotency(operation, result) { // Clear the saved key when the outcome is clear.
  if (result.networkError || result.status >= 500) return; // Outcome unknown: keep the key.
  delete state.pending[operation]; // Outcome known: forget the key.
} // Finish settleIdempotency.

// ---------- Rendering ----------
function showMessage(target, kind, ...lines) { // Show a message box.
  target.hidden = false; // Make the box visible.
  target.className = `result ${kind}`; // "ok" or "error" styling.
  target.replaceChildren(...lines.map((line) => (line instanceof Node ? line : el("div", {}, line)))); // Replace its content with one row per line.
} // Finish showMessage.

function showError(target, result, extra = null) { // Show an API error.
  const { code, message } = result.error; // The error's code and message.
  const lines = [el("strong", {}, `${result.status || "—"} ${code}`), el("div", {}, message)]; // Status and code in bold, then the message.
  for (const d of result.error.details || []) lines.push(el("div", { className: "meta" }, `• ${d.field}: ${d.reason}`)); // One line per field problem.
  if (extra) lines.push(el("div", { className: "meta" }, extra)); // Any extra note.
  if (result.requestId) lines.push(el("div", { className: "meta" }, `Request ID: ${result.requestId}`)); // Request ID for log searches.
  showMessage(target, "error", ...lines); // Display everything.
} // Finish showError.

function logRequest(method, path, status, requestId, started) { // Add a line to the on-page request log.
  const ms = Math.round(performance.now() - started); // How long the request took.
  const ok = typeof status === "number" && status < 400; // Success if it is a number below 400.
  const item = el("li", {}, // One list item per request.
    `${new Date().toLocaleTimeString()}  ${method} ${path}  `, // Time, method, and path.
    el("span", { className: ok ? "status-ok" : "status-err" }, String(status)), // Colored status.
    `  ${ms} ms  id=${requestId || "-"}`); // Duration and request ID.
  const log = $("request-log"); // The log list.
  log.prepend(item); // Newest entry on top.
  while (log.children.length > 30) log.lastChild.remove(); // Keep only the latest 30.
} // Finish logRequest.

function setSession(token, me) { // Update the page after login or logout.
  state.token = token; // Save the token.
  state.me = me; // Save the profile.
  const loggedIn = Boolean(token); // True when we have a token.
  $("session").textContent = loggedIn ? `Logged in as ${me ? me.email : "user"}` : "Not logged in"; // Header status text.
  $("logout-btn").hidden = !loggedIn; // Show "Log out" only when logged in.
  $("reload-fields-btn").disabled = !loggedIn; // Reloading fields needs a login.
  if (!loggedIn) { // Logging out.
    // Keep the last booking ID handy so the owner-only rule can be tested with another account.
    const last = Array.from(state.bookings.keys()).pop(); // The most recent booking ID.
    if (last) $("lookup-input").value = last; // Put it in the lookup box.
    state.bookings.clear(); // Forget this session's bookings.
    state.pending = {}; // Forget unfinished retry keys.
    renderBookings(); // Redraw the (now empty) table.
  } // Finish the logout cleanup.
  renderManagerInfo(); // Update the manager hint.
} // Finish setSession.

function renderManagerInfo() { // Explain what the user can expect in the manager section.
  const info = $("manager-info"); // The hint element.
  if (!state.token) { // Not logged in.
    info.textContent = "Log in to see which facilities you manage."; // Ask them to log in.
  } else if (!state.me) { // Logged in but the profile failed to load.
    info.textContent = "Could not load your profile (GET /auth/me). You can still try; the server decides."; // Explain the fallback.
  } else if (state.me.managed_facility_ids.length === 0) { // A regular player.
    info.textContent = "You don't manage any facility: creating a block should be refused (403)."; // Predict the refusal.
  } else { // A manager.
    info.textContent = `You manage ${state.me.managed_facility_ids.length} facility(ies). ` + // How many facilities.
      "Blocking a field in another facility should be refused (403)."; // Predict the refusal elsewhere.
  } // Finish the branches.
} // Finish renderManagerInfo.

function renderFields() { // Fill the field drop-down.
  const select = $("field-select"); // The drop-down.
  const previous = select.value; // Remember the current choice.
  select.replaceChildren(); // Empty it.
  if (state.fields.length === 0) { // Nothing to show.
    select.append(el("option", { value: "" }, "No fields")); // Placeholder option.
    select.disabled = true; // Nothing to choose.
    return; // Done.
  } // Finish the empty case.
  // One group per facility; full/standalone fields first, sub-fields indented under them.
  const facilities = [...new Set(state.fields.map((f) => f.facility_id))]; // Unique facility IDs.
  facilities.forEach((facilityId, i) => { // One group per facility.
    const group = el("optgroup", { label: `Facility ${i + 1}` }); // Group label.
    const inFacility = state.fields.filter((f) => f.facility_id === facilityId); // Fields in this facility.
    for (const parent of inFacility.filter((f) => !f.parent_field_id)) { // Full and standalone fields first.
      group.append(el("option", { value: parent.id }, `${parent.name} · ${parent.sport}`)); // The parent option.
      for (const child of inFacility.filter((f) => f.parent_field_id === parent.id)) { // Its sub-fields.
        group.append(el("option", { value: child.id }, `\u00A0\u00A0\u00A0└ ${child.name}`)); // Indented under the parent.
      } // Finish the sub-fields.
    } // Finish the parents.
    select.append(group); // Add the group to the drop-down.
  }); // Finish the facilities.
  select.disabled = false; // Allow choosing.
  if (state.fields.some((f) => f.id === previous)) select.value = previous; // Restore the earlier choice if it still exists.
} // Finish renderFields.

function renderBookings() { // Redraw the bookings table.
  const body = $("bookings-body"); // The table body.
  body.replaceChildren(); // Empty it.
  if (state.bookings.size === 0) { // No bookings yet.
    body.append(el("tr", {}, el("td", { colSpan: 6, className: "muted" }, "No bookings yet."))); // Placeholder row.
    return; // Done.
  } // Finish the empty case.
  for (const b of state.bookings.values()) { // One row per booking.
    const refresh = el("button", { type: "button", className: "secondary small" }, "Refresh"); // Refresh button.
    refresh.addEventListener("click", () => refreshBooking(b.id)); // Reload this booking when clicked.
    const cancel = el("button", { type: "button", className: "secondary small" }, "Cancel"); // Cancel button.
    cancel.addEventListener("click", () => cancelBooking(b.id)); // Cancel this booking when clicked.
    const canCancel = b.status === "HELD" || b.status === "CONFIRMED"; // Only active bookings can be cancelled.
    cancel.disabled = !canCancel; // Disable it otherwise.

    body.append(el("tr", {}, // The row.
      el("td", {}, fieldName(b.field_id)), // Field name.
      el("td", {}, `${formatLocal(b.start)} – ${formatTime(b.end)}`), // Time range.
      el("td", {}, el("span", { className: `badge ${b.status}` }, b.status)), // Status badge.
      el("td", { className: "countdown", dataset: { expires: b.hold_expires_at || "", status: b.status } }, ""), // Countdown, filled in below.
      el("td", {}, el("code", {}, b.id)), // Booking ID.
      el("td", { className: "actions" }, refresh, cancel))); // Action buttons.
  } // Finish the rows.
  updateCountdowns(); // Fill the countdown cells now.
} // Finish renderBookings.

function updateCountdowns() { // Refresh every "hold expires" cell.
  for (const cell of document.querySelectorAll("td.countdown")) { // Each countdown cell.
    const { expires, status } = cell.dataset; // Its saved deadline and status.
    if (status !== "HELD" || !expires) { cell.textContent = "—"; continue; } // Only temporary holds count down.
    const left = Math.round((new Date(expires) - Date.now()) / 1000); // Seconds remaining.
    cell.textContent = left > 0 // Still time left?
      ? `in ${Math.floor(left / 60)}:${pad(left % 60)}` // Show minutes:seconds.
      : "elapsed (press Refresh)"; // Past the deadline.
  } // Finish the cells.
} // Finish updateCountdowns.

// ---------- Form values ----------
function selectedSlot(target) { // Read and check the field and time inputs.
  const fieldId = $("field-select").value; // Chosen field.
  const start = toOffsetTimestamp($("start-input").value); // Start with timezone offset.
  const end = toOffsetTimestamp($("end-input").value); // End with timezone offset.
  if (!state.token) { // Not logged in.
    showMessage(target, "error", "Log in first."); // Explain.
    return null; // Stop.
  } // Finish the login check.
  if (!fieldId) { // No field chosen.
    showMessage(target, "error", "Choose a field."); // Explain.
    return null; // Stop.
  } // Finish the field check.
  if (!start || !end) { // A time is missing.
    showMessage(target, "error", "Choose a start and an end time."); // Explain.
    return null; // Stop.
  } // Finish the time check.
  return { fieldId, start, end }; // Everything is present.
} // Finish selectedSlot.

// ---------- Actions ----------
async function login(event) { // Handle the login form.
  event.preventDefault(); // Stop the browser from reloading the page.
  const target = $("login-result"); // Where to show the outcome.
  const result = await api("POST", "/auth/login", { // Ask the server for a token.
    auth: false, // No token yet.
    body: { email: $("login-email").value.trim(), password: $("login-password").value }, // Credentials from the form.
  }); // Finish the request.
  $("login-password").value = ""; // Clear the password field right away.
  if (!result.ok) return showError(target, result); // Show the error and stop.

  setSession(result.data.access_token, null); // Save the token first, so the next call is authenticated.
  const me = await api("GET", "/auth/me"); // Load the profile.
  setSession(result.data.access_token, me.ok ? me.data : null); // Save the profile too.
  const minutes = Math.round((result.data.expires_in || 0) / 60); // Token lifetime in minutes.
  showMessage(target, "ok", `Logged in. The token expires in ${minutes} minutes.`); // Confirm.
  await loadFields(); // Load the field list.
} // Finish login.

async function loadFields() { // Fetch and show the fields.
  const result = await api("GET", "/fields"); // Ask the server.
  if (!result.ok) { // It failed.
    state.fields = []; // Clear the list.
    renderFields(); // Redraw the drop-down.
    return showError($("availability-result"), result, "Could not load fields."); // Show the error.
  } // Finish the failure case.
  state.fields = result.data.items; // Save the fields.
  renderFields(); // Redraw the drop-down.
} // Finish loadFields.

async function checkAvailability() { // Ask whether the slot is free.
  const target = $("availability-result"); // Where to show the outcome.
  const slot = selectedSlot(target); // Read the inputs.
  if (!slot) return; // Stop if something is missing.
  const query = new URLSearchParams({ start: slot.start, end: slot.end }); // encodes "+" in offsets
  const result = await api("GET", `/fields/${encodeURIComponent(slot.fieldId)}/availability?${query}`); // Ask the server.
  if (!result.ok) return showError(target, result); // Show the error and stop.
  const a = result.data; // The answer.
  showMessage(target, a.available ? "ok" : "error", // Green when free, red when taken.
    el("strong", {}, a.available ? "Available" : "Not available"), // Headline.
    `${fieldName(a.field_id)}: ${formatLocal(a.start)} – ${formatTime(a.end)}`, // Field and local time range.
    el("div", { className: "meta" }, `UTC: ${a.start} → ${a.end} · Request ID: ${result.requestId}`)); // UTC times and request ID.
} // Finish checkAvailability.

async function placeHold() { // Try to hold the slot.
  const target = $("hold-result"); // Where to show the outcome.
  const slot = selectedSlot(target); // Read the inputs.
  if (!slot) return; // Stop if something is missing.
  const payload = { start: slot.start, end: slot.end }; // Request body.
  const { key, reused } = idempotencyKeyFor("hold", { fieldId: slot.fieldId, ...payload }); // New key, or the same one for a retry.

  const result = await api("POST", `/fields/${encodeURIComponent(slot.fieldId)}/bookings`, { // Create the hold.
    body: payload, // The interval.
    idempotencyKey: key, // The retry key.
  }); // Finish the request.
  settleIdempotency("hold", result); // Forget the key if the outcome is known.
  const keyNote = `Idempotency-Key: ${key}${reused ? " (reused: this was a retry)" : ""}`; // Show which key was used.

  if (!result.ok) { // It failed.
    const retryNote = result.networkError || result.status >= 500 // Unknown outcome?
      ? "The outcome is unknown. Press \"Place hold\" again to retry safely with the same key." // Tell them to retry.
      : null; // Otherwise no note.
    return showError(target, result, [keyNote, retryNote].filter(Boolean).join("\n")); // Show the error and notes.
  } // Finish the failure case.
  const b = result.data; // The new booking.
  state.bookings.set(b.id, b); // Remember it.
  renderBookings(); // Redraw the table.
  showMessage(target, "ok", // Show success.
    el("strong", {}, `Hold placed: ${b.status}`), // Headline.
    `${fieldName(b.field_id)}: ${formatLocal(b.start)} – ${formatTime(b.end)}`, // Field and time range.
    `Hold expires at ${formatTime(b.hold_expires_at)}`, // Deadline.
    el("div", { className: "meta" }, `Booking ID: ${b.id}`), // Booking ID.
    el("div", { className: "meta" }, keyNote)); // Retry key note.
} // Finish placeHold.

async function refreshBooking(id) { // Reload one booking from the server.
  const result = await api("GET", `/bookings/${encodeURIComponent(id)}`); // Ask the server.
  if (!result.ok) return showError($("hold-result"), result, `Booking ${id}`); // Show the error and stop.
  state.bookings.set(id, result.data); // Save the fresh copy.
  renderBookings(); // Redraw the table.
} // Finish refreshBooking.

async function cancelBooking(id) { // Cancel one booking.
  const result = await api("DELETE", `/bookings/${encodeURIComponent(id)}`); // Ask the server.
  if (!result.ok) return showError($("hold-result"), result, `Booking ${id}`); // Show the error and stop.
  showMessage($("hold-result"), "ok", `Booking cancelled (${result.status}). The slot is released.`); // Confirm.
  await refreshBooking(id); // Show its new status.
} // Finish cancelBooking.

async function lookupBooking() { // Find a booking by its ID.
  const target = $("lookup-result"); // Where to show the outcome.
  const id = $("lookup-input").value.trim(); // The pasted ID.
  if (!state.token) return showMessage(target, "error", "Log in first."); // Login is required.
  if (!id) return showMessage(target, "error", "Paste a booking ID."); // An ID is required.
  const result = await api("GET", `/bookings/${encodeURIComponent(id)}`); // Ask the server.
  if (!result.ok) return showError(target, result); // Show the error and stop.
  const b = result.data; // The booking.
  state.bookings.set(b.id, b); // Remember it.
  renderBookings(); // Redraw the table.
  showMessage(target, "ok", el("strong", {}, `Found: ${b.status}`), // Headline with the status.
    `${fieldName(b.field_id)}: ${formatLocal(b.start)} – ${formatTime(b.end)}`); // Field and time range.
} // Finish lookupBooking.

async function createBlock() { // Manager: block the slot.
  const target = $("block-result"); // Where to show the outcome.
  const slot = selectedSlot(target); // Read the inputs.
  if (!slot) return; // Stop if something is missing.
  const payload = { start: slot.start, end: slot.end }; // Request body.
  const { key, reused } = idempotencyKeyFor("block", { fieldId: slot.fieldId, ...payload }); // New key, or the same one for a retry.

  const result = await api("POST", `/fields/${encodeURIComponent(slot.fieldId)}/blocks`, { // Create the block.
    body: payload, // The interval.
    idempotencyKey: key, // The retry key.
  }); // Finish the request.
  settleIdempotency("block", result); // Forget the key if the outcome is known.
  const keyNote = `Idempotency-Key: ${key}${reused ? " (reused: this was a retry)" : ""}`; // Show which key was used.
  if (!result.ok) return showError(target, result, keyNote); // Show the error and stop.
  const b = result.data; // The new block.
  showMessage(target, "ok", // Show success.
    el("strong", {}, `Block created: ${b.status}`), // Headline.
    `${fieldName(b.field_id)}: ${formatLocal(b.start)} – ${formatTime(b.end)}`, // Field and time range.
    el("div", { className: "meta" }, `Block ID: ${b.id}`), // Block ID.
    el("div", { className: "meta" }, keyNote)); // Retry key note.
} // Finish createBlock.

function logout() { // Log out locally.
  setSession(null, null); // Clear the token and profile.
  state.fields = []; // Forget the fields.
  renderFields(); // Redraw the drop-down.
  $("field-select").replaceChildren(el("option", {}, "Log in to load fields")); // Show the login hint instead.
  showMessage($("login-result"), "ok", "Logged out."); // Confirm.
} // Finish logout.

// ---------- Start-up ----------
function init() { // Prepare the page.
  // Default slot: the next full hour, for 90 minutes.
  const start = new Date(); // Now.
  start.setMinutes(0, 0, 0); // Round down to the hour.
  start.setHours(start.getHours() + 1); // Move to the next hour.
  const end = new Date(start.getTime() + 90 * 60 * 1000); // 90 minutes later.
  $("start-input").value = toLocalInputValue(start); // Fill the start input.
  $("end-input").value = toLocalInputValue(end); // Fill the end input.
  $("tz-label").textContent = `Your time zone: ${Intl.DateTimeFormat().resolvedOptions().timeZone}`; // Show the browser's timezone.

  $("login-form").addEventListener("submit", login); // Log in on submit.
  $("logout-btn").addEventListener("click", logout); // Log out on click.
  $("reload-fields-btn").addEventListener("click", loadFields); // Reload fields on click.
  $("availability-btn").addEventListener("click", checkAvailability); // Check availability on click.
  $("hold-btn").addEventListener("click", placeHold); // Place a hold on click.
  $("lookup-btn").addEventListener("click", lookupBooking); // Look up a booking on click.
  $("block-btn").addEventListener("click", createBlock); // Create a block on click.
  setInterval(updateCountdowns, 1000); // Update the countdowns every second.
} // Finish init.

init(); // Start the page.
