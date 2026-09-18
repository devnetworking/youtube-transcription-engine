(function () {
  "use strict";
  const D = window.Docs;

  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const mergeList = document.getElementById("merge-list");
  const mergeBtn = document.getElementById("merge-btn");
  const outputName = document.getElementById("output-name");
  const jobsList = document.getElementById("jobs-list");

  let items = []; // {id, document, pageRanges, uploading, error}
  let dragIndex = null;

  function uid() { return Math.random().toString(36).slice(2); }

  function render() {
    if (!items.length) {
      mergeList.innerHTML = `<p class="muted" style="font-size:0.84rem;">No files added yet.</p>`;
      mergeBtn.disabled = true;
      return;
    }
    mergeList.innerHTML = "";
    items.forEach((item, index) => {
      const row = D.el("div", "file-row");
      row.draggable = !item.uploading;
      row.dataset.index = String(index);
      row.innerHTML = `
        <span class="drag-handle">${D.icon("dots")}</span>
        <div class="thumb">${item.document ? `<img src="/api/documents/${item.document.id}/thumbnail/0?size=80" alt="">` : ""}</div>
        <div class="meta">
          <div class="name">${index + 1}. ${D.escapeHtml(item.document ? item.document.original_name : item.name)}</div>
          <div class="sub">
            ${item.uploading ? "Uploading..." : item.document ? `${item.document.page_count} page(s) &middot; ${D.formatBytes(item.document.file_size)}` : (item.error || "")}
          </div>
          ${item.document ? `<input type="text" class="page-ranges-input" placeholder="All pages (e.g. 1-10,15)" value="${D.escapeHtml(item.pageRanges || "")}" style="margin-top:6px;max-width:260px;padding:5px 8px;font-size:0.78rem;">` : ""}
        </div>
        <div class="flex gap-8">
          <button class="icon-btn move-up" title="Move up" ${index === 0 ? "disabled" : ""}>&uarr;</button>
          <button class="icon-btn move-down" title="Move down" ${index === items.length - 1 ? "disabled" : ""}>&darr;</button>
          <button class="icon-btn remove-btn" title="Remove">${D.icon("x")}</button>
        </div>
      `;
      row.querySelector(".remove-btn").addEventListener("click", () => { items.splice(index, 1); render(); });
      row.querySelector(".move-up").addEventListener("click", () => { swap(index, index - 1); });
      row.querySelector(".move-down").addEventListener("click", () => { swap(index, index + 1); });
      const rangesInput = row.querySelector(".page-ranges-input");
      if (rangesInput) rangesInput.addEventListener("input", () => { item.pageRanges = rangesInput.value; });

      row.addEventListener("dragstart", () => { dragIndex = index; row.classList.add("dragging"); });
      row.addEventListener("dragend", () => row.classList.remove("dragging"));
      row.addEventListener("dragover", (e) => e.preventDefault());
      row.addEventListener("drop", (e) => {
        e.preventDefault();
        if (dragIndex === null || dragIndex === index) return;
        swap(dragIndex, index);
        dragIndex = null;
      });
      mergeList.appendChild(row);
    });
    mergeBtn.disabled = items.some((i) => i.uploading) || items.filter((i) => i.document).length < 1;
  }

  function swap(a, b) {
    if (b < 0 || b >= items.length) return;
    const tmp = items[a];
    items[a] = items[b];
    items[b] = tmp;
    render();
  }

  function addFiles(fileArray) {
    Array.from(fileArray).forEach((file) => {
      const item = { id: uid(), name: file.name, uploading: true };
      items.push(item);
      render();
      const formData = new FormData();
      formData.append("file", file);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/documents/upload");
      xhr.onload = () => {
        let data = {};
        try { data = JSON.parse(xhr.responseText); } catch (e) { /* ignore */ }
        item.uploading = false;
        if (data.documents && data.documents.length) {
          item.document = data.documents[0];
        } else {
          item.error = (data.errors && data.errors[0] && data.errors[0].error) || "Upload failed.";
        }
        render();
      };
      xhr.onerror = () => { item.uploading = false; item.error = "Network error."; render(); };
      xhr.send(formData);
    });
  }

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => { e.preventDefault(); dropzone.classList.remove("dragover"); addFiles(e.dataTransfer.files); });
  fileInput.addEventListener("change", () => { addFiles(fileInput.files); fileInput.value = ""; });

  mergeBtn.addEventListener("click", async () => {
    mergeBtn.disabled = true;
    try {
      const result = await D.apiFetch("/api/documents/merge", {
        method: "POST",
        body: {
          inputs: items.filter((i) => i.document).map((i) => ({ document_id: i.document.id, page_ranges: i.pageRanges || null })),
          output_name: outputName.value || null,
        },
      });
      addJobCard(result.job);
      items = [];
      render();
      D.toast("Merge started.", { type: "success" });
    } catch (e) {
      D.toast(e.message, { type: "error" });
    }
    render();
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
    let actionsHtml = "";
    if (job.status === "completed" && outputs && outputs.length) {
      const output = outputs.find((o) => o.output_type === "pdf") || outputs[0];
      actionsHtml = `<a class="btn small" href="/api/document-jobs/${job.id}/download/${output.id}">${D.icon("download")} Download ${D.escapeHtml(output.filename)}</a>`;
    }
    if (job.status === "failed") {
      actionsHtml = `<button class="btn small retry-btn">${D.icon("retry")} Retry</button>`;
    }
    card.innerHTML = `
      <div class="flex between center">
        <div class="flex center gap-8">${D.statusBadge(job.status)}<strong>Merge PDFs</strong></div>
        <div>${actionsHtml}</div>
      </div>
      ${job.status === "processing" || job.status === "queued" ? `
        <div class="progress-track" style="margin-top:10px;"><div class="progress-fill" style="width:${pct}%"></div></div>
        <div class="muted" style="font-size:0.78rem;margin-top:6px;">${D.escapeHtml(job.stage || "Waiting...")}</div>
      ` : ""}
      ${job.status === "failed" ? `<div class="text-err" style="font-size:0.86rem;margin-top:8px;">${D.escapeHtml(job.error_message || "Merge failed.")}</div>` : ""}
      ${job.status === "completed" && job.result_summary ? `<div style="font-size:0.86rem;margin-top:8px;">Merged ${job.result_summary.source_count} file(s) into ${job.result_summary.page_count} page(s).</div>` : ""}
    `;
    const retryBtn = card.querySelector(".retry-btn");
    if (retryBtn) retryBtn.addEventListener("click", async () => {
      try {
        const res = await D.apiFetch(`/api/document-jobs/${job.id}/retry`, { method: "POST" });
        renderCard(card, res.job);
      } catch (e) { D.toast(e.message, { type: "error" }); }
    });
  }

  render();
})();
