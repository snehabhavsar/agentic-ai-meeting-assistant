const $ = (id) => document.getElementById(id);

const state = {
  projects: [],
  selectedProjectId: null,
  selectedProjectName: null,
  participants: [],
  meetingId: null,
  recorder: null,
  chunks: [],
  stream: null,
  mimeType: null,
  view: "setup", // setup | record | intel
  currentMeeting: null,
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

function setActiveNav() {
  const map = {
    setup: "navSetup",
    record: "navRecord",
    intel: "navIntel",
  };
  for (const key of Object.values(map)) {
    $(key).classList.remove("active");
  }
  $(map[state.view]).classList.add("active");
}

function showView(view) {
  state.view = view;
  $("viewSetup").hidden = view !== "setup";
  $("viewRecord").hidden = view !== "record";
  $("viewIntel").hidden = view !== "intel";
  setActiveNav();
}

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
      state.selectedProjectId = Number(parsed.id);
      state.selectedProjectName = parsed.name || null;
    }
  } catch {}
}

function updateSelectedProjectLabels() {
  const label = state.selectedProjectName
    ? `${state.selectedProjectName} (id=${state.selectedProjectId})`
    : state.selectedProjectId
      ? `Project id=${state.selectedProjectId}`
      : "—";
  $("selectedProjectLabel").textContent = label;
  $("intelProjectLabel").textContent = label;
}

function renderProjectTree(filterText = "") {
  const root = $("projectTree");
  root.innerHTML = "";
  const q = (filterText || "").trim().toLowerCase();
  const items = (state.projects || []).filter((p) => !q || (p.name || "").toLowerCase().includes(q));

  if (!items.length) {
    root.innerHTML = `<div class="muted">No projects found.</div>`;
    return;
  }

  for (const p of items) {
    const el = document.createElement("div");
    el.className = "project-node" + (p.id === state.selectedProjectId ? " active" : "");
    el.innerHTML = `
      <div class="project-icon">PR</div>
      <div class="project-meta">
        <div class="project-name">${escapeHtml(p.name)}</div>
        <div class="project-id">id=${p.id}</div>
      </div>
    `;
    el.addEventListener("click", async () => {
      state.selectedProjectId = p.id;
      state.selectedProjectName = p.name;
      $("projectSelect").value = String(p.id);
      persistSelectedProject();
      updateSelectedProjectLabels();
      renderProjectTree($("projectSearch").value);
      // When selecting from the sidebar, jump to intelligence view.
      showView("intel");
      await loadHistory();
    });
    root.appendChild(el);
  }
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

  state.currentMeeting = meeting;

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

  // If speaker segments exist, render editor.
  renderSegmentsEditor(transcript?.speaker_segments || []);
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

  // restore previous selection if present, else pick first
  if (state.selectedProjectId && state.projects.some((p) => p.id === state.selectedProjectId)) {
    sel.value = String(state.selectedProjectId);
    const p = state.projects.find((x) => x.id === state.selectedProjectId);
    state.selectedProjectName = p?.name || state.selectedProjectName;
  } else if (state.projects.length) {
    state.selectedProjectId = Number(sel.value);
    const p = state.projects.find((x) => x.id === state.selectedProjectId);
    state.selectedProjectName = p?.name || null;
  } else {
    state.selectedProjectId = null;
    state.selectedProjectName = null;
  }

  updateSelectedProjectLabels();
  renderProjectTree($("projectSearch").value);
}

async function loadParticipants() {
  if (!state.selectedProjectId) return;
  const payload = await api(`/api/projects/${state.selectedProjectId}/participants`, { method: "GET" });
  const participants = payload?.project?.participants;
  state.participants = Array.isArray(participants) ? participants : [];
  renderParticipants();
}

async function saveParticipants() {
  if (!state.selectedProjectId) throw new Error("Select a project first");
  const payload = await api(`/api/projects/${state.selectedProjectId}/participants`, {
    method: "PUT",
    body: JSON.stringify({ participants: state.participants }),
  });
  const participants = payload?.project?.participants;
  state.participants = Array.isArray(participants) ? participants : state.participants;
  $("participantsStatus").textContent = "Saved.";
  renderParticipants();
}

function renderParticipants() {
  const root = $("participantsList");
  root.innerHTML = "";
  if (!state.participants.length) {
    root.innerHTML = `<div class="muted">No participants yet. Add names like Alice, Bob, Mentor.</div>`;
    return;
  }
  const wrap = document.createElement("div");
  for (const p of state.participants) {
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.innerHTML = `
      <span>${escapeHtml(p)}</span>
      <button data-name="${escapeHtml(p)}">Remove</button>
    `;
    pill.querySelector("button").addEventListener("click", () => {
      state.participants = state.participants.filter((x) => x !== p);
      renderParticipants();
    });
    wrap.appendChild(pill);
  }
  root.appendChild(wrap);
}

