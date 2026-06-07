const domainInput = document.getElementById("domain");
const limitInput = document.getElementById("limit");
const dryRunInput = document.getElementById("dryRun");
const runBtn = document.getElementById("runBtn");
const sendBtn = document.getElementById("sendBtn");
const logsEl = document.getElementById("logs");
const statusBadge = document.getElementById("statusBadge");
const resultsCard = document.getElementById("resultsCard");
const contactsTable = document.getElementById("contactsTable");
const contactCount = document.getElementById("contactCount");
const confirmArea = document.getElementById("confirmArea");

let currentJobId = null;
let pollTimer = null;

function setBadge(text, className) {
  statusBadge.textContent = text;
  statusBadge.className = `badge ${className}`;
}

function setStep(stageKey) {
  document.querySelectorAll(".step").forEach((step) => {
    step.classList.remove("active", "done");
  });

  const order = ["ocean", "prospeo-search", "prospeo-enrich", "brevo"];
  const index = order.indexOf(stageKey);
  order.forEach((key, i) => {
    const el = document.querySelector(`[data-step="${key}"]`);
    if (!el) return;
    if (i < index) el.classList.add("done");
    if (i === index) el.classList.add("active");
  });
}

function renderLogs(logs) {
  if (!logs.length) {
    logsEl.innerHTML = '<p class="muted">No logs yet.</p>';
    return;
  }

  logsEl.innerHTML = logs
    .map(
      (log) =>
        `<p class="log-line ${log.level}">${escapeHtml(log.message)}</p>`
    )
    .join("");
  logsEl.scrollTop = logsEl.scrollHeight;

  const last = logs[logs.length - 1]?.message || "";
  if (last.includes("Ocean.io")) setStep("ocean");
  if (last.includes("decision-makers")) setStep("prospeo-search");
  if (last.includes("verified emails")) setStep("prospeo-enrich");
  if (last.includes("Brevo")) setStep("brevo");
}

function renderContacts(contacts) {
  contactsTable.innerHTML = contacts
    .map(
      (c) => `
      <tr>
        <td>${escapeHtml(c.company_name || c.company_domain || "—")}</td>
        <td>${escapeHtml(c.full_name || "—")}</td>
        <td>${escapeHtml(c.job_title || "—")}</td>
        <td>${
          c.linkedin_url
            ? `<a href="${escapeHtml(c.linkedin_url)}" target="_blank" rel="noopener">Profile</a>`
            : "—"
        }</td>
        <td>${escapeHtml(c.email || "—")}</td>
      </tr>`
    )
    .join("");
  contactCount.textContent = `${contacts.length} contacts`;
  resultsCard.classList.remove("hidden");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function pollStatus() {
  if (!currentJobId) return;

  const res = await fetch(`/api/status/${currentJobId}`);
  const data = await res.json();
  if (!data.ok) return;

  renderLogs(data.logs || []);

  if (data.status === "running" || data.status === "sending") {
    setBadge(data.status === "sending" ? "Sending..." : "Running...", "running");
    return;
  }

  clearInterval(pollTimer);
  pollTimer = null;
  runBtn.disabled = false;
  sendBtn.disabled = false;

  const result = data.result || {};
  if (result.contacts?.length) {
    renderContacts(result.contacts);
    document.querySelectorAll(".step").forEach((step) => {
      step.classList.add("done");
      step.classList.remove("active");
    });
  }

  if (data.status === "done" && result.awaiting_confirmation && !result.dry_run) {
    setBadge("Awaiting confirmation", "done");
    confirmArea.classList.remove("hidden");
  } else if (data.status === "sent") {
    setBadge(`Sent (${data.send_result?.sent || 0})`, "sent");
    confirmArea.classList.add("hidden");
  } else if (data.status === "error") {
    setBadge("Error", "error");
    renderLogs([
      ...(data.logs || []),
      { message: data.error || "Something went wrong.", level: "error" },
    ]);
  } else {
    setBadge(result.dry_run ? "Dry run complete" : "Done", "done");
    confirmArea.classList.add("hidden");
  }
}

runBtn.addEventListener("click", async () => {
  runBtn.disabled = true;
  sendBtn.disabled = true;
  confirmArea.classList.add("hidden");
  resultsCard.classList.add("hidden");
  logsEl.innerHTML = "";
  setBadge("Starting...", "running");
  setStep("ocean");

  const res = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      domain: domainInput.value.trim(),
      limit: Number(limitInput.value),
      dry_run: dryRunInput.checked,
    }),
  });

  const data = await res.json();
  if (!data.ok) {
    setBadge("Error", "error");
    renderLogs([{ message: data.error || "Failed to start.", level: "error" }]);
    runBtn.disabled = false;
    return;
  }

  currentJobId = data.job_id;
  pollTimer = setInterval(pollStatus, 1200);
  pollStatus();
});

sendBtn.addEventListener("click", async () => {
  if (!currentJobId) return;
  const confirmed = window.confirm("Send outreach emails to all contacts in the summary?");
  if (!confirmed) return;

  sendBtn.disabled = true;
  setBadge("Sending...", "running");
  setStep("brevo");

  const res = await fetch(`/api/send/${currentJobId}`, { method: "POST" });
  const data = await res.json();
  if (!data.ok) {
    setBadge("Error", "error");
    renderLogs([{ message: data.error || "Send failed.", level: "error" }]);
    sendBtn.disabled = false;
    return;
  }

  if (!pollTimer) {
    pollTimer = setInterval(pollStatus, 1200);
  }
  pollStatus();
});
