const NAV_LINKS = [
  ["dashboard.html", "Dashboard"],
  ["resume.html", "Résumé"],
  ["preferences.html", "Preferences"],
  ["compare.html", "Compare"],
  ["chat.html", "Ask AI"],
  ["exams.html", "Exams"],
  ["saved.html", "Saved"],
  ["history.html", "History"]
];

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options
  });

  const isJson = (response.headers.get("content-type") || "").includes("json");
  const body = isJson ? await response.json() : null;

  if (!response.ok) {
    throw new Error((body && body.detail) || `Request failed (${response.status})`);
  }

  return body;
}

async function getUser() {
  try {
    const user = await api("/api/auth/me");
    return user && user.email ? user : null;
  } catch {
    return null;
  }
}

/** Redirects to login when signed out. Returns the user otherwise. */
async function requireUser() {
  const user = await getUser();

  if (!user) {
    window.location.href = "login.html";
    return null;
  }

  return user;
}

function renderHeader(user, currentPage) {
  const links = NAV_LINKS.map(
    ([href, label]) =>
      `<a href="${href}"${href === currentPage ? ' class="is-current"' : ""}>${label}</a>`
  ).join("");

  const adminLink = user && user.is_admin
    ? `<a href="admin.html"${currentPage === "admin.html" ? ' class="is-current"' : ""}>Admin</a>`
    : "";

  document.querySelector(".site-header").innerHTML = `
    <div class="wrap header-inner">
      <a class="brand" href="dashboard.html">
        <svg class="brand-mark" viewBox="0 0 48 48" aria-hidden="true">
          <path d="M24 6 L46 16 L24 26 L2 16 Z"/>
          <path d="M12 20.5 V32 C12 35 17 38 24 38 C31 38 36 35 36 32 V20.5"/>
        </svg>
        <span class="brand-name">EduBridge</span>
      </a>
      <nav class="site-nav">
        ${links}${adminLink}
        <span class="nav-user">${user ? escapeHtml(user.email) : ""}</span>
        <a href="#" id="logout-link">Sign out</a>
      </nav>
    </div>`;

  const logout = document.getElementById("logout-link");

  if (logout) {
    logout.addEventListener("click", async (event) => {
      event.preventDefault();
      await api("/api/auth/logout", { method: "POST" });
      window.location.href = "index.html";
    });
  }
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

/**
 * Renders the light Markdown a free LLM tends to produce (**bold**,
 * "- " bullet lists, blank-line paragraphs) as HTML. Escapes first, so
 * nothing in the model's own text can inject real markup — only the
 * "**...**" / "- " patterns this function itself adds become tags.
 */
function renderMarkdown(text) {
  const escaped = escapeHtml(text ?? "").replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  const blocks = [];
  let listItems = null;

  for (const rawLine of escaped.split("\n")) {
    const line = rawLine.trim();
    const bullet = line.match(/^[-*]\s+(.*)/);

    if (bullet) {
      if (!listItems) { listItems = []; blocks.push(listItems); }
      listItems.push(bullet[1]);
    } else {
      listItems = null;
      if (line) blocks.push(line);
    }
  }

  return blocks
    .map((block) =>
      Array.isArray(block)
        ? `<ul>${block.map((item) => `<li>${item}</li>`).join("")}</ul>`
        : `<p>${block}</p>`
    )
    .join("");
}

function money(value) {
  return value === null || value === undefined
    ? "Not reported"
    : `$${Math.round(value).toLocaleString()}`;
}

function percent(value) {
  return value === null || value === undefined
    ? "Not reported"
    : `${(value * 100).toFixed(1)}%`;
}

function plain(value) {
  return value === null || value === undefined || value === ""
    ? "Not reported"
    : value;
}

/** Small compare affordance shared by every card type and the saved list. */
function compareLink(key) {
  return `<a class="compare-link" href="compare.html?a=${encodeURIComponent(key)}"
     onclick="event.stopPropagation()">Compare ⇄</a>`;
}

let savedKeysCache = null;

/** The signed-in student's saved-university keys, fetched once and
    cached for the page — avoids one request per card to know whether
    its star should start filled. */
async function getSavedKeys() {
  if (savedKeysCache) return savedKeysCache;

  try {
    const data = await api("/api/saved");
    savedKeysCache = new Set(data.saved.map((s) => s.key));
  } catch {
    savedKeysCache = new Set();
  }

  return savedKeysCache;
}

/** Toggles a university's saved state. Expects the button to carry a
    URI-encoded compare key ("us:166683", "india:...") in data-key. */
async function toggleSave(button) {
  const key = decodeURIComponent(button.dataset.key);
  const keys = await getSavedKeys();
  const isSaved = keys.has(key);

  button.disabled = true;

  try {
    await api(isSaved ? "/api/saved/remove" : "/api/saved", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key })
    });

    if (isSaved) {
      keys.delete(key);
      button.textContent = "☆ Save";
      button.classList.remove("is-saved");
    } else {
      keys.add(key);
      button.textContent = "★ Saved";
      button.classList.add("is-saved");
    }
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
  }
}

