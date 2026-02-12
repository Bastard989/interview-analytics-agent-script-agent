const el = {
  apiKey: document.getElementById("apiKey"),
  apiSignal: document.getElementById("apiSignal"),
  meetingUrl: document.getElementById("meetingUrl"),
  durationSec: document.getElementById("durationSec"),
  language: document.getElementById("language"),
  inputDevice: document.getElementById("inputDevice"),
  transcribe: document.getElementById("transcribe"),
  uploadToAgent: document.getElementById("uploadToAgent"),
  localReport: document.getElementById("localReport"),
  autoOpen: document.getElementById("autoOpen"),
  quickStart: document.getElementById("quickStart"),
  quickStop: document.getElementById("quickStop"),
  quickState: document.getElementById("quickState"),
  quickMeta: document.getElementById("quickMeta"),
  refreshMeetings: document.getElementById("refreshMeetings"),
  meetingsInfo: document.getElementById("meetingsInfo"),
  meetingsTable: document.getElementById("meetingsTable"),
  meetingIdInput: document.getElementById("meetingIdInput"),
  loadMeeting: document.getElementById("loadMeeting"),
  loadScorecard: document.getElementById("loadScorecard"),
  rebuildArtifacts: document.getElementById("rebuildArtifacts"),
  openReportJson: document.getElementById("openReportJson"),
  openReportTxt: document.getElementById("openReportTxt"),
  enhancedTranscript: document.getElementById("enhancedTranscript"),
  reportJson: document.getElementById("reportJson"),
  scorecardJson: document.getElementById("scorecardJson"),
  comparisonMeetingIds: document.getElementById("comparisonMeetingIds"),
  runComparison: document.getElementById("runComparison"),
  comparisonJson: document.getElementById("comparisonJson"),
  senderAccount: document.getElementById("senderAccount"),
  manualRecipients: document.getElementById("manualRecipients"),
  manualMessage: document.getElementById("manualMessage"),
  manualSend: document.getElementById("manualSend"),
  manualSendState: document.getElementById("manualSendState"),
  manualSendMeta: document.getElementById("manualSendMeta"),
};

const state = {
  jobId: null,
  pollTimer: null,
};

function apiHeaders(extra = {}) {
  const headers = { ...extra };
  const apiKey = (el.apiKey.value || "").trim();
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }
  return headers;
}

async function apiFetch(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: apiHeaders(options.headers || {}),
  });
  const text = await res.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const detail = body && typeof body === "object" ? JSON.stringify(body) : String(body || "request failed");
    throw new Error(`${res.status} ${detail}`);
  }
  return body;
}

function setQuickState(status, meta = "") {
  el.quickState.textContent = status || "idle";
  el.quickMeta.textContent = meta || "";
  const isActive = ["queued", "running", "stopping"].includes(status);
  el.quickStart.disabled = isActive;
  el.quickStop.disabled = !isActive;
}

async function checkApiSignal() {
  try {
    const body = await apiFetch("/health");
    if (body && body.ok) {
      el.apiSignal.textContent = "API signal: ok";
      el.apiSignal.className = "signal status-ok";
      return;
    }
    throw new Error("bad health payload");
  } catch (err) {
    el.apiSignal.textContent = `API signal: error (${err.message})`;
    el.apiSignal.className = "signal status-bad";
  }
}

async function pollQuickStatus() {
  try {
    const query = state.jobId ? `?job_id=${encodeURIComponent(state.jobId)}` : "";
    const body = await apiFetch(`/v1/quick-record/status${query}`);
    const job = body && body.job;
    if (!job) {
      setQuickState("idle", "Нет активной quick записи.");
      state.jobId = null;
      return;
    }
    state.jobId = job.job_id;
    const meta = [
      `job_id=${job.job_id}`,
      job.mp3_path ? `mp3=${job.mp3_path}` : null,
      job.local_report_json_path ? `report=${job.local_report_json_path}` : null,
      job.error ? `error=${job.error}` : null,
    ]
      .filter(Boolean)
      .join(" | ");
    setQuickState(job.status, meta);
  } catch (err) {
    setQuickState("error", err.message);
  }
}

function startQuickPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
  state.pollTimer = setInterval(() => {
    pollQuickStatus().catch(() => {});
  }, 3000);
}

