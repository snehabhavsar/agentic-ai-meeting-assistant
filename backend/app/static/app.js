/* ═══════════════════════════════════════════════════════════════
   MEETING AI — Frontend Application
   All API integrations preserved exactly.
   New: toast system, modal, dark mode, sidebar, drag-drop,
        recording timer, stats, activity log, progress bar.
   ═══════════════════════════════════════════════════════════════ */

// ─── Shorthand ─────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

// ─── 401 interceptor ────────────────────────────────────────────
// Any API call that gets a 401 redirects to /login automatically.
(function () {
  const _fetch = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    const resp = await _fetch(input, init);
    if (resp.status === 401) {
      const url = typeof input === "string" ? input : input?.url || "";
      if (!url.includes("/auth/")) {
        window.location.href = "/login";
      }
    }
    return resp;
  };
})();

// ─── Application State ─────────────────────────────────────────
const state = {
  projects:             [],
  selectedProjectId:    null,
  selectedProjectName:  null,
  participants:         [],
  name_aliases:         {},
  meetingId:            null,
  recorder:             null,
  chunks:               [],
  stream:               null,
  mimeType:             null,
  view:                 "setup",
  currentMeeting:       null,
  selectedAiIds:        new Set(),
};

// ═══════════════════════════════════════════════════════════════
// UTILITY HELPERS
// ═══════════════════════════════════════════════════════════════

function escapeHtml(s) {
  return String(s)
    .replaceAll("&",  "&amp;")
    .replaceAll("<",  "&lt;")
    .replaceAll(">",  "&gt;")
    .replaceAll('"',  "&quot;")
    .replaceAll("'",  "&#039;");
}

function fmtActionItem(ai) {
  const due    = ai.by_when || null;
  const who    = ai.who     || "Unassigned";
  const willDo = ai.will_do || "do";
  return `${who} — ${willDo} — ${ai.what}${due ? ` — By ${due}` : ""}`;
}

function fmtDate(isoStr) {
  if (!isoStr) return "—";
  const date    = new Date(isoStr);
  const now     = new Date();
  const diffMs  = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  const diffDay = Math.floor(diffMs / 86400000);
  if (diffMin < 1)   return "Just now";
  if (diffMin < 60)  return `${diffMin}m ago`;
  if (diffDay === 0) return "Today";
  if (diffDay === 1) return "Yesterday";
  if (diffDay < 7)   return `${diffDay} days ago`;
  if (diffDay < 30)  return `${Math.floor(diffDay / 7)}w ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function fmtFileSize(bytes) {
  if (bytes < 1024)        return `${bytes} B`;
  if (bytes < 1048576)     return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function fmtDateTime(isoStr) {
  if (!isoStr) return "—";
  return (isoStr || "").slice(0, 19).replace("T", " ");
}

// Status → badge class mapping
function statusBadge(status) {
  const map = {
    processed: "badge-success",
    created:   "badge-default",
    failed:    "badge-danger",
    pending:   "badge-warning",
    completed: "badge-success",
    processing:"badge-primary",
  };
  return map[status] || "badge-default";
}

// ═══════════════════════════════════════════════════════════════
// TOAST NOTIFICATION SYSTEM
// ═══════════════════════════════════════════════════════════════

const toast = (() => {
  const ICONS = {
    success: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
    error:   `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>`,
    warning: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/></svg>`,
    info:    `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>`,
  };

  function show(message, type = "info", duration = 4500) {
    const container = $("toastContainer");
    if (!container) return;

    const el = document.createElement("div");
    el.className = `toast toast-${type}`;
    el.setAttribute("role", "alert");
    el.innerHTML = `
      <span class="toast-icon" aria-hidden="true">${ICONS[type] || ICONS.info}</span>
      <span class="toast-body">
        <span class="toast-message">${escapeHtml(message)}</span>
      </span>
      <button class="toast-close" aria-label="Dismiss notification">&times;</button>
    `;

    el.querySelector(".toast-close").addEventListener("click", () => dismiss(el));
    container.appendChild(el);

    // Trigger CSS transition
    requestAnimationFrame(() => {
      requestAnimationFrame(() => el.classList.add("visible"));
    });

    if (duration > 0) setTimeout(() => dismiss(el), duration);
  }

  function dismiss(el) {
    el.classList.remove("visible");
    setTimeout(() => el.remove(), 350);
  }

  return {
    show,
    success: (msg) => show(msg, "success"),
    error:   (msg) => show(msg, "error", 6000),
    warning: (msg) => show(msg, "warning"),
    info:    (msg) => show(msg, "info"),
  };
})();

// ═══════════════════════════════════════════════════════════════
// CONFIRM MODAL
// ═══════════════════════════════════════════════════════════════

const modal = (() => {
  let resolveFn = null;

  function init() {
    $("modalCancelBtn")?.addEventListener("click",  () => close(false));
    $("modalConfirmBtn")?.addEventListener("click", () => close(true));
    $("modalOverlay")?.addEventListener("click", (e) => {
      if (e.target === $("modalOverlay")) close(false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("modalOverlay").hidden) close(false);
    });
  }

  function confirm(message, title = "Are you sure?", confirmLabel = "Confirm") {
    return new Promise((resolve) => {
      resolveFn = resolve;
      const titleEl   = $("modalTitle");
      const messageEl = $("modalMessage");
      const confirmBtn = $("modalConfirmBtn");
      if (titleEl)   titleEl.textContent   = title;
      if (messageEl) messageEl.textContent = message;
      if (confirmBtn) confirmBtn.textContent = confirmLabel;
      const overlay = $("modalOverlay");
      if (overlay) overlay.hidden = false;
    });
  }

  function close(result) {
    const overlay = $("modalOverlay");
    if (overlay) overlay.hidden = true;
    if (resolveFn) resolveFn(result);
    resolveFn = null;
  }

  return { init, confirm };
})();

// ═══════════════════════════════════════════════════════════════
// DARK MODE
// ═══════════════════════════════════════════════════════════════

const darkMode = (() => {
  const KEY = "meeting_ai_theme";

  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(KEY, theme);
    const btn = $("darkModeToggle");
    if (btn) btn.title = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
  }

  function init() {
    const saved  = localStorage.getItem(KEY);
    const system = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    apply(saved || system);
    $("darkModeToggle")?.addEventListener("click", toggle);
  }

  function toggle() {
    const current = document.documentElement.getAttribute("data-theme");
    apply(current === "dark" ? "light" : "dark");
  }

  return { init, toggle, apply };
})();

// ═══════════════════════════════════════════════════════════════
// SIDEBAR
// ═══════════════════════════════════════════════════════════════

const sidebar = (() => {
  const KEY = "meeting_ai_sidebar";
  let isMobileOpen = false;

  function init() {
    const saved = localStorage.getItem(KEY);
    if (saved === "collapsed") collapse(false);

    $("sidebarCollapseBtn")?.addEventListener("click", () => {
      const app = $("app");
      if (app.classList.contains("sidebar-collapsed")) expand();
      else collapse();
    });

    $("sidebarToggleBtn")?.addEventListener("click", toggleMobile);

    $("sidebarBackdrop")?.addEventListener("click", closeMobile);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && isMobileOpen) closeMobile();
    });
  }

  function collapse(save = true) {
    $("app")?.classList.add("sidebar-collapsed");
    if (save) localStorage.setItem(KEY, "collapsed");
  }

  function expand() {
    $("app")?.classList.remove("sidebar-collapsed");
    localStorage.setItem(KEY, "expanded");
  }

  function toggleMobile() {
    isMobileOpen ? closeMobile() : openMobile();
  }

  function openMobile() {
    isMobileOpen = true;
    $("app")?.classList.add("mobile-open");
    $("sidebarToggleBtn")?.setAttribute("aria-expanded", "true");
  }

  function closeMobile() {
    isMobileOpen = false;
    $("app")?.classList.remove("mobile-open");
    $("sidebarToggleBtn")?.setAttribute("aria-expanded", "false");
  }

  return { init, collapse, expand, closeMobile };
})();

