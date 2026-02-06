const $ = (id) => document.getElementById(id);

const state = {
  projects: [],
  selectedProjectId: null,
  meetingId: null,
  recorder: null,
  chunks: [],
  stream: null,
  mimeType: null,
};

function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmtActionItem(ai) {
  const due = ai.by_when || "N/A";
  const who = ai.who || "Unassigned";
  const willDo = ai.will_do || "do";
  return `${who} — ${willDo} — ${ai.what}${ai.by_when ? ` — By ${due}` : ""}`;
}

function renderPending(items) {
  const root = $("pendingItemsList");
  root.innerHTML = "";
  if (!items || !items.length) {
    root.innerHTML = `<div class="muted">No pending action items.</div>`;
    return;
  }

  for (const ai of items) {
    const el = document.createElement("div");
    el.className = "item";
    el.innerHTML = `
      <div>
        <div class="item-title">${escapeHtml(fmtActionItem(ai))}</div>
        <div class="item-meta">
          <span class="tag">id=${ai.id}</span>
          <span class="tag">status=${escapeHtml(ai.status)}</span>
          ${ai.created_in_meeting_id ? `<span class="tag">created_in_meeting=${ai.created_in_meeting_id}</span>` : ""}
        </div>
      </div>
      <div class="item-actions">
        <button data-ai="${ai.id}" class="primary">Mark completed</button>
      </div>
    `;
    const btn = el.querySelector("button");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        await api(`/api/action_items/${ai.id}`, {
          method: "PATCH",
          body: JSON.stringify({ status: "completed", resolved_in_meeting_id: state.meetingId }),
        });
        await loadHistory();
      } catch (e) {
        $("meetingStatus").textContent = `Error: ${e.message}`;
      } finally {
        btn.disabled = false;
      }
    });
    root.appendChild(el);
  }
}

function renderCompleted(items) {
  const root = $("completedItemsList");
  root.innerHTML = "";
  if (!items || !items.length) {
    root.innerHTML = `<div class="muted">No completed action items.</div>`;
    return;
  }

  for (const ai of items) {
    const el = document.createElement("div");
    el.className = "item";
    el.innerHTML = `
      <div>
        <div class="item-title">${escapeHtml(fmtActionItem(ai))}</div>
        <div class="item-meta">
          <span class="tag ok">completed</span>
          <span class="tag">id=${ai.id}</span>
          ${ai.resolved_in_meeting_id ? `<span class="tag">resolved_in_meeting=${ai.resolved_in_meeting_id}</span>` : ""}
        </div>
      </div>
      <div class="item-actions">
        <button data-ai="${ai.id}">Re-open</button>
      </div>
    `;
    const btn = el.querySelector("button");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        await api(`/api/action_items/${ai.id}`, {
          method: "PATCH",
          body: JSON.stringify({ status: "pending", resolved_in_meeting_id: null }),
        });
        await loadHistory();
      } catch (e) {
        $("meetingStatus").textContent = `Error: ${e.message}`;
      } finally {
        btn.disabled = false;
      }
    });
    root.appendChild(el);
  }
}

function renderMinutes(meeting) {
  const root = $("latestMinutes");
  if (!meeting) {
    root.innerHTML = `<div class="muted">No meeting loaded.</div>`;
    return;
  }

  const summary = meeting.summary || null;
  const transcript = meeting.transcript || null;

  const decisions = summary?.decisions || [];
  const extracted = summary?.action_items_extracted || [];

  root.innerHTML = `
    <div class="minutes">
      <div class="row small">
        <span><b>meeting_id:</b> ${meeting.id}</span>
        <span><b>status:</b> ${escapeHtml(meeting.status)}</span>
        <span><b>created:</b> ${escapeHtml(meeting.created_at || "")}</span>
      </div>

      <h4>Summary</h4>
      <p>${escapeHtml(summary?.summary_text || "(not processed yet)")}</p>

      <h4>Decisions</h4>
      ${
        decisions && decisions.length
          ? `<ul>${decisions.map((d) => `<li>${escapeHtml(d.text || JSON.stringify(d))}</li>`).join("")}</ul>`
          : `<div class="muted">No decisions extracted.</div>`
      }

      <h4>Action items extracted (this meeting)</h4>
      ${
        extracted && extracted.length
          ? `<ul>${extracted.map((ai) => `<li>${escapeHtml(fmtActionItem(ai))}</li>`).join("")}</ul>`
          : `<div class="muted">No action items extracted.</div>`
      }

      <h4>Transcript (debug)</h4>
      <p class="muted">${escapeHtml((transcript?.text || "").slice(0, 1200))}${(transcript?.text || "").length > 1200 ? "…" : ""}</p>
    </div>
  `;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await res.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text };
  }
  if (!res.ok) {
    const msg = payload?.error || `HTTP ${res.status}`;
    throw new Error(`${msg}${payload?.details ? `: ${payload.details}` : ""}`);
  }
  return payload;
}