async function startQuickRecord() {
  const meetingUrl = (el.meetingUrl.value || "").trim();
  if (!meetingUrl.startsWith("http://") && !meetingUrl.startsWith("https://")) {
    setQuickState("error", "URL встречи должен начинаться с http:// или https://");
    return;
  }

  const duration = Number(el.durationSec.value || 0);
  if (!Number.isFinite(duration) || duration < 5) {
    setQuickState("error", "Длительность должна быть >= 5 сек");
    return;
  }

  const payload = {
    meeting_url: meetingUrl,
    duration_sec: duration,
    transcribe: Boolean(el.transcribe.checked),
    transcribe_language: (el.language.value || "ru").trim() || "ru",
    input_device: (el.inputDevice.value || "").trim() || null,
    upload_to_agent: Boolean(el.uploadToAgent.checked),
    build_local_report: Boolean(el.localReport.checked),
    auto_open_url: Boolean(el.autoOpen.checked),
    email_to: [],
  };

  try {
    const body = await apiFetch("/v1/quick-record/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.jobId = body.job.job_id;
    setQuickState(body.job.status, `job_id=${body.job.job_id}`);
    await refreshMeetings();
  } catch (err) {
    setQuickState("error", err.message);
  }
}

async function stopQuickRecord() {
  try {
    const body = await apiFetch("/v1/quick-record/stop", { method: "POST" });
    const job = body && body.job;
    if (job) {
      state.jobId = job.job_id;
      setQuickState(job.status, `job_id=${job.job_id}`);
    } else {
      setQuickState("idle", "Активной quick записи нет.");
    }
  } catch (err) {
    setQuickState("error", err.message);
  }
}

function statusClass(status) {
  const value = (status || "").toLowerCase();
  if (["done", "completed"].includes(value)) return "status-ok";
  if (["queued", "processing", "running", "stopping"].includes(value)) return "status-warn";
  if (["failed", "error"].includes(value)) return "status-bad";
  return "";
}

function renderMeetings(items) {
  el.meetingsTable.innerHTML = "";
  for (const item of items) {
    const tr = document.createElement("tr");
    const artifactTags = Object.entries(item.artifacts || {})
      .filter(([, present]) => Boolean(present))
      .map(([name]) => name)
      .join(", ");

    tr.innerHTML = `
      <td>${item.meeting_id}</td>
      <td class="${statusClass(item.status)}">${item.status}</td>
      <td>${item.created_at || ""}</td>
      <td>${artifactTags || "-"}</td>
      <td><button class="btn" data-open="${item.meeting_id}">Open</button></td>
    `;
    el.meetingsTable.appendChild(tr);
  }

  for (const btn of el.meetingsTable.querySelectorAll("button[data-open]")) {
    btn.addEventListener("click", () => {
      const meetingId = btn.getAttribute("data-open");
      el.meetingIdInput.value = meetingId || "";
      loadMeeting().catch(() => {});
    });
  }
}

async function refreshMeetings() {
  try {
    const body = await apiFetch("/v1/meetings?limit=50");
    const items = Array.isArray(body.items) ? body.items : [];
    renderMeetings(items);
    el.meetingsInfo.textContent = `Найдено встреч: ${items.length}`;
  } catch (err) {
    el.meetingsInfo.textContent = `Ошибка: ${err.message}`;
  }
}

async function loadMeeting() {
  const meetingId = (el.meetingIdInput.value || "").trim();
  if (!meetingId) {
    return;
  }

  try {
    const body = await apiFetch(`/v1/meetings/${encodeURIComponent(meetingId)}`);
    el.enhancedTranscript.value = body.enhanced_transcript || "";
    el.reportJson.value = JSON.stringify(body.report || {}, null, 2);
    el.scorecardJson.value = JSON.stringify((body.report && body.report.scorecard) || {}, null, 2);
  } catch (err) {
    el.reportJson.value = `Ошибка загрузки встречи: ${err.message}`;
  }
}

async function loadScorecard() {
  const meetingId = (el.meetingIdInput.value || "").trim();
  if (!meetingId) {
    return;
  }
  try {
    const body = await apiFetch(`/v1/meetings/${encodeURIComponent(meetingId)}/scorecard`);
    el.scorecardJson.value = JSON.stringify(body.scorecard || {}, null, 2);
  } catch (err) {
    el.scorecardJson.value = `Ошибка загрузки scorecard: ${err.message}`;
  }
}

async function rebuildArtifacts() {
  const meetingId = (el.meetingIdInput.value || "").trim();
  if (!meetingId) {
    return;
  }
  try {
    await apiFetch(`/v1/meetings/${encodeURIComponent(meetingId)}/artifacts/rebuild`, {
      method: "POST",
    });
    await loadMeeting();
    await refreshMeetings();
  } catch (err) {
    el.reportJson.value = `Ошибка rebuild: ${err.message}`;
  }
}

async function downloadArtifact(kind, fmt) {
  const meetingId = (el.meetingIdInput.value || "").trim();
  if (!meetingId) {
    return;
  }
  const url = `/v1/meetings/${encodeURIComponent(meetingId)}/artifact?kind=${encodeURIComponent(kind)}&fmt=${encodeURIComponent(fmt)}`;
  const res = await fetch(url, { headers: apiHeaders() });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  const blob = await res.blob();
  const filename = kind === "report" && fmt === "json" ? "report.json" : "report.txt";

  if (fmt === "txt") {
    const text = await blob.text();
    el.reportJson.value = text;
    return;
  }

  const link = document.createElement("a");
  const href = URL.createObjectURL(blob);
  link.href = href;
  link.download = `${meetingId}_${filename}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

function setManualSendState(status, meta) {
  el.manualSendState.textContent = status || "idle";
  el.manualSendMeta.textContent = meta || "";
}

async function loadDeliveryAccounts() {
  try {
    const body = await apiFetch("/v1/delivery/accounts");
    const accounts = Array.isArray(body.accounts) ? body.accounts : [];
    el.senderAccount.innerHTML = "";
    for (const acc of accounts) {
      const opt = document.createElement("option");
      opt.value = acc.account_id;
      opt.textContent = `${acc.account_id} (${acc.from_email})`;
      el.senderAccount.appendChild(opt);
    }
  } catch (err) {
    setManualSendState("error", `Не удалось загрузить sender accounts: ${err.message}`);
  }
}

async function runComparison() {
  const raw = (el.comparisonMeetingIds.value || "").trim();
  if (!raw) {
    el.comparisonJson.value = "Укажите meeting IDs через запятую.";
    return;
  }
  const meetingIds = raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (meetingIds.length < 2) {
    el.comparisonJson.value = "Нужно минимум 2 meeting_id.";
    return;
  }
  try {
    const body = await apiFetch("/v1/analysis/comparison", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ meeting_ids: meetingIds }),
    });
    el.comparisonJson.value = JSON.stringify(body.report || {}, null, 2);
    await refreshMeetings();
  } catch (err) {
    el.comparisonJson.value = `Ошибка сравнения: ${err.message}`;
  }
}

async function sendManualDelivery() {
  const meetingId = (el.meetingIdInput.value || "").trim();
  if (!meetingId) {
    setManualSendState("error", "Сначала выберите meeting_id.");
    return;
  }
  const recipients = (el.manualRecipients.value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (!recipients.length) {
    setManualSendState("error", "Укажите хотя бы один email получателя.");
    return;
  }
  const senderAccount = (el.senderAccount.value || "").trim() || null;
  const payload = {
    channel: "email",
    recipients,
    sender_account: senderAccount,
    include_artifacts: ["report_json", "report_txt", "scorecard_json", "comparison_json", "calibration_json"],
    custom_message: (el.manualMessage.value || "").trim() || null,
  };
  setManualSendState("sending", "Отправка...");
  try {
    const body = await apiFetch(`/v1/meetings/${encodeURIComponent(meetingId)}/delivery/manual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setManualSendState(
      body.ok ? "ok" : "failed",
      `channel=${body.channel} sender=${body.sender_account || "-"} recipients=${(body.recipients || []).join(", ")}`
    );
    await refreshMeetings();
  } catch (err) {
    setManualSendState("error", err.message);
  }
}