// ═══════════════════════════════════════════════════════════════
// RECORDING TIMER
// ═══════════════════════════════════════════════════════════════

const recTimer = (() => {
  let interval = null;
  let seconds  = 0;

  function tick() {
    seconds++;
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    const timerEl = $("recTimer");
    if (timerEl) timerEl.textContent = `${m}:${String(s).padStart(2, "0")}`;
  }

  return {
    start() {
      seconds = 0;
      const timerEl = $("recTimer");
      if (timerEl) timerEl.textContent = "0:00";
      interval = setInterval(tick, 1000);
    },
    stop() {
      if (interval) clearInterval(interval);
      interval = null;
    },
    reset() {
      this.stop();
      seconds = 0;
      const timerEl = $("recTimer");
      if (timerEl) timerEl.textContent = "";
    },
  };
})();

// ═══════════════════════════════════════════════════════════════
// DRAG-AND-DROP UPLOAD
// ═══════════════════════════════════════════════════════════════

function initDropZone() {
  const zone       = $("dropZone");
  const fileInput  = $("uploadFile");
  const emptyEl    = $("dropZoneEmpty");
  const fileEl     = $("dropZoneFile");
  const nameEl     = $("dropFileName");
  const sizeEl     = $("dropFileSize");
  const clearBtn   = $("dropFileClear");
  const processBtn = $("uploadProcessBtn");

  if (!zone) return;

  function showFile(file) {
    if (!file) return clearFile();
    if (emptyEl) emptyEl.style.display = "none";
    if (fileEl)  fileEl.style.display  = "flex";
    if (nameEl)  nameEl.textContent    = file.name;
    if (sizeEl)  sizeEl.textContent    = fmtFileSize(file.size);
    if (processBtn) processBtn.disabled = false;
  }

  function clearFile() {
    if (emptyEl) emptyEl.style.display = "flex";
    if (fileEl)  fileEl.style.display  = "none";
    if (processBtn) processBtn.disabled = true;
    if (fileInput) {
      fileInput.value = "";
      // Re-create input to allow same file re-selection
      const dt = new DataTransfer();
      fileInput.files = dt.files;
    }
  }

  // File input change
  fileInput?.addEventListener("change", () => {
    const f = fileInput.files?.[0];
    if (f) showFile(f);
    else clearFile();
  });

  // Clear button
  clearBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    clearFile();
  });

  // Drag events
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("drag-over");
  });

  zone.addEventListener("dragleave", (e) => {
    if (!zone.contains(e.relatedTarget)) zone.classList.remove("drag-over");
  });

  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const files = e.dataTransfer.files;
    if (files.length) {
      const dt = new DataTransfer();
      dt.items.add(files[0]);
      fileInput.files = dt.files;
      showFile(files[0]);
    }
  });

  // Keyboard accessibility
  zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput?.click();
    }
  });
}

// ═══════════════════════════════════════════════════════════════
// VIEW MANAGEMENT
// ═══════════════════════════════════════════════════════════════

const VIEW_LABELS = { setup: "Setup", record: "Record", intel: "Intelligence" };

function setActiveNav() {
  const map = { setup: "navSetup", record: "navRecord", intel: "navIntel" };
  for (const key of Object.values(map)) {
    $(key)?.classList.remove("active");
    $(key)?.setAttribute("aria-current", "false");
  }
  const activeId = map[state.view];
  $(activeId)?.classList.add("active");
  $(activeId)?.setAttribute("aria-current", "page");

  const breadcrumb = $("breadcrumbView");
  if (breadcrumb) breadcrumb.textContent = VIEW_LABELS[state.view] || state.view;
}

function showView(view) {
  state.view = view;
  $("viewSetup").hidden  = view !== "setup";
  $("viewRecord").hidden = view !== "record";
  $("viewIntel").hidden  = view !== "intel";
  setActiveNav();
  // Close mobile sidebar when navigating
  sidebar.closeMobile();
  // Scroll to top
  $("mainContent")?.scrollTo?.(0, 0);
}

// ═══════════════════════════════════════════════════════════════
// PROJECT PERSISTENCE
// ═══════════════════════════════════════════════════════════════

function persistSelectedProject() {
  try {
    localStorage.setItem(
      "meeting_ai_selected_project",
      JSON.stringify({ id: state.selectedProjectId, name: state.selectedProjectName })
    );
  } catch {}
}

function restoreSelectedProject() {
  try {
    const raw = localStorage.getItem("meeting_ai_selected_project");
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (parsed?.id) {
      state.selectedProjectId   = Number(parsed.id);
      state.selectedProjectName = parsed.name || null;
    }
  } catch {}
}

function updateSelectedProjectLabels() {
  const p     = state.projects.find((x) => x.id === state.selectedProjectId);
  const label = state.selectedProjectName || (state.selectedProjectId ? "Project" : "—");

  const els = [
    $("selectedProjectLabel"),
    $("intelProjectLabel"),
    $("topbarProjectName"),
  ];
  for (const el of els) if (el) el.textContent = label;

  const badge = $("topbarProjectBadge");
  if (badge) badge.style.display = state.selectedProjectId ? "flex" : "none";

  // Update archive button label to reflect current project state
  const archiveBtn = $("archiveProjectBtn");
  if (archiveBtn) {
    const svg = archiveBtn.querySelector("svg")?.outerHTML || "";
    archiveBtn.innerHTML = svg + (p?.archived ? " Unarchive" : " Archive");
  }
}

// ═══════════════════════════════════════════════════════════════
// PROJECT TREE (Sidebar)
// ═══════════════════════════════════════════════════════════════

function renderProjectTree(filterText = "") {
  const root = $("projectTree");
  if (!root) return;
  root.innerHTML = "";

  const q     = (filterText || "").trim().toLowerCase();
  const items = (state.projects || []).filter(
    (p) => !q || (p.name || "").toLowerCase().includes(q)
  );

  if (!items.length) {
    root.innerHTML = `<div class="muted" style="font-size:12px;color:var(--sidebar-text-dim);padding:8px 6px;">No projects found.</div>`;
    return;
  }

  for (const p of items) {
    const el    = document.createElement("div");
    el.className = "project-node" + (p.id === state.selectedProjectId ? " active" : "");
    el.setAttribute("role", "listitem");
    el.setAttribute("tabindex", "0");
    el.setAttribute("title", p.name);
    const initials = (p.name || "?").slice(0, 2).toUpperCase();

    el.innerHTML = `
      <div class="project-icon" aria-hidden="true">${escapeHtml(initials)}</div>
      <div class="project-meta">
        <div class="project-name">${escapeHtml(p.name)}</div>
        ${p.description ? `<div class="project-desc">${escapeHtml(String(p.description).slice(0, 55))}${p.description.length > 55 ? "…" : ""}</div>` : ""}
      </div>
    `;

    const activate = async () => {
      state.selectedProjectId   = p.id;
      state.selectedProjectName = p.name;
      $("projectSelect").value  = String(p.id);
      persistSelectedProject();
      updateSelectedProjectLabels();
      renderProjectTree($("projectSearch").value);
      showView("intel");
      try { await loadHistory(); } catch (e) { toast.error(e.message); }
    };

    el.addEventListener("click", activate);
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); } });
    root.appendChild(el);
  }
}