function renderSegmentsEditor(segments) {
  const root = $("segmentsEditor");
  root.innerHTML = "";
  $("segmentsStatus").textContent = "";

  if (!segments || !segments.length) {
    root.innerHTML = `<div class="muted">No segments yet. Click “Generate segments”.</div>`;
    $("saveSegmentsBtn").disabled = true;
    return;
  }

  const speakerOptions = ["(Unassigned)", ...state.participants];

  for (const seg of segments) {
    const el = document.createElement("div");
    el.className = "seg";
    const speaker = seg.speaker || "";
    el.innerHTML = `
      <div>
        <div class="item-meta"><span class="tag">segment ${seg.idx}</span></div>
        <select data-idx="${seg.idx}">
          ${speakerOptions
            .map((opt) => {
              const val = opt === "(Unassigned)" ? "" : opt;
              const sel = val === speaker ? "selected" : "";
              return `<option value="${escapeHtml(val)}" ${sel}>${escapeHtml(opt)}</option>`;
            })
            .join("")}
        </select>
      </div>
      <div>
        <textarea data-text-idx="${seg.idx}">${escapeHtml(seg.text || "")}</textarea>
      </div>
    `;
    root.appendChild(el);
  }

  $("saveSegmentsBtn").disabled = false;
}

function downloadJson(filename, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function generateSegments() {
  if (!state.currentMeeting?.id) throw new Error("Open a meeting first");
  const payload = await api(`/api/meetings/${state.currentMeeting.id}/speaker_segments/generate`, { method: "POST" });
  renderSegmentsEditor(payload.transcript?.speaker_segments || []);
  $("segmentsStatus").textContent = "Generated segments.";
}

async function saveSegments() {
  if (!state.currentMeeting?.id) throw new Error("Open a meeting first");
  const root = $("segmentsEditor");
  const selects = Array.from(root.querySelectorAll("select[data-idx]"));
  const segs = selects.map((sel) => {
    const idx = Number(sel.getAttribute("data-idx"));
    const speaker = sel.value || null;
    const ta = root.querySelector(`textarea[data-text-idx="${idx}"]`);
    const text = ta ? ta.value.trim() : "";
    return { idx, speaker, text };
  });

  const payload = await api(`/api/meetings/${state.currentMeeting.id}/speaker_segments`, {
    method: "PATCH",
    body: JSON.stringify({ speaker_segments: segs }),
  });
  $("segmentsStatus").textContent = "Saved speaker labels.";
  renderSegmentsEditor(payload.transcript?.speaker_segments || []);
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
  state.selectedProjectName = payload.project.name;
  persistSelectedProject();
  updateSelectedProjectLabels();
  renderProjectTree($("projectSearch").value);
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
      await api(`/api/meetings/${state.meetingId}/process`, {
        method: "POST",
        body: JSON.stringify({ async: true }),
      });

      await pollUntilDone(state.meetingId, (m) => {
        const pct = m.processing_progress ?? 0;
        const stage = m.processing_stage || "processing";
        $("meetingStatus").textContent = `Processing… ${pct}% (${stage})`;
      });

      $("meetingStatus").textContent = "Done. Opening Project Intelligence.";
      showView("intel");
      await loadHistory();
      $("viewIntelBtn").disabled = false;
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

  renderMeetingsList(payload.meetings || []);
  await loadParticipants();

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

async function pollUntilDone(meetingId, onUpdate) {
  const maxMs = 60 * 60 * 1000; // 1 hour demo safety
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    const payload = await api(`/api/meetings/${meetingId}`, { method: "GET" });
    const m = payload.meeting;
    if (onUpdate) onUpdate(m);
    if (m.status === "processed") {
      renderMinutes(m);
      return m;
    }
    if (m.status === "failed") {
      throw new Error(m.processing_error || "processing failed");
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
  throw new Error("processing timeout");
}

function renderMeetingsList(meetings) {
  const root = $("meetingsList");
  root.innerHTML = "";
  if (!meetings || !meetings.length) {
    root.innerHTML = `<div class="muted">No meetings yet. Record your first meeting.</div>`;
    return;
  }

  for (const m of meetings) {
    const el = document.createElement("div");
    el.className = "item";
    const title = m.title || `Meeting ${m.id}`;
    el.innerHTML = `
      <div>
        <div class="item-title">${escapeHtml(title)}</div>
        <div class="item-meta">
          <span class="tag">id=${m.id}</span>
          <span class="tag">status=${escapeHtml(m.status)}</span>
          <span class="tag">created=${escapeHtml((m.created_at || "").slice(0, 19).replace("T", " "))}</span>
        </div>
      </div>
      <div class="item-actions">
        <button class="primary">Open</button>
      </div>
    `;
    el.querySelector("button").addEventListener("click", async () => {
      try {
        const payload = await api(`/api/meetings/${m.id}`, { method: "GET" });
        state.meetingId = payload.meeting.id;
        renderMinutes(payload.meeting);
      } catch (e) {
        $("meetingStatus").textContent = `Error: ${e.message}`;
      }
    });
    root.appendChild(el);
  }
}

function wire() {
  // Nav
  $("navSetup").addEventListener("click", () => showView("setup"));
  $("navRecord").addEventListener("click", () => showView("record"));
  $("navIntel").addEventListener("click", async () => {
    showView("intel");
    if (state.selectedProjectId) await loadHistory();
  });

  $("refreshProjectsBtn").addEventListener("click", async () => {
    try {
      await refreshProjects();
    } catch (e) {
      $("projectStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("useProjectBtn").addEventListener("click", () => {
    if (!state.selectedProjectId) {
      $("projectStatus").textContent = "Select a project first.";
      return;
    }
    const p = state.projects.find((x) => x.id === state.selectedProjectId);
    state.selectedProjectName = p?.name || state.selectedProjectName;
    persistSelectedProject();
    updateSelectedProjectLabels();
    showView("record");
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
    const p = state.projects.find((x) => x.id === state.selectedProjectId);
    state.selectedProjectName = p?.name || null;
    persistSelectedProject();
    updateSelectedProjectLabels();
    renderProjectTree($("projectSearch").value);
  });

  $("projectSearch").addEventListener("input", (e) => {
    renderProjectTree(e.target.value);
  });

  $("startBtn").addEventListener("click", async () => {
    try {
      $("viewIntelBtn").disabled = true;
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

  $("viewIntelBtn").addEventListener("click", async () => {
    showView("intel");
    await loadHistory();
  });

  // Upload recording
  $("uploadFile").addEventListener("change", () => {
    const f = $("uploadFile").files?.[0];
    $("uploadProcessBtn").disabled = !f;
  });

  $("uploadProcessBtn").addEventListener("click", async () => {
    try {
      const file = $("uploadFile").files?.[0];
      if (!file) throw new Error("Choose an audio file first");
      if (!state.selectedProjectId) throw new Error("Select a project first");

      $("uploadStatus").textContent = "Creating meeting...";
      const title = $("uploadTitle").value.trim() || file.name;
      const started = await api("/api/meetings/start", {
        method: "POST",
        body: JSON.stringify({ project_id: state.selectedProjectId, title }),
      });
      state.meetingId = started.meeting.id;
      setMeetingId(state.meetingId);

      await api(`/api/meetings/${state.meetingId}/stop`, { method: "POST", body: JSON.stringify({}) });

      $("uploadStatus").textContent = "Uploading audio...";
      const fd = new FormData();
      fd.append("audio", file, file.name);
      const uploadRes = await fetch(`/api/meetings/${state.meetingId}/upload_audio`, { method: "POST", body: fd });
      if (!uploadRes.ok) throw new Error(await uploadRes.text());

      $("uploadStatus").textContent = "Processing...";
      await api(`/api/meetings/${state.meetingId}/process`, {
        method: "POST",
        body: JSON.stringify({ async: true }),
      });
      await pollUntilDone(state.meetingId, (m) => {
        const pct = m.processing_progress ?? 0;
        const stage = m.processing_stage || "processing";
        $("uploadStatus").textContent = `Processing… ${pct}% (${stage})`;
      });
      $("uploadStatus").textContent = "Done. Opening Project Intelligence.";
      showView("intel");
      await loadHistory();
    } catch (e) {
      $("uploadStatus").textContent = `Error: ${e.message}`;
    }
  });

  // Participants + speaker labeling
  $("addParticipantBtn").addEventListener("click", () => {
    const name = $("participantInput").value.trim();
    if (!name) return;
    if (!state.participants.includes(name)) state.participants.push(name);
    $("participantInput").value = "";
    $("participantsStatus").textContent = "";
    renderParticipants();
  });

  $("saveParticipantsBtn").addEventListener("click", async () => {
    try {
      $("participantsStatus").textContent = "Saving...";
      await saveParticipants();
    } catch (e) {
      $("participantsStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("generateSegmentsBtn").addEventListener("click", async () => {
    try {
      $("segmentsStatus").textContent = "Generating...";
      await generateSegments();
    } catch (e) {
      $("segmentsStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("saveSegmentsBtn").addEventListener("click", async () => {
    try {
      $("segmentsStatus").textContent = "Saving...";
      await saveSegments();
    } catch (e) {
      $("segmentsStatus").textContent = `Error: ${e.message}`;
    }
  });

  // Export / Print
  $("exportJsonBtn").addEventListener("click", async () => {
    try {
      if (!state.currentMeeting?.id) throw new Error("Open a meeting first");
      const payload = await api(`/api/meetings/${state.currentMeeting.id}/export`, { method: "GET" });
      downloadJson(`meeting_${state.currentMeeting.id}_minutes.json`, payload);
    } catch (e) {
      $("meetingStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("printBtn").addEventListener("click", () => {
    window.print();
  });
}

async function main() {
  restoreSelectedProject();
  wire();
  try {
    await refreshProjects();
  } catch (e) {
    $("projectStatus").textContent = `Error loading projects: ${e.message}`;
  }

  // Default: if no projects exist, stay on setup; else go to record.
  if (state.selectedProjectId) {
    showView("record");
  } else {
    showView("setup");
  }
}

main();