async function refreshProjects() {
  const payload = await api("/api/projects", { method: "GET" });
  state.projects = payload.projects || [];

  const sel = $("projectSelect");
  sel.innerHTML = "";
  for (const p of state.projects) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.name} (id=${p.id})`;
    sel.appendChild(opt);
  }

  if (state.projects.length) {
    state.selectedProjectId = Number(sel.value);
  } else {
    state.selectedProjectId = null;
  }
}

async function createProject() {
  const name = $("projectName").value.trim();
  const description = $("projectDesc").value.trim();
  $("projectStatus").textContent = "Creating project...";
  const payload = await api("/api/projects", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
  $("projectStatus").textContent = `Created: ${payload.project.name} (id=${payload.project.id})`;
  await refreshProjects();
  $("projectSelect").value = String(payload.project.id);
  state.selectedProjectId = payload.project.id;
}

function setRecStatus(s) {
  $("recStatus").textContent = s;
}

function setMeetingId(id) {
  $("meetingId").textContent = id ? String(id) : "—";
}

async function startRecording() {
  if (!state.selectedProjectId) throw new Error("Create/select a project first");

  // Create meeting first so everything is linked to a meeting_id.
  $("meetingStatus").textContent = "Starting meeting...";
  const title = $("meetingTitle").value.trim();
  const started = await api("/api/meetings/start", {
    method: "POST",
    body: JSON.stringify({ project_id: state.selectedProjectId, title }),
  });
  state.meetingId = started.meeting.id;
  setMeetingId(state.meetingId);

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  state.stream = stream;

  // Pick a supported audio mimeType.
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
  ];
  state.mimeType = candidates.find((t) => MediaRecorder.isTypeSupported(t)) || "";

  state.chunks = [];
  const rec = new MediaRecorder(stream, state.mimeType ? { mimeType: state.mimeType } : undefined);
  state.recorder = rec;

  rec.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) state.chunks.push(e.data);
  };

  rec.onstop = async () => {
    try {
      const blob = new Blob(state.chunks, { type: state.mimeType || "audio/webm" });
      const url = URL.createObjectURL(blob);
      const playback = $("playback");
      playback.src = url;
      playback.hidden = false;

      $("meetingStatus").textContent = "Stopping meeting + uploading audio...";
      await api(`/api/meetings/${state.meetingId}/stop`, {
        method: "POST",
        body: JSON.stringify({}),
      });

      const fd = new FormData();
      fd.append("audio", blob, "recording.webm");
      const uploadRes = await fetch(`/api/meetings/${state.meetingId}/upload_audio`, {
        method: "POST",
        body: fd,
      });
      if (!uploadRes.ok) {
        const t = await uploadRes.text();
        throw new Error(t || `upload failed (${uploadRes.status})`);
      }

      $("meetingStatus").textContent = "Processing meeting (ASR + summary + action items)...";
      const processed = await api(`/api/meetings/${state.meetingId}/process`, { method: "POST" });

      $("meetingStatus").textContent = "Done. Showing latest meeting + pending items.";
      renderMinutes(processed.meeting);

      await loadHistory();
    } catch (err) {
      $("meetingStatus").textContent = `Error: ${err.message}`;
    } finally {
      // Cleanup mic
      if (state.stream) {
        for (const t of state.stream.getTracks()) t.stop();
      }
      state.stream = null;
    }
  };

  rec.start();
  setRecStatus("recording");
  $("startBtn").disabled = true;
  $("stopBtn").disabled = false;
  $("meetingStatus").textContent = "Recording...";
}

async function stopRecording() {
  if (!state.recorder) return;
  setRecStatus("stopping...");
  $("stopBtn").disabled = true;
  state.recorder.stop();
  setRecStatus("processing...");
  $("startBtn").disabled = false;
}

async function loadHistory() {
  if (!state.selectedProjectId) throw new Error("Select a project");
  const payload = await api(`/api/projects/${state.selectedProjectId}/history`, { method: "GET" });
  renderPending(payload.pending_action_items || []);
  if (payload.meetings && payload.meetings.length) {
    renderMinutes(payload.meetings[0]);
  }

  // Completed items are fetched on-demand to keep /history lean.
  const showCompleted = $("showCompletedToggle")?.checked;
  if (showCompleted) {
    const completed = await api(`/api/projects/${state.selectedProjectId}/action_items?status=completed`, {
      method: "GET",
    });
    renderCompleted(completed.action_items || []);
  } else {
    renderCompleted([]);
  }
}

function wire() {
  $("refreshProjectsBtn").addEventListener("click", async () => {
    try {
      await refreshProjects();
    } catch (e) {
      $("projectStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("createProjectBtn").addEventListener("click", async () => {
    try {
      await createProject();
    } catch (e) {
      $("projectStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("projectSelect").addEventListener("change", (e) => {
    state.selectedProjectId = Number(e.target.value);
  });

  $("startBtn").addEventListener("click", async () => {
    try {
      await startRecording();
    } catch (e) {
      $("meetingStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("stopBtn").addEventListener("click", async () => {
    try {
      await stopRecording();
    } catch (e) {
      $("meetingStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("loadHistoryBtn").addEventListener("click", async () => {
    try {
      await loadHistory();
    } catch (e) {
      $("meetingStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("showCompletedToggle").addEventListener("change", async () => {
    try {
      await loadHistory();
    } catch (e) {
      $("meetingStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("addAiBtn").addEventListener("click", async () => {
    try {
      if (!state.selectedProjectId) throw new Error("Select a project first");
      const who = $("aiWho").value.trim();
      const will_do = $("aiWillDo").value.trim();
      const what = $("aiWhat").value.trim();
      const by_when = $("aiByWhen").value.trim();

      $("aiStatus").textContent = "Adding...";
      await api(`/api/projects/${state.selectedProjectId}/action_items`, {
        method: "POST",
        body: JSON.stringify({ who, will_do, what, by_when: by_when || null }),
      });

      $("aiStatus").textContent = "Added.";
      $("aiWhat").value = "";
      $("aiByWhen").value = "";
      await loadHistory();
    } catch (e) {
      $("aiStatus").textContent = `Error: ${e.message}`;
    }
  });
}

async function main() {
  wire();
  try {
    await refreshProjects();
  } catch (e) {
    $("projectStatus").textContent = `Error loading projects: ${e.message}`;
  }
}

main();