// ═══════════════════════════════════════════════════════════════
// CORE API WRAPPER
// ═══════════════════════════════════════════════════════════════

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await res.text();
  let payload;
  try   { payload = text ? JSON.parse(text) : {}; }
  catch { payload = { raw: text }; }
  if (!res.ok) {
    const msg = payload?.error || `HTTP ${res.status}`;
    throw new Error(`${msg}${payload?.details ? `: ${payload.details}` : ""}`);
  }
  return payload;
}

// ═══════════════════════════════════════════════════════════════
// PROJECTS API
// ═══════════════════════════════════════════════════════════════

async function refreshProjects() {
  const showArchived = $("showArchivedToggle")?.checked ? "1" : "0";
  const payload      = await api(`/api/projects?archived=${showArchived}`, { method: "GET" });
  state.projects     = payload.projects || [];

  const sel = $("projectSelect");
  sel.innerHTML = "";
  if (!state.projects.length) {
    const opt = document.createElement("option");
    opt.value       = "";
    opt.textContent = "— No projects yet —";
    sel.appendChild(opt);
  }
  for (const p of state.projects) {
    const opt = document.createElement("option");
    opt.value       = p.id;
    opt.textContent = p.name;
    sel.appendChild(opt);
  }

  if (state.selectedProjectId && state.projects.some((p) => p.id === state.selectedProjectId)) {
    sel.value = String(state.selectedProjectId);
    const p   = state.projects.find((x) => x.id === state.selectedProjectId);
    state.selectedProjectName = p?.name || state.selectedProjectName;
  } else if (state.projects.length) {
    state.selectedProjectId   = Number(sel.value);
    const p = state.projects.find((x) => x.id === state.selectedProjectId);
    state.selectedProjectName = p?.name || null;
  } else {
    state.selectedProjectId   = null;
    state.selectedProjectName = null;
  }

  updateSelectedProjectLabels();
  renderProjectTree($("projectSearch").value);
}

async function createProject() {
  const name        = $("projectName").value.trim();
  const description = $("projectDesc").value.trim();
  if (!name) throw new Error("Project name is required.");

  const payload = await api("/api/projects", {
    method: "POST",
    body:   JSON.stringify({ name, description }),
  });

  $("projectName").value = "";
  $("projectDesc").value = "";
  await refreshProjects();
  $("projectSelect").value    = String(payload.project.id);
  state.selectedProjectId     = payload.project.id;
  state.selectedProjectName   = payload.project.name;
  persistSelectedProject();
  updateSelectedProjectLabels();
  renderProjectTree($("projectSearch").value);
  toast.success(`Project "${payload.project.name}" created.`);
}

// ═══════════════════════════════════════════════════════════════
// PARTICIPANTS
// ═══════════════════════════════════════════════════════════════

async function loadParticipants() {
  if (!state.selectedProjectId) return;
  const payload    = await api(`/api/projects/${state.selectedProjectId}/participants`, { method: "GET" });
  const participants = payload?.project?.participants;
  state.participants = Array.isArray(participants) ? participants : [];
  renderParticipants();
}

async function saveParticipants() {
  if (!state.selectedProjectId) throw new Error("Select a project first.");
  await api(`/api/projects/${state.selectedProjectId}/participants`, {
    method: "PUT",
    body:   JSON.stringify({ participants: state.participants }),
  });
  toast.success("Participants saved.");
  renderParticipants();
}

function renderParticipants() {
  const root = $("participantsList");
  if (!root) return;
  root.innerHTML = "";

  if (!state.participants.length) {
    root.innerHTML = `<span style="font-size:13px;color:var(--text-muted);">No participants yet. Add names like Alice, Bob…</span>`;
    return;
  }

  for (const p of state.participants) {
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.setAttribute("role", "listitem");
    pill.innerHTML = `
      <span>${escapeHtml(p)}</span>
      <button class="pill-remove" data-name="${escapeHtml(p)}" aria-label="Remove ${escapeHtml(p)}" title="Remove">×</button>
    `;
    pill.querySelector("button").addEventListener("click", () => {
      state.participants = state.participants.filter((x) => x !== p);
      renderParticipants();
    });
    root.appendChild(pill);
  }
}

// ═══════════════════════════════════════════════════════════════
// NAME ALIASES
// ═══════════════════════════════════════════════════════════════

function renderNameAliases() {
  const root = $("nameAliasesList");
  if (!root) return;
  root.innerHTML = "";

  const entries = Object.entries(state.name_aliases || {});
  if (!entries.length) {
    root.innerHTML = `<span style="font-size:13px;color:var(--text-muted);">No corrections yet. e.g. map "spkr_1" → "Alice".</span>`;
    return;
  }

  for (const [fromVal, toVal] of entries) {
    const row = document.createElement("div");
    row.className = "alias-row";
    row.innerHTML = `
      <input type="text" data-alias-from placeholder="Transcript shows" value="${escapeHtml(fromVal)}" class="form-input" aria-label="Original name" />
      <span class="alias-arrow" aria-hidden="true">→</span>
      <input type="text" data-alias-to placeholder="Display as" value="${escapeHtml(toVal)}" class="form-input" aria-label="Display name" />
      <button class="btn btn-danger-outline btn-sm" data-alias-remove="${escapeHtml(fromVal)}" aria-label="Remove alias">Remove</button>
    `;
    row.querySelector("[data-alias-from]").addEventListener("change", (e) => {
      const newFrom = e.target.value.trim();
      if (newFrom && fromVal !== newFrom) {
        delete state.name_aliases[fromVal];
        state.name_aliases[newFrom] = toVal;
        renderNameAliases();
      }
    });
    row.querySelector("[data-alias-to]").addEventListener("change", (e) => {
      const newTo = e.target.value.trim();
      if (newTo !== toVal) {
        state.name_aliases[fromVal] = newTo;
      }
    });
    row.querySelector("[data-alias-remove]").addEventListener("click", () => {
      delete state.name_aliases[fromVal];
      renderNameAliases();
    });
    root.appendChild(row);
  }
}

function addNameAliasRow() {
  const fromInput = $("nameAliasFromInput");
  const toInput   = $("nameAliasToInput");
  if (!fromInput || !toInput) return;
  const fromVal = fromInput.value.trim();
  const toVal   = toInput.value.trim();
  if (!fromVal || !toVal) { toast.warning("Fill in both fields."); return; }
  state.name_aliases[fromVal] = toVal;
  fromInput.value = "";
  toInput.value   = "";
  renderNameAliases();
}

async function saveNameAliases() {
  if (!state.selectedProjectId) { toast.warning("Select a project first."); return; }
  await api(`/api/projects/${state.selectedProjectId}`, {
    method: "PATCH",
    body:   JSON.stringify({ name_aliases: state.name_aliases }),
  });
  toast.success("Name corrections saved.");
}

// ═══════════════════════════════════════════════════════════════
// SPEAKER SEGMENTS
// ═══════════════════════════════════════════════════════════════