el.quickStart.addEventListener("click", () => {
  startQuickRecord().catch(() => {});
});

el.quickStop.addEventListener("click", () => {
  stopQuickRecord().catch(() => {});
});

el.refreshMeetings.addEventListener("click", () => {
  refreshMeetings().catch(() => {});
});

el.loadMeeting.addEventListener("click", () => {
  loadMeeting().catch(() => {});
});

el.loadScorecard.addEventListener("click", () => {
  loadScorecard().catch(() => {});
});

el.rebuildArtifacts.addEventListener("click", () => {
  rebuildArtifacts().catch(() => {});
});

el.openReportJson.addEventListener("click", () => {
  downloadArtifact("report", "json").catch((err) => {
    el.reportJson.value = `Ошибка скачивания report.json: ${err.message}`;
  });
});

el.openReportTxt.addEventListener("click", () => {
  downloadArtifact("report", "txt").catch((err) => {
    el.reportJson.value = `Ошибка загрузки report.txt: ${err.message}`;
  });
});

el.runComparison.addEventListener("click", () => {
  runComparison().catch(() => {});
});

el.manualSend.addEventListener("click", () => {
  sendManualDelivery().catch(() => {});
});

(async function bootstrap() {
  await checkApiSignal();
  await pollQuickStatus();
  await refreshMeetings();
  await loadDeliveryAccounts();
  startQuickPolling();
  setInterval(() => {
    checkApiSignal().catch(() => {});
  }, 10000);
})();
