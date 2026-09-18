(function () {
  "use strict";
  const D = window.Docs;

  const uploadPanel = document.getElementById("upload-panel");
  const splitPanel = document.getElementById("split-panel");
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const jobsList = document.getElementById("jobs-list");

  let document_ = null; // the selected Document
  let mode = "ranges";
  const PAGE_BATCH = 100;
  let thumbOffset = 0;
  let selectedPages = new Set();

  function uid() { return Math.random().toString(36).slice(2); }

  async function selectDocument(doc) {
    document_ = doc;
    uploadPanel.classList.add("hidden");
    splitPanel.classList.remove("hidden");
    document.getElementById("doc-name").textContent = doc.original_name;
    document.getElementById("doc-meta").textContent = `${doc.page_count} page(s) - ${D.formatBytes(doc.file_size)}`;
    document.getElementById("doc-thumb").innerHTML = `<img src="/api/documents/${doc.id}/thumbnail/0?size=90" style="width:100%;height:100%;object-fit:cover;">`;
    updateNamingPreview();
  }

  function uploadFile(file) {
    const formData = new FormData();
    formData.append("file", file);
    return D.apiFetch("/api/documents/upload", { method: "POST", body: formData }).then((data) => {
      if (data.documents && data.documents.length) return data.documents[0];
      throw new Error((data.errors && data.errors[0] && data.errors[0].error) || "Upload failed.");
    });
  }

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]).then(selectDocument).catch((err) => D.toast(err.message, { type: "error" }));
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) uploadFile(fileInput.files[0]).then(selectDocument).catch((err) => D.toast(err.message, { type: "error" }));
    fileInput.value = "";
  });

  document.getElementById("change-doc-btn").addEventListener("click", () => {
    document_ = null;
    splitPanel.classList.add("hidden");
    uploadPanel.classList.remove("hidden");
  });

  // ---- mode tabs -----------------------------------------------------------

  document.querySelectorAll("#mode-tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#mode-tabs button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      mode = btn.dataset.mode;
      document.querySelectorAll(".mode-panel").forEach((p) => p.classList.add("hidden"));
      const key = mode === "visual" ? "visual" : mode;
      document.getElementById("mode-" + key).classList.remove("hidden");
      document.getElementById("naming-field").classList.toggle("hidden", mode === "extract_pages" || mode === "visual");
      if (mode === "visual") loadThumbGrid();
      updateNamingPreview();
    });
  });

  // ---- naming preview --------------------------------------------------------

  function updateNamingPreview() {
    if (!document_) return;
    const pattern = document.getElementById("naming-pattern").value;
    const stem = document_.original_name.replace(/\.pdf$/i, "");
    const preview = pattern
      .replace("{original_name}", stem)
      .replace("{index}", "01")
      .replace("{start_page}", "1")
      .replace("{end_page}", "10");
    document.getElementById("naming-preview").textContent = `Preview: ${preview}.pdf`;
  }
  document.getElementById("naming-pattern").addEventListener("input", updateNamingPreview);

  // ---- visual page grid (paginated + lazy thumbnails) --------------------------

  function loadThumbGrid() {
    const grid = document.getElementById("thumb-grid");
    grid.innerHTML = "";
    const total = document_.page_count;
    const end = Math.min(thumbOffset + PAGE_BATCH, total);
    document.getElementById("thumb-range").textContent = `Pages ${thumbOffset + 1}-${end} of ${total}`;
    document.getElementById("thumb-prev").disabled = thumbOffset === 0;
    document.getElementById("thumb-next").disabled = end >= total;

    const cells = [];
    for (let p = thumbOffset; p < end; p++) {
      const cell = D.el("div", "thumb-cell" + (selectedPages.has(p + 1) ? " selected" : ""));
      cell.dataset.page = String(p + 1);
      cell.innerHTML = `<div class="check"></div><span class="page-num">${p + 1}</span>`;
      cell.addEventListener("click", () => {
        const page = Number(cell.dataset.page);
        if (selectedPages.has(page)) selectedPages.delete(page); else selectedPages.add(page);
        cell.classList.toggle("selected");
      });
      grid.appendChild(cell);
      cells.push(cell);
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const cell = entry.target;
          if (!cell.dataset.loaded) {
            const img = document.createElement("img");
            img.src = `/api/documents/${document_.id}/thumbnail/${Number(cell.dataset.page) - 1}?size=200`;
            cell.appendChild(img);
            cell.dataset.loaded = "1";
          }
          observer.unobserve(cell);
        }
      });
    }, { rootMargin: "200px" });
    cells.forEach((c) => observer.observe(c));
  }

  document.getElementById("thumb-prev").addEventListener("click", () => { thumbOffset = Math.max(0, thumbOffset - PAGE_BATCH); loadThumbGrid(); });
  document.getElementById("thumb-next").addEventListener("click", () => { thumbOffset += PAGE_BATCH; loadThumbGrid(); });

  // ---- submit ---------------------------------------------------------------

  document.getElementById("split-btn").addEventListener("click", async () => {
    if (!document_) return;
    let payload = { document_id: document_.id, mode, naming_pattern: document.getElementById("naming-pattern").value };

    if (mode === "ranges") {
      payload.ranges = document.getElementById("ranges-input").value;
      if (!payload.ranges.trim()) { D.toast("Enter at least one page range.", { type: "error" }); return; }
    } else if (mode === "every_n_pages") {
      payload.every_n_pages = Number(document.getElementById("every-n-input").value) || 1;
    } else if (mode === "extract_pages") {
      payload.ranges = document.getElementById("extract-input").value;
      payload.mode = "extract_pages";
      if (!payload.ranges.trim()) { D.toast("Enter at least one page.", { type: "error" }); return; }
    } else if (mode === "every_page") {
      payload.mode = "every_page";
      if (document_.page_count > 300) {
        const ok = await D.confirmDialog({
          title: "Split into many files?",
          message: `This will produce ${document_.page_count} separate PDF files, delivered as a ZIP. Continue?`,
          confirmLabel: "Split into " + document_.page_count + " files",
        });
        if (!ok) return;
      }
    } else if (mode === "visual") {
      if (!selectedPages.size) { D.toast("Select at least one page.", { type: "error" }); return; }
      payload.mode = "extract_pages";
      payload.ranges = Array.from(selectedPages).sort((a, b) => a - b).join(",");
    }

    try {
      const result = await D.apiFetch("/api/documents/split", { method: "POST", body: payload });
      addJobCard(result.job);
      D.toast("Split started.", { type: "success" });
    } catch (e) {
      D.toast(e.message, { type: "error" });
    }
  });

  function addJobCard(job) {
    const card = D.el("div", "panel");
    card.style.marginBottom = "14px";
    jobsList.insertBefore(card, jobsList.firstChild);
    renderCard(card, job);
    const timer = setInterval(async () => {
      try {
        const data = await D.apiFetch(`/api/document-jobs/${job.id}`);
        renderCard(card, data.job, data.outputs);
        if (["completed", "failed", "cancelled"].includes(data.job.status)) clearInterval(timer);
      } catch (e) { clearInterval(timer); }
    }, 1500);
  }

  function renderCard(card, job, outputs) {
    const pct = Math.round((job.progress || 0) * 100);
    let resultHtml = "";
    if (job.status === "completed" && outputs) {
      const zip = outputs.find((o) => o.output_type === "zip");
      const files = outputs.filter((o) => o.output_type === "pdf");
      resultHtml = `<div style="font-size:0.86rem;margin-top:8px;">Produced ${files.length} file(s).</div>`;
      resultHtml += `<div class="flex gap-8 wrap" style="margin-top:8px;">`;
      if (zip) resultHtml += `<a class="btn small" href="/api/document-jobs/${job.id}/download/${zip.id}">${D.icon("download")} Download all (ZIP)</a>`;
      files.slice(0, 6).forEach((f) => {
        resultHtml += `<a class="btn ghost small" href="/api/document-jobs/${job.id}/download/${f.id}">${D.escapeHtml(f.filename)}</a>`;
      });
      if (files.length > 6) resultHtml += `<span class="muted" style="font-size:0.8rem;align-self:center;">+${files.length - 6} more</span>`;
      resultHtml += `</div>`;
    }
    card.innerHTML = `
      <div class="flex between center">
        <div class="flex center gap-8">${D.statusBadge(job.status)}<strong>Split PDF</strong></div>
        ${job.status === "failed" ? '<button class="btn small retry-btn">Retry</button>' : ""}
      </div>
      ${job.status === "processing" || job.status === "queued" ? `
        <div class="progress-track" style="margin-top:10px;"><div class="progress-fill" style="width:${pct}%"></div></div>
        <div class="muted" style="font-size:0.78rem;margin-top:6px;">${D.escapeHtml(job.stage || "Waiting...")}</div>` : ""}
      ${job.status === "failed" ? `<div class="text-err" style="font-size:0.86rem;margin-top:8px;">${D.escapeHtml(job.error_message || "Split failed.")}</div>` : ""}
      ${resultHtml}
    `;
    const retryBtn = card.querySelector(".retry-btn");
    if (retryBtn) retryBtn.addEventListener("click", async () => {
      try { const res = await D.apiFetch(`/api/document-jobs/${job.id}/retry`, { method: "POST" }); renderCard(card, res.job); }
      catch (e) { D.toast(e.message, { type: "error" }); }
    });
  }

  // Preselect a document when linked from Files ("Split" context action).
  const params = new URLSearchParams(window.location.search);
  const preselect = params.get("document_id");
  if (preselect) {
    D.apiFetch(`/api/documents/${preselect}`).then((data) => selectDocument(data.document)).catch(() => {});
  }
})();