function renderSegmentsEditor(segments) {
  const root = $("segmentsEditor");
  if (!root) return;
  root.innerHTML = "";
  $("segmentsStatus").textContent = "";

  if (!segments || !segments.length) {
    root.innerHTML = `<div class="empty-state empty-state-sm"><p>No segments yet. Click "Generate" after processing a meeting.</p></div>`;
    $("saveSegmentsBtn").disabled = true;
    return;
  }

  const speakerOptions = ["(Unassigned)", ...state.participants];

  for (const seg of segments) {
    const el = document.createElement("div");
    el.className = "seg-row";
    el.setAttribute("role", "listitem");
    const speaker = seg.speaker || "";

    el.innerHTML = `
      <div>
        <div class="seg-meta">Segment ${escapeHtml(String(seg.idx))}</div>
        <select data-idx="${seg.idx}" class="form-select form-select-sm" aria-label="Speaker for segment ${seg.idx}">
          ${speakerOptions.map((opt) => {
            const val = opt === "(Unassigned)" ? "" : opt;
            return `<option value="${escapeHtml(val)}" ${val === speaker ? "selected" : ""}>${escapeHtml(opt)}</option>`;
          }).join("")}
        </select>
      </div>
      <div>
        <textarea data-text-idx="${seg.idx}" aria-label="Segment ${seg.idx} text">${escapeHtml(seg.text || "")}</textarea>
      </div>
    `;
    root.appendChild(el);
  }

  $("saveSegmentsBtn").disabled = false;
}

async function generateSegments() {
  if (!state.currentMeeting?.id) throw new Error("Open a meeting first.");
  const payload = await api(`/api/meetings/${state.currentMeeting.id}/speaker_segments/generate`, { method: "POST" });
  renderSegmentsEditor(payload.transcript?.speaker_segments || []);
  toast.success("Segments generated.");
}

async function saveSegments() {
  if (!state.currentMeeting?.id) throw new Error("Open a meeting first.");
  const root    = $("segmentsEditor");
  const selects = Array.from(root.querySelectorAll("select[data-idx]"));
  const segs    = selects.map((sel) => {
    const idx     = Number(sel.getAttribute("data-idx"));
    const speaker = sel.value || null;
    const ta      = root.querySelector(`textarea[data-text-idx="${idx}"]`);
    const text    = ta ? ta.value.trim() : "";
    return { idx, speaker, text };
  });

  const payload = await api(`/api/meetings/${state.currentMeeting.id}/speaker_segments`, {
    method: "PATCH",
    body:   JSON.stringify({ speaker_segments: segs }),
  });
  renderSegmentsEditor(payload.transcript?.speaker_segments || []);
  toast.success("Speaker labels saved.");
}

// ═══════════════════════════════════════════════════════════════
// STATS
// ═══════════════════════════════════════════════════════════════

function renderStats(stats) {
  if (!stats) return;
  const mc = $("statMeetingsCount");
  const pc = $("statPendingCount");
  const cc = $("statCompletedCount");
  const lm = $("statLastMeeting");
  if (mc) mc.textContent = stats.meetings_count                ?? "—";
  if (pc) pc.textContent = stats.pending_action_items_count    ?? "—";
  if (cc) cc.textContent = stats.completed_action_items_count  ?? "—";
  if (lm) lm.textContent = stats.last_meeting_at ? fmtDate(stats.last_meeting_at) : "—";
}

// ═══════════════════════════════════════════════════════════════
// ACTIVITY LOG
// ═══════════════════════════════════════════════════════════════

async function loadActivity() {
  if (!state.selectedProjectId) return;
  try {
    const payload = await api(`/api/projects/${state.selectedProjectId}/activity`, { method: "GET" });
    renderActivity(payload.activity || []);
  } catch {
    const root = $("activityLogList");
    if (root) root.innerHTML = `<div class="empty-state empty-state-sm"><p>Activity log unavailable.</p></div>`;
  }
}

function renderActivity(items) {
  const root = $("activityLogList");
  if (!root) return;
  root.innerHTML = "";

  if (!items.length) {
    root.innerHTML = `<div class="empty-state empty-state-sm"><p>No activity recorded yet.</p></div>`;
    return;
  }

  for (const item of items) {
    const el = document.createElement("div");
    el.className = "activity-item";
    el.setAttribute("role", "listitem");
    const ts = fmtDateTime(item.created_at || "");
    el.innerHTML = `
      <div class="activity-dot" aria-hidden="true"></div>
      <div class="activity-body">
        <div class="activity-action">${escapeHtml(item.action || "")}</div>
        ${item.details ? `<div class="activity-detail">${escapeHtml(item.details)}</div>` : ""}
        <div class="activity-detail text-xs" style="margin-top:2px;">${escapeHtml(ts)}</div>
      </div>
    `;
    root.appendChild(el);
  }
}

// ═══════════════════════════════════════════════════════════════
// PENDING / COMPLETED ACTION ITEMS
// ═══════════════════════════════════════════════════════════════

function renderPending(items) {
  const root = $("pendingItemsList");
  if (!root) return;
  root.innerHTML = "";

  // Reset selections on every re-render
  state.selectedAiIds.clear();
  const bulkBtn = $("bulkCompleteBtn");
  if (bulkBtn) bulkBtn.disabled = true;

  if (!items || !items.length) {
    root.innerHTML = `<div class="empty-state empty-state-sm"><p>No pending action items. Great work!</p></div>`;
    return;
  }

  for (const ai of items) {
    const el = document.createElement("div");
    el.className = "action-item";
    el.setAttribute("role", "listitem");
    const rementionedBadge = ai.last_rementioned_meeting_id
      ? `<span class="badge badge-warning">re-mentioned</span>`
      : "";

    el.innerHTML = `
      <label class="ai-checkbox-wrap" title="Select">
        <input type="checkbox" class="ai-select-cb" data-id="${ai.id}" />
      </label>
      <div class="action-item-body">
        <div class="action-item-title">${escapeHtml(fmtActionItem(ai))}</div>
        <div class="action-item-meta">
          <span class="badge ${statusBadge(ai.status)}">${escapeHtml(ai.status)}</span>
          ${rementionedBadge}
          ${ai.by_when ? `<span class="badge badge-default">Due ${escapeHtml(ai.by_when)}</span>` : ""}
        </div>
      </div>
      <div class="action-item-actions">
        <button class="btn btn-primary btn-sm complete-btn" aria-label="Mark as completed">
          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          Complete
        </button>
        <button class="btn btn-danger-outline btn-sm delete-btn" aria-label="Delete action item">
          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/></svg>
        </button>
      </div>
    `;

    el.querySelector(".ai-select-cb").addEventListener("change", (e) => {
      const id = Number(e.target.dataset.id);
      if (e.target.checked) state.selectedAiIds.add(id);
      else                   state.selectedAiIds.delete(id);
      if (bulkBtn) bulkBtn.disabled = state.selectedAiIds.size === 0;
    });

    el.querySelector(".complete-btn").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await api(`/api/action_items/${ai.id}`, {
          method: "PATCH",
          body:   JSON.stringify({ status: "completed", resolved_in_meeting_id: state.meetingId }),
        });
        toast.success("Marked as completed.");
        await loadHistory();
      } catch (err) {
        toast.error(`Error: ${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });

    el.querySelector(".delete-btn").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      const ok  = await modal.confirm("Delete this action item?", "Delete Action Item", "Delete");
      if (!ok) return;
      btn.disabled = true;
      try {
        await api(`/api/action_items/${ai.id}`, { method: "DELETE" });
        toast.success("Action item deleted.");
        await loadHistory();
      } catch (err) {
        toast.error(`Error: ${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });

    root.appendChild(el);
  }
}

