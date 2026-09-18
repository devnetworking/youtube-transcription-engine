(function () {
  "use strict";
  const D = window.Docs;

  const urlInput = document.getElementById("youtube-url");
  const urlError = document.getElementById("url-error");
  const getBtn = document.getElementById("get-transcript-btn");
  const previewPanel = document.getElementById("preview-panel");
  const optionsWrap = document.getElementById("options-panel-wrap");
  const generateBtn = document.getElementById("generate-btn");
  const languageSelect = document.getElementById("opt-language");
  const jobsList = document.getElementById("jobs-list");

  let lastPreview = null;

  function showError(message) {
    urlError.textContent = message;
    urlError.classList.remove("hidden");
    previewPanel.classList.add("hidden");
    optionsWrap.classList.add("hidden");
  }

  function clearError() {
    urlError.classList.add("hidden");
    urlError.textContent = "";
  }

  function formatDuration(seconds) {
    if (seconds == null) return "Unknown";
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  async function runPreview() {
    const url = urlInput.value.trim();
    if (!url) { showError("Enter a YouTube URL first."); return; }
    clearError();
    getBtn.disabled = true;
    previewPanel.classList.remove("hidden");
    previewPanel.innerHTML = `<div class="skeleton" style="height:90px;border-radius:10px;"></div>`;
    try {
      const preview = await D.apiFetch("/api/youtube/preview", { method: "POST", body: { url } });
      lastPreview = preview;
      renderPreview(preview, url);
      optionsWrap.classList.remove("hidden");
    } catch (e) {
      lastPreview = null;
      showError(e.message);
    } finally {
      getBtn.disabled = false;
    }
  }

  function renderPreview(preview, rawUrl) {
    if (preview.is_playlist) {
      previewPanel.innerHTML = `
        <div class="flex center gap-12">
          <div class="icon-badge" data-icon="youtube"></div>
          <div>
            <h3 style="margin:0 0 2px;font-size:0.95rem;">This is a playlist</h3>
            <p class="muted" style="margin:0;font-size:0.85rem;">
              ${preview.video_count} video(s) will be processed as separate transcripts
              ${preview.truncated ? ` (playlist has ${preview.total_found}; capped at ${preview.video_count})` : ""}.
            </p>
          </div>
        </div>`;
      D.hydrateIcons(previewPanel);
      languageSelect.innerHTML = `<option value="auto">Auto detect</option>`;
      return;
    }

    const captionsNote = preview.captions_available
      ? `<span class="badge completed"><span class="dot"></span>Captions available</span>`
      : `<span class="badge queued"><span class="dot"></span>No captions - will use local speech recognition</span>`;

    previewPanel.innerHTML = `
      <div class="flex gap-12" style="align-items:flex-start;">
        <div style="width:160px;flex:none;border-radius:8px;overflow:hidden;background:var(--bg);border:1px solid var(--border);">
          ${preview.thumbnail ? `<img src="${preview.thumbnail}" alt="" style="width:100%;display:block;">` : `<div style="height:90px;"></div>`}
        </div>
        <div style="min-width:0;flex:1;">
          <h3 style="margin:0 0 4px;font-size:1rem;">${D.escapeHtml(preview.title || "Untitled video")}</h3>
          <p class="muted" style="margin:0 0 8px;font-size:0.85rem;">${D.escapeHtml(preview.channel || "Unknown channel")} &middot; ${formatDuration(preview.duration_seconds)}${preview.publication_date ? " &middot; " + D.escapeHtml(preview.publication_date) : ""}</p>
          ${captionsNote}
        </div>
      </div>`;

    languageSelect.innerHTML = `<option value="auto">Auto detect</option>` + (preview.languages || []).map((l) =>
      `<option value="${l.code}">${D.escapeHtml(l.name)}${l.is_generated ? " (auto-generated)" : ""}</option>`
    ).join("");
  }

  getBtn.addEventListener("click", runPreview);
  urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") runPreview(); });

  function currentOptions() {
    return {
      language: languageSelect.value,
      whisper_model: document.getElementById("opt-model").value,
      force_whisper: document.getElementById("opt-force-whisper").checked,
      timestamps: document.getElementById("opt-timestamps").checked,
      chapter_detection: document.getElementById("opt-chapters").checked,
      generate_summary: document.getElementById("opt-summary").checked,
      research_mode: document.getElementById("opt-research").checked,
      remove_filler_words: document.getElementById("opt-filler").checked,
      generate_txt: document.getElementById("opt-txt").checked,
      generate_metadata: document.getElementById("opt-metadata").checked,
    };
  }

  generateBtn.addEventListener("click", async () => {
    const url = (lastPreview && lastPreview.url) || urlInput.value.trim();
    if (!url) return;
    generateBtn.disabled = true;
    try {
      const result = await D.apiFetch("/api/documents/youtube-transcript", {
        method: "POST",
        body: { url, options: currentOptions() },
      });
      const preview = lastPreview;
      result.jobs.forEach((job) => addJobCard(job, preview));
      D.toast(`${result.jobs.length} transcript job(s) started.`, { type: "success" });
    } catch (e) {
      D.toast(e.message, { type: "error" });
    }
    generateBtn.disabled = false;
  });

  // ---- job cards --------------------------------------------------------

  function stageListHtml(job) {
    return `<div class="stage-list">${(job.stages || []).map((s) => `
      <div class="stage-item ${s.status}">
        <span class="stage-dot">${s.status === "done" ? D.icon("check") : ""}</span>
        <span>${D.escapeHtml(s.label)}</span>
      </div>`).join("")}</div>`;
  }

  function logsHtml(job) {
    if (!job.logs || !job.logs.length) return "";
    return `<div class="logs" style="margin-top:10px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:0.76rem;max-height:160px;overflow-y:auto;background:var(--bg);border-radius:8px;padding:8px 10px;">
      ${job.logs.map((entry) => `<div style="color:${entry.level === "error" ? "var(--err)" : entry.level === "warning" ? "var(--warn)" : entry.level === "success" ? "var(--ok)" : "var(--muted)"};">${D.escapeHtml(entry.message)}</div>`).join("")}
    </div>`;
  }

  function addJobCard(job, preview) {
    const card = D.el("div", "panel");
    card.id = "job-" + job.id;
    card.style.marginBottom = "14px";
    card.dataset.preview = preview ? JSON.stringify(preview) : "";
    jobsList.insertBefore(card, jobsList.firstChild);
    renderJobCard(card, job);
    pollJob(job.id, card);
  }

  function renderJobCard(card, job) {
    const pct = Math.round((job.progress || 0) * 100);
    card.innerHTML = `
      <div class="flex between center">
        <div class="flex center gap-8">${D.statusBadge(job.status)}<strong>${D.escapeHtml((job.result_summary && job.result_summary.title) || "YouTube Transcript")}</strong></div>
        <div class="flex gap-8" data-role="actions"></div>
      </div>
      <div style="margin-top:10px;">
        ${job.status === "processing" || job.status === "queued" ? `
          <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
          <div class="muted" style="font-size:0.78rem;margin-top:6px;">${D.escapeHtml(job.stage ? nicifyStage(job, job.stage) : "Waiting to start...")}</div>
        ` : ""}
        ${job.status === "failed" ? `<div class="text-err" style="font-size:0.86rem;">${D.escapeHtml(job.error_message || "Transcription failed.")}</div>` : ""}
        ${job.status === "completed" ? renderResultSummary(job) : ""}
      </div>
      <details style="margin-top:10px;"><summary class="muted" style="cursor:pointer;font-size:0.78rem;">Details</summary>
        <div style="margin-top:10px;">${stageListHtml(job)}${logsHtml(job)}</div>
      </details>
      <div data-role="workspace"></div>
    `;

    const actions = card.querySelector('[data-role="actions"]');
    if (job.status === "processing" || job.status === "queued") {
      const cancelBtn = D.el("button", "btn ghost small", ["Cancel"]);
      cancelBtn.addEventListener("click", () => D.apiFetch(`/api/document-jobs/${job.id}/cancel`, { method: "POST" }).catch((e) => D.toast(e.message, { type: "error" })));
      actions.appendChild(cancelBtn);
    }
    if (job.status === "failed") {
      const retryBtn = D.el("button", "btn small", ["Retry"]);
      retryBtn.innerHTML = D.icon("retry") + " Retry";
      retryBtn.addEventListener("click", async () => {
        try {
          const res = await D.apiFetch(`/api/document-jobs/${job.id}/retry`, { method: "POST" });
          renderJobCard(card, res.job);
          pollJob(job.id, card);
        } catch (e) { D.toast(e.message, { type: "error" }); }
      });
      actions.appendChild(retryBtn);
    }
    if (job.status === "completed") {
      const openBtn = D.el("button", "btn small", ["Open Transcript"]);
      openBtn.addEventListener("click", () => toggleWorkspace(card, job.id));
      actions.appendChild(openBtn);
      const downloadAllBtn = D.el("button", "btn ghost small", []);
      downloadAllBtn.innerHTML = D.icon("download") + " Download all";
      downloadAllBtn.addEventListener("click", () => downloadAll(job.id));
      actions.appendChild(downloadAllBtn);
    }
  }

  function nicifyStage(job, key) {
    const stage = (job.stages || []).find((s) => s.key === key);
    return stage ? stage.label + "..." : "Processing...";
  }

  function renderResultSummary(job) {
    const s = job.result_summary || {};
    const parts = [];
    if (s.quality) parts.push(`${s.quality} quality`);
    if (s.source) parts.push(`source: ${s.source}`);
    let html = `<div style="font-size:0.86rem;">Transcript ready${parts.length ? " - " + parts.join(" &middot; ") : ""}.</div>`;
    if (s.warnings && s.warnings.length) {
      html += s.warnings.map((w) => `<div class="text-err" style="font-size:0.82rem;margin-top:4px;">${D.escapeHtml(w)}</div>`).join("");
    }
    return html;
  }

  async function downloadAll(jobId) {
    try {
      const data = await D.apiFetch(`/api/document-jobs/${jobId}`);
      const zip = (data.outputs || []).find((o) => o.output_type === "zip");
      const target = zip || (data.outputs || [])[0];
      if (target) window.location.href = `/api/document-jobs/${jobId}/download/${target.id}`;
    } catch (e) { D.toast(e.message, { type: "error" }); }
  }

  async function toggleWorkspace(card, jobId) {
    const container = card.querySelector('[data-role="workspace"]');
    if (container.dataset.open === "1") { container.innerHTML = ""; container.dataset.open = "0"; return; }
    container.dataset.open = "1";
    container.innerHTML = `<div class="skeleton" style="height:320px;border-radius:10px;margin-top:14px;"></div>`;
    let preview = null;
    try { preview = card.dataset.preview ? JSON.parse(card.dataset.preview) : null; } catch (e) { preview = null; }

    try {
      const [jobData, mdPreview] = await Promise.all([
        D.apiFetch(`/api/document-jobs/${jobId}`),
        D.apiFetch(`/api/document-jobs/${jobId}/preview`),
      ]);
      const outputs = jobData.outputs || [];
      const mdOutput = outputs.find((o) => o.output_type === "markdown");
      const txtOutput = outputs.find((o) => o.output_type === "text");
      const metaOutput = outputs.find((o) => o.filename === "metadata.json");

      const videoInfoHtml = preview && !preview.is_playlist ? `
        ${preview.thumbnail ? `<img src="${preview.thumbnail}" alt="" style="width:100%;border-radius:8px;margin-bottom:12px;">` : ""}
        <h3 style="margin:0 0 6px;font-size:0.95rem;">${D.escapeHtml(preview.title || "")}</h3>
        <p class="muted" style="font-size:0.84rem;margin:0 0 4px;">${D.escapeHtml(preview.channel || "")}</p>
        <p class="muted" style="font-size:0.84rem;margin:0;">${formatDuration(preview.duration_seconds)}${preview.publication_date ? " &middot; " + D.escapeHtml(preview.publication_date) : ""}</p>
      ` : `<p class="muted" style="font-size:0.85rem;">${D.escapeHtml((jobData.job.result_summary && jobData.job.result_summary.title) || "Video information unavailable.")}</p>`;

      container.innerHTML = `
        <div class="split-view" style="margin-top:14px;min-height:420px;">
          <div class="split-pane">
            <div class="pane-head">Video</div>
            <div class="pane-body">${videoInfoHtml}</div>
          </div>
          <div class="split-pane">
            <div class="pane-head"><span>Transcript</span></div>
            <div class="pane-body" style="padding:14px;" data-role="md-viewer"></div>
          </div>
        </div>
        <div class="flex gap-8 wrap" style="margin-top:12px;">
          ${txtOutput ? `<a class="btn ghost small" href="/api/document-jobs/${jobId}/download/${txtOutput.id}">Download .txt</a>` : ""}
          ${metaOutput ? `<a class="btn ghost small" href="/api/document-jobs/${jobId}/download/${metaOutput.id}">Download metadata</a>` : ""}
        </div>
      `;
      D.createMarkdownViewer(container.querySelector('[data-role="md-viewer"]'), {
        markdown: mdPreview.markdown,
        downloadUrl: mdOutput ? `/api/document-jobs/${jobId}/download/${mdOutput.id}` : null,
        supportsClean: true,
      });
    } catch (e) {
      container.innerHTML = `<div class="text-err" style="margin-top:14px;">${D.escapeHtml(e.message)}</div>`;
    }
  }

  const activeJobs = new Map();
  function pollJob(jobId, card) {
    if (activeJobs.has(jobId)) return;
    const timer = setInterval(async () => {
      try {
        const data = await D.apiFetch(`/api/document-jobs/${jobId}`);
        renderJobCard(card, data.job);
        if (["completed", "failed", "cancelled"].includes(data.job.status)) {
          clearInterval(timer);
          activeJobs.delete(jobId);
        }
      } catch (e) {
        clearInterval(timer);
        activeJobs.delete(jobId);
      }
    }, 1500);
    activeJobs.set(jobId, timer);
  }
})();
