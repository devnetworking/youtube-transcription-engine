(function () {
  "use strict";
  const D = window.Docs;

  const table = document.getElementById("jobs-table");
  const filterStatus = document.getElementById("filter-status");
  const filterOperation = document.getElementById("filter-operation");
  const drawerRoot = document.getElementById("drawer-root");

  const OPERATION_LABEL = {
    pdf_to_markdown: "Convert &rarr; Markdown", merge: "Merge PDFs", split: "Split PDF",
    youtube_transcript: "YouTube Transcript",
  };

  const params = new URLSearchParams(window.location.search);
  if (params.get("status")) filterStatus.value = params.get("status");

  let pollTimer = null;

  function durationOf(job) {
    if (!job.started_at) return "-";
    const end = job.completed_at ? new Date(job.completed_at) : new Date();
    return D.formatDuration((end - new Date(job.started_at)) / 1000);
  }

  async function load() {
    const query = new URLSearchParams();
    if (filterStatus.value) query.set("status", filterStatus.value);
    if (filterOperation.value) query.set("operation", filterOperation.value);
    let data;
    try {
      data = await D.apiFetch("/api/document-jobs?" + query.toString());
    } catch (e) {
      table.innerHTML = `<div class="text-err">${D.escapeHtml(e.message)}</div>`;
      return;
    }
    renderTable(data.jobs);
    const hasActive = data.jobs.some((j) => j.status === "queued" || j.status === "processing");
    clearTimeout(pollTimer);
    if (hasActive) pollTimer = setTimeout(load, 2000);
  }

  function renderTable(jobs) {
    if (!jobs.length) {
      table.innerHTML = `
        <div class="empty-state">
          <div class="glyph" data-icon="jobs"></div>
          <h3>No jobs yet</h3>
          <p>Conversions, merges and splits will show up here once you start one.</p>
          <a class="btn primary" href="/documents/pdf-to-markdown">Start a conversion</a>
        </div>`;
      D.hydrateIcons(table);
      return;
    }
    table.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Job</th><th>Type</th><th>Progress</th><th>Started</th><th>Duration</th><th>Actions</th></tr></thead>
        <tbody>
          ${jobs.map((job) => `
            <tr data-job-id="${job.id}" style="cursor:pointer;">
              <td class="cell-muted">${job.id.slice(0, 8)}</td>
              <td>${OPERATION_LABEL[job.operation] || job.operation}</td>
              <td>
                ${job.status === "processing" || job.status === "queued" ? `
                  <div class="progress-track" style="width:120px;"><div class="progress-fill" style="width:${Math.round((job.progress || 0) * 100)}%"></div></div>
                ` : D.statusBadge(job.status)}
              </td>
              <td class="cell-muted">${D.timeAgo(job.started_at || job.created_at)}</td>
              <td class="cell-muted">${durationOf(job)}</td>
              <td data-role="row-actions"></td>
            </tr>
          `).join("")}
        </tbody>
      </table>`;

    jobs.forEach((job) => {
      const row = table.querySelector(`tr[data-job-id="${job.id}"]`);
      row.addEventListener("click", (e) => { if (!e.target.closest("button")) openDrawer(job.id); });
      const cell = row.querySelector('[data-role="row-actions"]');
      if (job.status === "failed") {
        const btn = D.el("button", "btn small", ["Retry"]);
        btn.addEventListener("click", async (e) => { e.stopPropagation(); await retry(job.id); });
        cell.appendChild(btn);
      } else if (job.status === "processing" || job.status === "queued") {
        const btn = D.el("button", "btn ghost small", ["Cancel"]);
        btn.addEventListener("click", async (e) => { e.stopPropagation(); await cancel(job.id); });
        cell.appendChild(btn);
      } else if (job.status === "completed") {
        const btn = D.el("button", "icon-btn", []);
        btn.innerHTML = D.icon("download");
        btn.title = "Download";
        btn.addEventListener("click", async (e) => { e.stopPropagation(); await downloadFirst(job.id); });
        cell.appendChild(btn);
      }
    });
  }

  async function retry(jobId) {
    try { await D.apiFetch(`/api/document-jobs/${jobId}/retry`, { method: "POST" }); D.toast("Retrying job.", { type: "success" }); load(); }
    catch (e) { D.toast(e.message, { type: "error" }); }
  }
  async function cancel(jobId) {
    try { await D.apiFetch(`/api/document-jobs/${jobId}/cancel`, { method: "POST" }); D.toast("Cancellation requested."); load(); }
    catch (e) { D.toast(e.message, { type: "error" }); }
  }
  async function downloadFirst(jobId) {
    try {
      const data = await D.apiFetch(`/api/document-jobs/${jobId}`);
      const zip = data.outputs.find((o) => o.output_type === "zip");
      const target = zip || data.outputs[0];
      if (target) window.location.href = `/api/document-jobs/${jobId}/download/${target.id}`;
    } catch (e) { D.toast(e.message, { type: "error" }); }
  }

  function stageHtml(job) {
    return (job.stages || []).map((s) => `
      <div class="stage-item ${s.status}">
        <span class="stage-dot">${s.status === "done" ? D.icon("check") : ""}</span>
        <span>${D.escapeHtml(s.label)}${s.status === "running" ? " - Processing..." : s.status === "waiting" ? " - Waiting" : ""}</span>
      </div>`).join("");
  }

  async function openDrawer(jobId) {
    drawerRoot.innerHTML = `<div class="overlay"></div><div class="drawer"><div class="drawer-body"><div class="skeleton" style="height:200px;"></div></div></div>`;
    drawerRoot.querySelector(".overlay").addEventListener("click", closeDrawer);
    let data;
    try {
      data = await D.apiFetch(`/api/document-jobs/${jobId}`);
    } catch (e) {
      D.toast(e.message, { type: "error" });
      closeDrawer();
      return;
    }
    const job = data.job;
    drawerRoot.querySelector(".drawer").innerHTML = `
      <div class="drawer-head">
        <div>
          <div class="muted" style="font-size:0.76rem;">JOB ${job.id}</div>
          <h3 style="margin:4px 0 0;font-size:1.05rem;">${OPERATION_LABEL[job.operation] || job.operation}</h3>
        </div>
        <button class="icon-btn" id="close-drawer">${D.icon("x")}</button>
      </div>
      <div class="drawer-body">
        <div class="flex center gap-8" style="margin-bottom:16px;">${D.statusBadge(job.status)} <span class="muted" style="font-size:0.82rem;">${durationOf(job)}</span></div>

        ${job.error_message ? `<div class="panel" style="background:var(--err-soft);border-color:transparent;margin-bottom:16px;"><strong style="font-size:0.85rem;">Error</strong><div style="font-size:0.85rem;margin-top:4px;">${D.escapeHtml(job.error_message)}</div></div>` : ""}

        <h4 style="font-size:0.78rem;text-transform:uppercase;letter-spacing:0.04em;color:var(--faint);margin-bottom:10px;">Processing stages</h4>
        <div class="stage-list" style="margin-bottom:20px;">${stageHtml(job)}</div>

        <h4 style="font-size:0.78rem;text-transform:uppercase;letter-spacing:0.04em;color:var(--faint);margin-bottom:10px;">Output files</h4>
        <div id="drawer-outputs">${(data.outputs || []).map((o) => `
          <a class="file-row" style="text-decoration:none;color:inherit;" href="/api/document-jobs/${job.id}/download/${o.id}">
            <div class="thumb">${D.icon(o.output_type === "zip" ? "zip" : "files")}</div>
            <div class="meta"><div class="name">${D.escapeHtml(o.filename)}</div><div class="sub">${D.formatBytes(o.file_size)}</div></div>
            <span class="icon-btn">${D.icon("download")}</span>
          </a>
        `).join("") || '<p class="muted" style="font-size:0.84rem;">No output files yet.</p>'}</div>

        <div class="flex gap-8" style="margin-top:20px;">
          ${job.status === "failed" ? '<button class="btn primary small" id="drawer-retry">Retry</button>' : ""}
          ${job.status === "processing" || job.status === "queued" ? '<button class="btn ghost small" id="drawer-cancel">Cancel</button>' : ""}
          <button class="btn ghost small" id="drawer-repeat">Run again</button>
        </div>
      </div>
    `;
    D.hydrateIcons(drawerRoot);
    document.getElementById("close-drawer").addEventListener("click", closeDrawer);
    const retryBtn = document.getElementById("drawer-retry");
    if (retryBtn) retryBtn.addEventListener("click", async () => { await retry(jobId); openDrawer(jobId); });
    const cancelBtn = document.getElementById("drawer-cancel");
    if (cancelBtn) cancelBtn.addEventListener("click", async () => { await cancel(jobId); openDrawer(jobId); });
    document.getElementById("drawer-repeat").addEventListener("click", async () => {
      try {
        await D.apiFetch(`/api/document-jobs/${jobId}/repeat`, { method: "POST" });
        D.toast("Started a new job with the same settings.", { type: "success" });
        closeDrawer();
        load();
      } catch (e) { D.toast(e.message, { type: "error" }); }
    });
  }

  function closeDrawer() { drawerRoot.innerHTML = ""; }

  filterStatus.addEventListener("change", load);
  filterOperation.addEventListener("change", load);

  const openParam = params.get("open");
  load().then(() => { if (openParam) openDrawer(openParam); });
})();