function renderCompleted(items) {
  const root = $("completedItemsList");
  if (!root) return;
  root.innerHTML = "";

  if (!items || !items.length) {
    root.innerHTML = `<div class="empty-state empty-state-sm"><p>No completed items to show.</p></div>`;
    return;
  }

  for (const ai of items) {
    const el = document.createElement("div");
    el.className = "action-item";
    el.setAttribute("role", "listitem");

    el.innerHTML = `
      <div class="action-item-body">
        <div class="action-item-title" style="text-decoration:line-through;opacity:0.7;">${escapeHtml(fmtActionItem(ai))}</div>
        <div class="action-item-meta">
          <span class="badge badge-success">completed</span>
        </div>
      </div>
      <div class="action-item-actions">
        <button class="btn btn-ghost btn-sm reopen-btn" aria-label="Re-open action item">Re-open</button>
        <button class="btn btn-danger-outline btn-sm delete-btn" aria-label="Delete">
          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/></svg>
        </button>
      </div>
    `;

    el.querySelector(".reopen-btn").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await api(`/api/action_items/${ai.id}`, {
          method: "PATCH",
          body:   JSON.stringify({ status: "pending", resolved_in_meeting_id: null }),
        });
        toast.info("Action item re-opened.");
        await loadHistory();
      } catch (err) {
        toast.error(`Error: ${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });

    el.querySelector(".delete-btn").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      const ok  = await modal.confirm("Delete this action item?", "Delete Action Item", "Delete");
      if (!ok) return;
      btn.disabled = true;
      try {
        await api(`/api/action_items/${ai.id}`, { method: "DELETE" });
        toast.success("Action item deleted.");
        await loadHistory();
      } catch (err) {
        toast.error(`Error: ${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });

    root.appendChild(el);
  }
}

// ═══════════════════════════════════════════════════════════════
// MEETING MINUTES
// ═══════════════════════════════════════════════════════════════

function renderMinutes(meeting) {
  const root = $("latestMinutes");
  if (!meeting) {
    root.innerHTML = `<div class="empty-state empty-state-sm"><p>Select a meeting to view minutes.</p></div>`;
    return;
  }

  state.currentMeeting = meeting;

  const notesEl = $("meetingNotesInput");
  if (notesEl) notesEl.value = meeting.notes || "";

  // Audio player
  const audioWrap = $("meetingAudioWrap");
  const audioEl   = $("meetingAudio");
  if (audioWrap && audioEl) {
    if (meeting.audio_path) {
      audioWrap.style.display = "flex";
      audioEl.src = `/api/meetings/${meeting.id}/audio`;
    } else {
      audioWrap.style.display = "none";
      audioEl.removeAttribute("src");
    }
  }

  const summary    = meeting.summary  || null;
  const transcript = meeting.transcript || null;
  const decisions  = summary?.decisions || [];
  const extracted  = summary?.action_items_extracted || [];

  const statusClass = statusBadge(meeting.status);

  let html = `
    <div class="minutes">
      <div class="minutes-meta">
        <span class="badge ${statusClass}">${escapeHtml(meeting.status)}</span>
        <span>Created: ${escapeHtml(fmtDateTime(meeting.created_at))}</span>
        ${meeting.processing_progress != null && meeting.status === "processing"
          ? `<span>Progress: ${meeting.processing_progress}%</span>` : ""}
      </div>

      <h4>Summary</h4>
      <p>${escapeHtml(summary?.summary_text || "(Not processed yet.)")}</p>

      <h4>Decisions</h4>
      ${decisions.length
        ? `<ul>${decisions.map((d) => `<li>${escapeHtml(d.text || JSON.stringify(d))}</li>`).join("")}</ul>`
        : `<p class="text-muted text-sm">No decisions extracted.</p>`}

      <h4>Action Items (this meeting)</h4>
      ${extracted.length
        ? `<ul>${extracted.map((ai) => {
            const carry = (ai.rementioned_in_meeting_id || ai.deduped)
              ? ` <span class="badge badge-warning">carry-forward</span>` : "";
            return `<li>${escapeHtml(fmtActionItem(ai))}${carry}</li>`;
          }).join("")}</ul>`
        : `<p class="text-muted text-sm">No action items extracted.</p>`}
  `;

  // Speaker transcript
  if (transcript?.speaker_segments?.length) {
    html += `
      <h4>Transcript (by speaker)</h4>
      <div class="transcript-section">
        ${transcript.speaker_segments.map((seg) => {
          const speaker = seg.speaker ? escapeHtml(seg.speaker) : "(Unassigned)";
          const text    = escapeHtml(seg.text || "").trim();
          return text
            ? `<div class="transcript-seg"><div class="transcript-speaker">${speaker}</div>${text}</div>`
            : "";
        }).filter(Boolean).join("")}
      </div>
    `;
  }

  if (!transcript?.speaker_segments?.length && transcript?.text) {
    html += `
      <h4>Transcript</h4>
      <div class="transcript-full">${escapeHtml(transcript.text || "")}</div>
    `;
  }

  html += `</div>`;
  root.innerHTML = html;

  // Render speaker editor from existing segments
  renderSegmentsEditor(transcript?.speaker_segments || []);
}

// ═══════════════════════════════════════════════════════════════
// MEETINGS LIST
// ═══════════════════════════════════════════════════════════════

function renderMeetingsList(meetings) {
  const root    = $("meetingsList");
  const emptyEl = $("meetingsEmpty");
  root.innerHTML = "";

  if (!meetings || !meetings.length) {
    if (emptyEl) emptyEl.style.display = "flex";
    return;
  }
  if (emptyEl) emptyEl.style.display = "none";

  for (const m of meetings) {
    const el    = document.createElement("div");
    el.className = "meeting-card";
    el.setAttribute("role", "listitem");
    const title      = m.title || "Untitled Meeting";
    const dateStr    = fmtDate(m.created_at);
    const badgeClass = statusBadge(m.status);

    el.innerHTML = `
      <div class="meeting-card-body">
        <div class="meeting-card-title" title="${escapeHtml(title)}">${escapeHtml(title)}</div>
        <div class="meeting-card-meta">
          <span class="badge ${badgeClass}"><span class="badge-dot"></span>${escapeHtml(m.status)}</span>
          <span class="badge badge-default">${escapeHtml(dateStr)}</span>
        </div>
      </div>
      <div class="meeting-card-actions">
        <button class="btn btn-primary btn-sm open-btn" aria-label="Open ${escapeHtml(title)}">Open</button>
        <button class="btn btn-ghost btn-sm dup-btn" aria-label="Duplicate meeting" title="Duplicate">
          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
        </button>
        <button class="btn btn-danger-outline btn-sm del-btn" aria-label="Delete meeting">
          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/></svg>
        </button>
      </div>
    `;

    // Open button
    el.querySelector(".open-btn").addEventListener("click", async () => {
      // Highlight selected card
      document.querySelectorAll(".meeting-card").forEach((c) => c.classList.remove("selected"));
      el.classList.add("selected");
      try {
        const payload    = await api(`/api/meetings/${m.id}`, { method: "GET" });
        state.meetingId  = payload.meeting.id;
        renderMinutes(payload.meeting);
      } catch (err) {
        toast.error(`Error: ${err.message}`);
      }
    });

    // Duplicate button
    el.querySelector(".dup-btn").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await api(`/api/meetings/${m.id}/duplicate`, { method: "POST" });
        toast.success("Meeting duplicated.");
        await loadHistory();
      } catch (err) {
        toast.error(`Error: ${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });

    // Delete button
    el.querySelector(".del-btn").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      const ok  = await modal.confirm(
        `Delete "${title}"? Action items will be kept but the meeting and its minutes will be removed.`,
        "Delete Meeting",
        "Delete"
      );
      if (!ok) return;
      btn.disabled = true;
      try {
        await api(`/api/meetings/${m.id}`, { method: "DELETE" });
        toast.success("Meeting deleted.");
        await loadHistory();
      } catch (err) {
        toast.error(`Error: ${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });

    root.appendChild(el);
  }
}