/** Save-toggle button markup, shared by every card type and the
    university detail page. */
function saveButton(key, savedKeys) {
  const isSaved = (savedKeys || new Set()).has(key);

  return `<button type="button" class="save-link${isSaved ? " is-saved" : ""}"
    data-key="${encodeURIComponent(key)}"
    onclick="event.preventDefault(); event.stopPropagation(); toggleSave(this);">${
      isSaved ? "★ Saved" : "☆ Save"
    }</button>`;
}

function setBusy(button, busy, busyLabel) {
  if (!button) return;
  button.dataset.label = button.dataset.label || button.textContent;
  button.disabled = busy;
  button.textContent = busy ? busyLabel : button.dataset.label;
}

/** Floating assistant available on every signed-in page. */
function mountBot() {
  const root = document.createElement("div");
  root.innerHTML = `
    <button id="bot-toggle" class="btn btn-primary" style="position:fixed;right:20px;bottom:20px;z-index:50;border-radius:999px;padding:12px 22px;box-shadow:var(--shadow-lg);">Ask EduBridge</button>
    <div id="bot-panel" hidden style="position:fixed;right:20px;bottom:80px;width:min(94vw,360px);max-height:66vh;overflow:auto;z-index:50;background:#fff;border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow-lg);padding:16px;">
      <strong>Ask about universities</strong>
      <div id="bot-log" class="chat-log" style="margin-top:12px;"></div>
      <form id="bot-form" class="chat-form">
        <input id="bot-input" type="text" placeholder="e.g. cheap CS universities" required>
        <button class="btn btn-secondary" type="submit">Go</button>
      </form>
    </div>`;
  document.body.appendChild(root);

  const panel = document.getElementById("bot-panel");
  const log = document.getElementById("bot-log");

  document.getElementById("bot-toggle").addEventListener("click", () => {
    panel.hidden = !panel.hidden;
  });

  document.getElementById("bot-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("bot-input");
    const question = input.value.trim();
    if (!question) return;

    log.innerHTML += `<div class="msg msg-user">${escapeHtml(question)}</div>`;
    input.value = "";
    log.innerHTML += `<div class="msg msg-bot" id="bot-pending">Thinking…</div>`;
    log.scrollTop = log.scrollHeight;

    try {
      const result = await api("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question })
      });
      document.getElementById("bot-pending").outerHTML =
        `<div class="msg msg-bot">${renderMarkdown(result.answer)}</div>`;
    } catch (error) {
      document.getElementById("bot-pending").outerHTML =
        `<div class="msg msg-bot">${escapeHtml(error.message)}</div>`;
    }
    log.scrollTop = log.scrollHeight;
  });
}

/** Standard page boot: auth gate, header, bot. */
async function initPage(currentPage, { bot = true } = {}) {
  const user = await requireUser();
  if (!user) return null;

  renderHeader(user, currentPage);
  if (bot) mountBot();

  return user;
}
