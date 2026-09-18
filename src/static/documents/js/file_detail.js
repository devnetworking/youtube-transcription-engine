(function () {
  "use strict";
  const D = window.Docs;
  const documentId = window.__DOCUMENT_ID__;

  const OPERATION_LABEL = {
    pdf_to_markdown: "Convert &rarr; Markdown", merge: "Merge", split: "Split",
    youtube_transcript: "YouTube Transcript",
  };

  document.querySelectorAll(".tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
      btn.classList.add("active");
      document.getElementById("tab-" + btn.dataset.tab).classList.remove("hidden");
    });
  });

  async function load() {
    let data;
    try {
      data = await D.apiFetch(`/api/documents/${documentId}`);
    } catch (e) {
      document.getElementById("doc-title").textContent = "Not found";
      document.getElementById("doc-subtitle").textContent = e.message;
      return;
    }
    const doc = data.document;
    document.title = doc.original_name;
    document.getElementById("crumb-name").textContent = doc.original_name;
    document.getElementById("doc-title").textContent = doc.original_name;
    const isPdf = doc.mime_type === "application/pdf";
    document.getElementById("doc-subtitle").innerHTML = isPdf
      ? `${D.formatBytes(doc.file_size)} &middot; ${doc.page_count != null ? doc.page_count + " pages" : "-"} &middot; ${D.statusBadge(doc.status)}`
      : `${D.formatBytes(doc.file_size)} &middot; YouTube Transcript &middot; ${D.statusBadge(doc.status)}`;

    const previewPane = document.getElementById("tab-preview");
    if (isPdf) {
      previewPane.innerHTML = `<iframe class="pdf-frame" style="width:100%;height:640px;border:1px solid var(--border);border-radius:10px;" id="pdf-iframe"></iframe>`;
      document.getElementById("pdf-iframe").src = `/api/documents/${documentId}/download`;
    } else {
      previewPane.innerHTML = `<div class="panel markdown-body" id="md-preview" style="max-height:640px;overflow:auto;"></div>`;
      fetch(`/api/documents/${documentId}/download`).then((r) => r.text()).then((text) => {
        document.getElementById("md-preview").innerHTML = D.renderMarkdown(text);
      }).catch(() => {});
    }

    const actions = document.getElementById("doc-actions");
    actions.innerHTML = `
      ${isPdf ? `<a class="btn primary" href="/documents/pdf-to-markdown?document_id=${documentId}">Convert</a>
      <a class="btn" href="/documents/split?document_id=${documentId}">Split</a>` : ""}
      <a class="btn ghost" href="/api/documents/${documentId}/download" ${isPdf ? "" : "download"}>${D.icon("download")} Download</a>
      <button class="btn ghost" id="delete-btn">${D.icon("trash")} Delete</button>
    `;
    document.getElementById("delete-btn").addEventListener("click", async () => {
      const ok = await D.confirmDialog({
        title: "Delete document?",
        message: "This will permanently remove the original document and its generated outputs.",
        confirmLabel: "Delete", danger: true,
      });
      if (!ok) return;
      try {
        await D.apiFetch(`/api/documents/${documentId}`, { method: "DELETE" });
        window.location.href = "/documents/files";
      } catch (e) { D.toast(e.message, { type: "error" }); }
    });

    document.getElementById("tab-details").innerHTML = `
      <table class="data-table">
        <tbody>
          <tr><td class="cell-muted">File name</td><td>${D.escapeHtml(doc.original_name)}</td></tr>
          <tr><td class="cell-muted">Size</td><td>${D.formatBytes(doc.file_size)}</td></tr>
          <tr><td class="cell-muted">Pages</td><td>${doc.page_count != null ? doc.page_count : "-"}</td></tr>
          <tr><td class="cell-muted">MIME type</td><td>${D.escapeHtml(doc.mime_type)}</td></tr>
          <tr><td class="cell-muted">Checksum (SHA-256)</td><td class="cell-muted" style="font-family:ui-monospace,monospace;font-size:0.78rem;">${D.escapeHtml(doc.checksum_sha256 || "-")}</td></tr>
          <tr><td class="cell-muted">Uploaded</td><td>${D.formatDate(doc.created_at)}</td></tr>
        </tbody>
      </table>`;

    const jobs = data.jobs || [];
    renderHistory(jobs);
    renderDerived(jobs);
  }

  async function renderDerived(jobs) {
    const container = document.getElementById("tab-derived");
    const completed = jobs.filter((j) => j.status === "completed");
    if (!completed.length) {
      container.innerHTML = `<p class="muted" style="font-size:0.86rem;">No conversions, merges or splits yet - derived files will appear here once a job completes.</p>`;
      return;
    }
    const results = await Promise.all(completed.map((j) => D.apiFetch(`/api/document-jobs/${j.id}`).catch(() => null)));
    container.innerHTML = results.filter(Boolean).map(({ job, outputs }) => `
      <div style="margin-bottom:16px;">
        <div class="muted" style="font-size:0.78rem;text-transform:uppercase;letter-spacing:0.03em;margin-bottom:6px;">${OPERATION_LABEL[job.operation] || job.operation} - ${D.timeAgo(job.completed_at)}</div>
        ${outputs.map((o) => `
          <a class="file-row" style="text-decoration:none;color:inherit;" href="/api/document-jobs/${job.id}/download/${o.id}">
            <div class="thumb">${D.icon(o.output_type === "zip" ? "zip" : "files")}</div>
            <div class="meta"><div class="name">${D.escapeHtml(o.filename)}</div><div class="sub">${D.formatBytes(o.file_size)}</div></div>
            <span class="icon-btn">${D.icon("download")}</span>
          </a>
        `).join("")}
      </div>
    `).join("");
    D.hydrateIcons(container);
  }

  function renderHistory(jobs) {
    const container = document.getElementById("tab-history");
    if (!jobs.length) {
      container.innerHTML = `<p class="muted" style="font-size:0.86rem;">No operations on this document yet.</p>`;
      return;
    }
    container.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Operation</th><th>Status</th><th>Date</th><th></th></tr></thead>
        <tbody>
          ${jobs.map((j) => `
            <tr>
              <td>${OPERATION_LABEL[j.operation] || j.operation}</td>
              <td>${D.statusBadge(j.status)}</td>
              <td class="cell-muted">${D.formatDate(j.created_at)}</td>
              <td><a class="btn ghost small" href="/documents/jobs?open=${j.id}">View</a></td>
            </tr>
          `).join("")}
        </tbody>
      </table>`;
  }

  load();
})();