// ═══════════════════════════════════════════════════════════════
// LOAD HISTORY (main data fetch for Intel view)
// ═══════════════════════════════════════════════════════════════

async function loadHistory() {
  if (!state.selectedProjectId) throw new Error("Select a project first.");

  const q      = $("meetingSearchQ")?.value?.trim()  || "";
  const from   = $("meetingFilterFrom")?.value        || "";
  const to     = $("meetingFilterTo")?.value          || "";
  const status = $("meetingFilterStatus")?.value      || "";

  let url    = `/api/projects/${state.selectedProjectId}/history`;
  const params = new URLSearchParams();
  if (q)      params.set("q",      q);
  if (from)   params.set("from",   from);
  if (to)     params.set("to",     to);
  if (status) params.set("status", status);
  if (params.toString()) url += "?" + params.toString();

  const payload = await api(url, { method: "GET" });

  // Project description
  const descEl = $("projectDescription");
  if (descEl && payload.project?.description) {
    descEl.textContent = payload.project.description;
    descEl.style.display = "block";
  } else if (descEl) {
    descEl.style.display = "none";
  }

  // Stats
  renderStats(payload.stats);

  // Meetings list
  const meetings = payload.meetings || [];
  renderMeetingsList(meetings);

  // Open most recent processed meeting automatically
  if (meetings.length && payload.meetings[0].status === "processed") {
    renderMinutes(payload.meetings[0]);
  } else if (meetings.length) {
    renderMinutes(meetings[0]);
  }

  // Pending action items
  renderPending(payload.pending_action_items || []);

  // Participants + aliases
  await loadParticipants();
  state.name_aliases = payload.project?.name_aliases || {};
  if (typeof state.name_aliases !== "object" || state.name_aliases === null) {
    state.name_aliases = {};
  }
  renderNameAliases();

  // Completed items (only if toggle is on)
  const showCompleted = $("showCompletedToggle")?.checked;
  if (showCompleted) {
    const completed = await api(`/api/projects/${state.selectedProjectId}/action_items?status=completed`, { method: "GET" });
    renderCompleted(completed.action_items || []);
  } else {
    renderCompleted([]);
  }
}

// ═══════════════════════════════════════════════════════════════
// RECORDING
// ═══════════════════════════════════════════════════════════════

function setRecordingActive(active) {
  const card = $("recordCard");
  if (active) {
    card?.classList.add("recording");
    recTimer.start();
  } else {
    card?.classList.remove("recording");
    recTimer.stop();
  }
}

async function startRecording() {
  if (!state.selectedProjectId) throw new Error("Create or select a project first.");

  $("meetingStatus").textContent = "Starting meeting…";
  const title   = $("meetingTitle").value.trim();
  const started = await api("/api/meetings/start", {
    method: "POST",
    body:   JSON.stringify({ project_id: state.selectedProjectId, title }),
  });
  state.meetingId = started.meeting.id;

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  state.stream = stream;

  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
  state.mimeType   = candidates.find((t) => MediaRecorder.isTypeSupported(t)) || "";

  state.chunks = [];
  const rec    = new MediaRecorder(stream, state.mimeType ? { mimeType: state.mimeType } : undefined);
  state.recorder = rec;

  rec.ondataavailable = (e) => { if (e.data?.size > 0) state.chunks.push(e.data); };

  rec.onstop = async () => {
    setRecordingActive(false);
    try {
      const blob = new Blob(state.chunks, { type: state.mimeType || "audio/webm" });
      const url  = URL.createObjectURL(blob);
      const playback = $("playback");
      if (playback) { playback.src = url; playback.hidden = false; }

      $("recStatus").textContent    = "Uploading…";
      $("meetingStatus").textContent = "Stopping meeting and uploading audio…";

      await api(`/api/meetings/${state.meetingId}/stop`, { method: "POST", body: JSON.stringify({}) });

      const fd = new FormData();
      fd.append("audio", blob, "recording.webm");
      const uploadRes = await fetch(`/api/meetings/${state.meetingId}/upload_audio`, { method: "POST", body: fd });
      if (!uploadRes.ok) throw new Error(await uploadRes.text() || `Upload failed (${uploadRes.status})`);

      $("recStatus").textContent    = "Processing…";
      $("meetingStatus").textContent = "Processing — transcribing and analysing…";

      await api(`/api/meetings/${state.meetingId}/process`, { method: "POST", body: JSON.stringify({ async: true }) });

      await pollUntilDone(state.meetingId, (m) => {
        const pct   = m.processing_progress ?? 0;
        const stage = m.processing_stage    || "processing";
        $("recStatus").textContent    = `${stage} (${pct}%)`;
        $("meetingStatus").textContent = `Processing… ${pct}% — ${stage}`;
      });

      $("recStatus").textContent    = "Done!";
      $("meetingStatus").textContent = "";
      toast.success("Meeting processed successfully!");
      $("viewIntelBtn").disabled = false;
      showView("intel");
      await loadHistory();
    } catch (err) {
      $("recStatus").textContent    = "Error";
      $("meetingStatus").textContent = `Error: ${err.message}`;
      toast.error(`Processing failed: ${err.message}`);
    } finally {
      if (state.stream) { for (const t of state.stream.getTracks()) t.stop(); }
      state.stream = null;
      $("startBtn").disabled = false;
      $("stopBtn").disabled  = true;
    }
  };

  rec.start();
  setRecordingActive(true);
  $("recStatus").textContent    = "Recording…";
  $("meetingStatus").textContent = "Recording in progress…";
  $("startBtn").disabled = true;
  $("stopBtn").disabled  = false;
}

async function stopRecording() {
  if (!state.recorder) return;
  $("recStatus").textContent = "Stopping…";
  $("stopBtn").disabled      = true;
  state.recorder.stop();
}

// ═══════════════════════════════════════════════════════════════
// UPLOAD & PROCESS
// ═══════════════════════════════════════════════════════════════

async function uploadAndProcess() {
  const file = $("uploadFile").files?.[0];
  if (!file)                     throw new Error("Choose an audio file first.");
  if (!state.selectedProjectId) throw new Error("Select a project first.");

  const progressWrap = $("uploadProgress");
  const progressFill = $("progressFill");
  const progressStage = $("progressStage");
  const statusEl     = $("uploadStatus");

  if (progressWrap) progressWrap.style.display = "block";
  if (statusEl)     statusEl.textContent        = "";

  const setProgress = (pct, stage) => {
    if (progressFill) { progressFill.style.width = `${pct}%`; progressFill.parentElement?.setAttribute("aria-valuenow", pct); }
    if (progressStage) progressStage.textContent = stage || "";
    if (statusEl)     statusEl.textContent        = stage ? `${stage}…` : "";
  };

  setProgress(5, "Creating meeting");

  const title   = $("uploadTitle").value.trim() || file.name;
  const started = await api("/api/meetings/start", {
    method: "POST",
    body:   JSON.stringify({ project_id: state.selectedProjectId, title }),
  });
  state.meetingId = started.meeting.id;

  setProgress(10, "Stopping");
  await api(`/api/meetings/${state.meetingId}/stop`, { method: "POST", body: JSON.stringify({}) });

  setProgress(20, "Uploading audio");
  const fd = new FormData();
  fd.append("audio", file, file.name);
  const uploadRes = await fetch(`/api/meetings/${state.meetingId}/upload_audio`, { method: "POST", body: fd });
  if (!uploadRes.ok) throw new Error(await uploadRes.text());

  setProgress(35, "Starting processing");
  await api(`/api/meetings/${state.meetingId}/process`, { method: "POST", body: JSON.stringify({ async: true }) });

  await pollUntilDone(state.meetingId, (m) => {
    const pct   = m.processing_progress ?? 35;
    const stage = m.processing_stage    || "processing";
    setProgress(35 + Math.floor(pct * 0.65), stage);
  });

  setProgress(100, "Done");
  if (progressWrap) setTimeout(() => { progressWrap.style.display = "none"; }, 1500);
  if (statusEl) statusEl.textContent = "";

  toast.success("Meeting uploaded and processed!");
  showView("intel");
  await loadHistory();
}

