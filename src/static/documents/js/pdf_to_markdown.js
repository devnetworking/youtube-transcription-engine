(function () {
  "use strict";
  const D = window.Docs;

  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const fileList = document.getElementById("file-list");
  const convertBtn = document.getElementById("convert-btn");
  const jobsList = document.getElementById("jobs-list");

  let pending = []; // {id, file, xhr, status, progress, error}
  const activeJobs = new Map(); // job_id -> {timer}

  function uid() { return Math.random().toString(36).slice(2); }

  function renderPending() {
    fileList.innerHTML = "";
    pending.forEach((entry) => {
      const row = D.el("div", "file-row");
      row.innerHTML = `
        <div class="thumb" data-icon="markdown"></div>
        <div class="meta">
          <div class="name">${D.escapeHtml(entry.file.name)}</div>
          <div class="sub">${D.formatBytes(entry.file.size)} ${entry.status === "error" ? "&middot; <span class=\"text-err\">" + D.escapeHtml(entry.error) + "</span>" : ""}</div>
          ${entry.status === "uploading" ? '<div class="progress-track" style="margin-top:6px;"><div class="progress-fill" style="width:' + Math.round(entry.progress * 100) + '%"></div></div>' : ""}
        </div>
        <button class="icon-btn remove-btn" title="Remove" ${entry.status === "uploading" ? "disabled" : ""}>${D.icon("x")}</button>
      `;
      row.querySelector(".remove-btn").addEventListener("click", () => {
        if (entry.xhr) entry.xhr.abort();
        pending = pending.filter((p) => p.id !== entry.id);
        renderPending();
        updateConvertButton();
      });
      fileList.appendChild(row);
      D.hydrateIcons(row);
    });
  }

  function updateConvertButton() {
    convertBtn.disabled = pending.length === 0 || pending.some((p) => p.status === "uploading");
  }

  function addFiles(fileArray) {
    Array.from(fileArray).forEach((file) => {
      if (file.type && file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
        D.toast(`"${file.name}" is not a PDF and was skipped.`, { type: "error" });
        return;
      }
      pending.push({ id: uid(), file, status: "pending", progress: 0 });
    });
    renderPending();
    updateConvertButton();
  }

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    addFiles(e.dataTransfer.files);
  });
  fileInput.addEventListener("change", () => { addFiles(fileInput.files); fileInput.value = ""; });

  function uploadOne(entry) {
    return new Promise((resolve) => {
      entry.status = "uploading";
      entry.progress = 0;
      renderPending();
      const xhr = new XMLHttpRequest();
      entry.xhr = xhr;
      xhr.open("POST", "/api/documents/upload");
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) { entry.progress = e.loaded / e.total; renderPending(); }
      };
      xhr.onload = () => {
        let data = {};
        try { data = JSON.parse(xhr.responseText); } catch (e) { /* ignore */ }
        if (xhr.status >= 200 && xhr.status < 300 && data.documents && data.documents.length) {
          entry.status = "done";
          resolve(data.documents[0]);
        } else {
          entry.status = "error";
          entry.error = (data.errors && data.errors[0] && data.errors[0].error) || data.error || "Upload failed.";
          resolve(null);
        }
        renderPending();
      };
      xhr.onerror = () => { entry.status = "error"; entry.error = "Network error during upload."; renderPending(); resolve(null); };
      xhr.onabort = () => resolve(null);
      const formData = new FormData();
      formData.append("file", entry.file);
      xhr.send(formData);
    });
  }

  function currentOptions() {
    return {
      detect_headings: document.getElementById("opt-headings").checked,
      preserve_lists: document.getElementById("opt-lists").checked,
      detect_tables: document.getElementById("opt-tables").checked,
      extract_links: document.getElementById("opt-links").checked,
      preserve_page_references: document.getElementById("opt-page-refs").checked,
      extract_images: document.getElementById("opt-images").checked,
      ignore_decorative_images: document.getElementById("opt-decorative").checked,
      language: document.getElementById("opt-language").value,
      ocr_mode: document.getElementById("opt-ocr").value,
      generate_txt: document.getElementById("opt-txt").checked,
      generate_metadata: document.getElementById("opt-metadata").checked,
      export_assets: true,
    };
  }

  convertBtn.addEventListener("click", async () => {
    convertBtn.disabled = true;
    const toUpload = pending.filter((p) => p.status !== "done");
    const alreadyReady = pending.filter((p) => p.status === "done" && p.document).map((p) => p.document);
    const uploaded = await Promise.all(toUpload.map(uploadOne));
    const documentIds = alreadyReady.concat(uploaded.filter(Boolean)).map((d) => d.id);
    pending = pending.filter((p) => p.status !== "done");
    renderPending();

    if (!documentIds.length) {
      updateConvertButton();
      return;
    }

    try {
      const result = await D.apiFetch("/api/documents/convert/markdown", {
        method: "POST",
        body: { document_ids: documentIds, options: currentOptions() },
      });
      (result.jobs || []).forEach((job) => addJobCard(job));
      D.toast(`${result.jobs.length} conversion(s) started.`, { type: "success" });
    } catch (err) {
      D.toast(err.message, { type: "error" });
    }
    updateConvertButton();
  });

  // ---- job cards --------------------------------------------------------

  function stageListHtml(job) {
    return `<div class="stage-list">${(job.stages || []).map((s) => `
      <div class="stage-item ${s.status}">
        <span class="stage-dot">${s.status === "done" ? D.icon("check") : ""}</span>
        <span>${D.escapeHtml(s.label)}</span>
      </div>`).join("")}</div>`;
  }

  function addJobCard(job) {
    const card = D.el("div", "panel");
    card.id = "job-" + job.id;
    card.style.marginBottom = "14px";
    jobsList.insertBefore(card, jobsList.firstChild);
    renderJobCard(card, job);
    pollJob(job.id, card);
  }

  function renderJobCard(card, job) {
    const pct = Math.round((job.progress || 0) * 100);
    card.innerHTML = `
      <div class="flex between center">
        <div class="flex center gap-8">${D.statusBadge(job.status)}<strong>Convert &rarr; Markdown</strong></div>
        <div class="flex gap-8" data-role="actions"></div>
      </div>
      <div style="margin-top:10px;">
        ${job.status === "processing" || job.status === "queued" ? `
          <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
          <div class="muted" style="font-size:0.78rem;margin-top:6px;">${D.escapeHtml(job.stage || "Waiting to start...")}</div>
        ` : ""}
        ${job.status === "failed" ? `<div class="text-err" style="font-size:0.86rem;">${D.escapeHtml(job.error_message || "Conversion failed.")}</div>` : ""}
        ${job.status === "completed" ? renderResultSummary(job) : ""}
      </div>
      <details style="margin-top:10px;"><summary class="muted" style="cursor:pointer;font-size:0.78rem;">Details</summary>
        <div style="margin-top:10px;">${stageListHtml(job)}</div>
      </details>
      <div data-role="preview"></div>
    `;

    const actions = card.querySelector('[data-role="actions"]');
    if (job.status === "processing" || job.status === "queued") {
      const cancelBtn = D.el("button", "btn ghost small", ["Cancel"]);
      cancelBtn.addEventListener("click", async () => {
        await D.apiFetch(`/api/document-jobs/${job.id}/cancel`, { method: "POST" }).catch((e) => D.toast(e.message, { type: "error" }));
      });
      actions.appendChild(cancelBtn);
    }
    if (job.status === "failed") {
      const retryBtn = D.el("button", "btn small", [D.icon("retry") + " Retry"]);
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
      const previewBtn = D.el("button", "btn small", []);
      previewBtn.innerHTML = "Preview";
      previewBtn.addEventListener("click", () => togglePreview(card, job.id));
      actions.appendChild(previewBtn);
      const downloadBtn = document.createElement("a");
      downloadBtn.className = "btn ghost small";
      downloadBtn.innerHTML = D.icon("download") + " Download package";
      downloadBtn.href = `/documents/jobs?open=${job.id}`;
      downloadBtn.addEventListener("click", (e) => { e.preventDefault(); downloadAll(job.id); });
      actions.appendChild(downloadBtn);
    }
  }

  function renderResultSummary(job) {
    const s = job.result_summary || {};
    const parts = [];
    if (s.pages != null) parts.push(`${s.pages} pages`);
    if (s.tables_detected) parts.push(`${s.tables_detected} table(s)`);
    if (s.images_extracted) parts.push(`${s.images_extracted} image(s)`);
    if (s.ocr_used) parts.push("OCR used");
    let html = `<div style="font-size:0.86rem;">Conversion completed - ${parts.join(" &middot; ") || "no content detected"}.</div>`;
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

  async function togglePreview(card, jobId) {
    const container = card.querySelector('[data-role="preview"]');
    if (container.dataset.open === "1") { container.innerHTML = ""; container.dataset.open = "0"; return; }
    container.dataset.open = "1";
    container.innerHTML = `<div class="skeleton" style="height:300px;border-radius:10px;margin-top:14px;"></div>`;
    try {
      const [jobData, preview] = await Promise.all([
        D.apiFetch(`/api/document-jobs/${jobId}`),
        D.apiFetch(`/api/document-jobs/${jobId}/preview`),
      ]);
      const documentId = jobData.job.input_document_ids[0];
      const mdOutput = jobData.outputs.find((o) => o.output_type === "markdown");
      container.innerHTML = `
        <div class="split-view" style="margin-top:14px;min-height:420px;">
          <div class="split-pane">
            <div class="pane-head">Original PDF</div>
            <div class="pane-body" style="padding:0;"><iframe class="pdf-frame" src="/api/documents/${documentId}/download"></iframe></div>
          </div>
          <div class="split-pane">
            <div class="pane-head"><span>Markdown</span></div>
            <div class="pane-body" style="padding:14px;" data-role="md-viewer"></div>
          </div>
        </div>
      `;
      D.createMarkdownViewer(container.querySelector('[data-role="md-viewer"]'), {
        markdown: preview.markdown,
        downloadUrl: mdOutput ? `/api/document-jobs/${jobId}/download/${mdOutput.id}` : null,
      });
    } catch (e) {
      container.innerHTML = `<div class="text-err" style="margin-top:14px;">${D.escapeHtml(e.message)}</div>`;
    }
  }

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

  updateConvertButton();

  // Preselect a document when linked from Files ("Convert" context action).
  const params = new URLSearchParams(window.location.search);
  const preselect = params.get("document_id");
  if (preselect) {
    D.apiFetch(`/api/documents/${preselect}`).then((data) => {
      const doc = data.document;
      pending.push({ id: uid(), file: { name: doc.original_name, size: doc.file_size }, status: "done", document: doc });
      renderPending();
      updateConvertButton();
    }).catch(() => {});
  }
})();