// ═══════════════════════════════════════════════════════════════
// POLLING
// ═══════════════════════════════════════════════════════════════

async function pollUntilDone(meetingId, onUpdate) {
  const maxMs = 60 * 60 * 1000;
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    const payload = await api(`/api/meetings/${meetingId}`, { method: "GET" });
    const m       = payload.meeting;
    if (onUpdate) onUpdate(m);
    if (m.status === "processed") { renderMinutes(m); return m; }
    if (m.status === "failed")    { throw new Error(m.processing_error || "Processing failed."); }
    await new Promise((r) => setTimeout(r, 1500));
  }
  throw new Error("Processing timed out.");
}

// ═══════════════════════════════════════════════════════════════
// EVENT WIRING
// ═══════════════════════════════════════════════════════════════

function wire() {
  // ── Navigation ──────────────────────────────────────────────
  $("navSetup").addEventListener("click", () => showView("setup"));
  $("navRecord").addEventListener("click", () => showView("record"));
  $("navIntel").addEventListener("click", async () => {
    showView("intel");
    if (state.selectedProjectId) {
      try { await loadHistory(); } catch (e) { toast.error(e.message); }
    }
  });

  // ── Sidebar project search ───────────────────────────────────
  $("projectSearch").addEventListener("input", (e) => renderProjectTree(e.target.value));

  $("refreshSidebarBtn")?.addEventListener("click", async () => {
    try { await refreshProjects(); } catch (e) { toast.error(e.message); }
  });

  // ── Backup ──────────────────────────────────────────────────
  $("downloadBackupBtn")?.addEventListener("click", () => {
    window.location.href = "/api/backup";
  });

  // ── Setup view ───────────────────────────────────────────────
  $("createProjectBtn").addEventListener("click", async () => {
    const btn = $("createProjectBtn");
    btn.disabled = true;
    try {
      await createProject();
    } catch (e) {
      toast.error(e.message);
      $("projectStatus").textContent = `Error: ${e.message}`;
    } finally {
      btn.disabled = false;
    }
  });

  $("refreshProjectsBtn").addEventListener("click", async () => {
    try { await refreshProjects(); toast.info("Projects refreshed."); }
    catch (e) { toast.error(e.message); }
  });

  $("showArchivedToggle").addEventListener("change", async () => {
    try { await refreshProjects(); } catch (e) { toast.error(e.message); }
  });

  $("useProjectBtn").addEventListener("click", () => {
    if (!state.selectedProjectId) { toast.warning("Select a project first."); return; }
    const p = state.projects.find((x) => x.id === state.selectedProjectId);
    state.selectedProjectName = p?.name || state.selectedProjectName;
    persistSelectedProject();
    updateSelectedProjectLabels();
    showView("record");
  });

  $("archiveProjectBtn")?.addEventListener("click", async () => {
    if (!state.selectedProjectId) { toast.warning("Select a project first."); return; }
    const p          = state.projects.find((x) => x.id === state.selectedProjectId);
    const isArchived = p?.archived;
    const action     = isArchived ? "Unarchive" : "Archive";
    const ok = await modal.confirm(
      `${action} "${p?.name || "this project"}"?`,
      `${action} Project`,
      action,
    );
    if (!ok) return;
    try {
      await api(`/api/projects/${state.selectedProjectId}`, {
        method: "PATCH",
        body:   JSON.stringify({ archived: !isArchived }),
      });
      toast.success(`Project ${action.toLowerCase()}d.`);
      if (!isArchived) {
        state.selectedProjectId   = null;
        state.selectedProjectName = null;
        persistSelectedProject();
      }
      await refreshProjects();
      updateSelectedProjectLabels();
    } catch (e) {
      toast.error(`Error: ${e.message}`);
    }
  });

  $("deleteProjectBtn").addEventListener("click", async () => {
    if (!state.selectedProjectId) { toast.warning("Select a project first."); return; }
    const p  = state.projects.find((x) => x.id === state.selectedProjectId);
    const ok = await modal.confirm(
      `Delete "${p?.name || "this project"}"? All meetings and action items inside it will be removed permanently.`,
      "Delete Project",
      "Delete"
    );
    if (!ok) return;
    try {
      await api(`/api/projects/${state.selectedProjectId}`, { method: "DELETE" });
      state.selectedProjectId   = null;
      state.selectedProjectName = null;
      persistSelectedProject();
      updateSelectedProjectLabels();
      await refreshProjects();
      toast.success("Project deleted.");
      $("projectStatus").textContent = "";
    } catch (e) {
      toast.error(`Error: ${e.message}`);
    }
  });

  $("projectSelect").addEventListener("change", (e) => {
    state.selectedProjectId   = Number(e.target.value);
    const p = state.projects.find((x) => x.id === state.selectedProjectId);
    state.selectedProjectName = p?.name || null;
    persistSelectedProject();
    updateSelectedProjectLabels();
    renderProjectTree($("projectSearch").value);
  });

  // ── Record view ──────────────────────────────────────────────
  $("startBtn").addEventListener("click", async () => {
    $("viewIntelBtn").disabled = true;
    try { await startRecording(); }
    catch (e) {
      setRecordingActive(false);
      $("recStatus").textContent    = "Ready to record";
      $("meetingStatus").textContent = `Error: ${e.message}`;
      $("startBtn").disabled = false;
      $("stopBtn").disabled  = true;
      toast.error(e.message);
    }
  });

  $("stopBtn").addEventListener("click", async () => {
    try { await stopRecording(); }
    catch (e) { toast.error(e.message); }
  });

  $("viewIntelBtn").addEventListener("click", async () => {
    showView("intel");
    try { if (state.selectedProjectId) await loadHistory(); } catch (e) { toast.error(e.message); }
  });

  $("uploadProcessBtn").addEventListener("click", async () => {
    const btn = $("uploadProcessBtn");
    btn.disabled = true;
    try {
      await uploadAndProcess();
    } catch (e) {
      $("uploadStatus").textContent = `Error: ${e.message}`;
      toast.error(e.message);
      const progressWrap = $("uploadProgress");
      if (progressWrap) progressWrap.style.display = "none";
    } finally {
      btn.disabled = false;
    }
  });

  // ── Intelligence view ────────────────────────────────────────
  $("loadHistoryBtn").addEventListener("click", async () => {
    const btn = $("loadHistoryBtn");
    btn.disabled = true;
    try { await loadHistory(); }
    catch (e) { toast.error(e.message); }
    finally { btn.disabled = false; }
  });

  // Search + filter changes (debounced)
  let searchDebounce;
  $("meetingSearchQ")?.addEventListener("input", () => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(async () => {
      try { if (state.selectedProjectId) await loadHistory(); } catch {}
    }, 350);
  });

  $("meetingFilterFrom")?.addEventListener("change",   async () => { try { await loadHistory(); } catch {} });
  $("meetingFilterTo")?.addEventListener("change",     async () => { try { await loadHistory(); } catch {} });
  $("meetingFilterStatus")?.addEventListener("change", async () => { try { await loadHistory(); } catch {} });

  $("showCompletedToggle").addEventListener("change", async () => {
    try { await loadHistory(); } catch (e) { toast.error(e.message); }
  });

  // Download PDF
  $("printBtn").addEventListener("click", () => {
    if (!state.currentMeeting?.id) { toast.warning("Open a meeting first."); return; }
    window.location.href = `/api/meetings/${state.currentMeeting.id}/export/pdf`;
  });

  // Bulk complete
  $("bulkCompleteBtn")?.addEventListener("click", async () => {
    if (!state.selectedAiIds.size) return;
    const ids = [...state.selectedAiIds];
    const ok  = await modal.confirm(
      `Mark ${ids.length} action item${ids.length > 1 ? "s" : ""} as completed?`,
      "Complete Selected",
      "Mark Complete",
    );
    if (!ok) return;
    const btn  = $("bulkCompleteBtn");
    btn.disabled = true;
    try {
      const res = await api("/api/action_items/bulk_complete", {
        method: "POST",
        body:   JSON.stringify({
          action_item_ids:        ids,
          resolved_in_meeting_id: state.meetingId || null,
        }),
      });
      toast.success(`${res.updated} action item${res.updated !== 1 ? "s" : ""} marked as completed.`);
      state.selectedAiIds.clear();
      await loadHistory();
    } catch (e) {
      toast.error(`Error: ${e.message}`);
      btn.disabled = false;
    }
  });

  // Notes save
  $("saveMeetingNotesBtn").addEventListener("click", async () => {
    if (!state.currentMeeting?.id) { toast.warning("Open a meeting first."); return; }
    try {
      await api(`/api/meetings/${state.currentMeeting.id}`, {
        method: "PATCH",
        body:   JSON.stringify({ notes: $("meetingNotesInput").value }),
      });
      toast.success("Notes saved.");
    } catch (e) {
      toast.error(`Error: ${e.message}`);
    }
  });

  // Participants
  $("addParticipantBtn").addEventListener("click", () => {
    const name = $("participantInput").value.trim();
    if (!name) return;
    if (!state.participants.includes(name)) state.participants.push(name);
    $("participantInput").value = "";
    renderParticipants();
  });

  $("participantInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("addParticipantBtn").click();
  });

  $("saveParticipantsBtn").addEventListener("click", async () => {
    const btn = $("saveParticipantsBtn");
    btn.disabled = true;
    try { await saveParticipants(); }
    catch (e) { toast.error(`Error: ${e.message}`); }
    finally { btn.disabled = false; }
  });

  // Name aliases
  $("addNameAliasBtn")?.addEventListener("click",   addNameAliasRow);
  $("saveNameAliasesBtn")?.addEventListener("click", async () => {
    try { await saveNameAliases(); }
    catch (e) { toast.error(`Error: ${e.message}`); }
  });

  $("nameAliasToInput")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") addNameAliasRow();
  });

  // Segments
  $("generateSegmentsBtn").addEventListener("click", async () => {
    const btn = $("generateSegmentsBtn");
    btn.disabled = true;
    try {
      $("segmentsStatus").textContent = "Generating…";
      await generateSegments();
      $("segmentsStatus").textContent = "";
    } catch (e) {
      $("segmentsStatus").textContent = `Error: ${e.message}`;
      toast.error(e.message);
    } finally {
      btn.disabled = false;
    }
  });

  $("saveSegmentsBtn").addEventListener("click", async () => {
    const btn = $("saveSegmentsBtn");
    btn.disabled = true;
    try {
      await saveSegments();
    } catch (e) {
      toast.error(`Error: ${e.message}`);
    } finally {
      btn.disabled = false;
    }
  });

  // Action items (add manually)
  $("addAiBtn").addEventListener("click", async () => {
    if (!state.selectedProjectId) { toast.warning("Select a project first."); return; }
    const what   = $("aiWhat").value.trim();
    if (!what)   { toast.warning("The 'What' field is required."); return; }
    const who    = $("aiWho").value.trim();
    const willDo = $("aiWillDo").value.trim();
    const byWhen = $("aiByWhen").value.trim();

    const btn    = $("addAiBtn");
    btn.disabled = true;
    try {
      await api(`/api/projects/${state.selectedProjectId}/action_items`, {
        method: "POST",
        body:   JSON.stringify({ who, will_do: willDo, what, by_when: byWhen || null }),
      });
      toast.success("Action item added.");
      $("aiWho").value    = "";
      $("aiWillDo").value = "";
      $("aiWhat").value   = "";
      $("aiByWhen").value = "";
      await loadHistory();
    } catch (e) {
      toast.error(`Error: ${e.message}`);
      $("aiStatus").textContent = `Error: ${e.message}`;
    } finally {
      btn.disabled = false;
    }
  });

  // Activity log
  $("loadActivityBtn").addEventListener("click", async () => {
    const btn = $("loadActivityBtn");
    btn.disabled = true;
    try { await loadActivity(); }
    catch (e) { toast.error(e.message); }
    finally { btn.disabled = false; }
  });

  // Keyboard shortcut: N = new project, R = record, I = intelligence
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const key = e.key.toLowerCase();
    if (key === "s") { e.preventDefault(); showView("setup"); }
    if (key === "r") { e.preventDefault(); showView("record"); }
    if (key === "i") { e.preventDefault(); showView("intel"); if (state.selectedProjectId) loadHistory().catch(() => {}); }
  });
}

// ═══════════════════════════════════════════════════════════════
// INITIALISATION
// ═══════════════════════════════════════════════════════════════

// ─── User menu ──────────────────────────────────────────────────
function initUserMenu() {
  const user = window.__currentUser;
  if (!user) return;

  const initials = user.initials || (user.name || "U").slice(0, 2).toUpperCase();
  $("userInitials").textContent        = initials;
  $("userDropdownAvatar").textContent  = initials;
  $("userDropdownName").textContent    = user.name  || "—";
  $("userDropdownEmail").textContent   = user.email || "—";

  const btn      = $("userAvatarBtn");
  const dropdown = $("userDropdown");

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const open = !dropdown.hidden;
    dropdown.hidden = open;
    btn.setAttribute("aria-expanded", !open);
  });

  document.addEventListener("click", (e) => {
    if (!$("userMenuWrap").contains(e.target)) {
      dropdown.hidden = true;
      btn.setAttribute("aria-expanded", "false");
    }
  });

  $("logoutBtn").addEventListener("click", async () => {
    try { await fetch("/auth/logout", { method: "POST" }); } catch (_) {}
    window.location.href = "/login";
  });
}

async function main() {
  // Init UI systems
  darkMode.init();
  sidebar.init();
  modal.init();
  initDropZone();
  initUserMenu();

  // Restore previous state
  restoreSelectedProject();
  updateSelectedProjectLabels();

  // Wire all events
  wire();

  // Load projects
  try {
    await refreshProjects();
  } catch (e) {
    toast.error(`Failed to load projects: ${e.message}`);
    $("projectStatus").textContent = `Error: ${e.message}`;
  }

  // Navigate to appropriate view
  if (state.selectedProjectId) {
    showView("record");
  } else {
    showView("setup");
  }
}

main();
