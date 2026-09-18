(function () {
  "use strict";
  const D = window.Docs;

  const OPERATION_LABEL = {
    pdf_to_markdown: "PDF &rarr; Markdown", merge: "Merge PDF", split: "Split PDF",
    youtube_transcript: "YouTube Transcript",
  };
  const STATUS_ICON = { completed: "check", failed: "x", processing: "jobs", queued: "jobs", cancelled: "x" };

  function renderStats(stats) {
    const grid = document.getElementById("stat-grid");
    const jobsProcessed = (stats.conversions || 0) + (stats.merges || 0) + (stats.splits || 0) + (stats.transcripts || 0);
    const tiles = [
      { value: stats.documents_total, label: "Documents" },
      { value: stats.transcripts, label: "Transcripts" },
      { value: jobsProcessed, label: "Jobs processed" },
      { value: D.formatBytes(stats.storage_bytes), label: "Storage used" },
    ];
    grid.innerHTML = tiles.map((t) => `
      <div class="stat-tile">
        <div class="value">${t.value}</div>
        <div class="label">${t.label}</div>
      </div>
    `).join("");

    if (stats.failed > 0) {
      const extra = D.el("div", "flex gap-12 wrap", []);
      extra.style.margin = "-10px 0 24px";
      extra.appendChild(D.el("span", "muted", [`${stats.failed} job(s) failed - `]));
      const link = document.createElement("a");
      link.href = "/documents/jobs?status=failed";
      link.textContent = "review them";
      link.style.color = "var(--err)";
      extra.appendChild(link);
      grid.after(extra);
    }
  }

  function renderActivity(jobs) {
    const container = document.getElementById("recent-activity");
    if (!jobs.length) {
      container.innerHTML = `<p class="muted" style="font-size:0.86rem;">Nothing processed yet - start with one of the tasks above.</p>`;
      return;
    }
    container.innerHTML = jobs.map((job) => {
      const isActive = job.status === "queued" || job.status === "processing";
      const statusText = isActive ? `Processing &middot; ${Math.round((job.progress || 0) * 100)}%` : `${job.status[0].toUpperCase()}${job.status.slice(1)} &middot; ${D.timeAgo(job.completed_at || job.created_at)}`;
      return `
        <div class="flex center gap-12" style="padding:10px 0;border-bottom:1px solid var(--border);">
          <span style="color:${job.status === 'completed' ? 'var(--ok)' : job.status === 'failed' ? 'var(--err)' : 'var(--muted)'};">${D.icon(STATUS_ICON[job.status] || "jobs")}</span>
          <div style="flex:1;min-width:0;">
            <div class="ellipsis" style="font-size:0.88rem;font-weight:500;">${OPERATION_LABEL[job.operation] || job.operation}</div>
            <div class="muted" style="font-size:0.78rem;">${statusText}</div>
          </div>
          <a class="btn ghost small" href="/documents/jobs?open=${job.id}">View</a>
        </div>`;
    }).join("");
    D.hydrateIcons(container);
  }

  function renderRecent(documents) {
    const container = document.getElementById("recent-documents");
    if (!documents.length) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="glyph" data-icon="files"></div>
          <h3>No documents yet</h3>
          <p>Upload a PDF or paste a YouTube URL to create your first document.</p>
          <div class="flex gap-8" style="justify-content:center;">
            <a class="btn primary" href="/documents/pdf-to-markdown">${D.icon("upload")} Upload PDF</a>
            <a class="btn" href="/documents/youtube-transcript">${D.icon("youtube")} YouTube Transcript</a>
          </div>
        </div>`;
      D.hydrateIcons(container);
      return;
    }
    container.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Name</th><th>Size</th><th>Status</th><th>Added</th></tr></thead>
        <tbody>
          ${documents.map((d) => `
            <tr onclick="window.location.href='/documents/files/${d.id}'" style="cursor:pointer;">
              <td class="cell-name">${D.icon(d.mime_type === "application/pdf" ? "files" : d.source === "youtube" ? "youtube" : "markdown")} <span class="ellipsis">${D.escapeHtml(d.original_name)}</span></td>
              <td class="cell-muted">${D.formatBytes(d.file_size)}</td>
              <td>${D.statusBadge(d.status)}</td>
              <td class="cell-muted">${D.timeAgo(d.created_at)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>`;
  }

  D.apiFetch("/api/documents-overview").then((stats) => {
    renderStats(stats);
    renderActivity(stats.recent_jobs || []);
    renderRecent(stats.recent_documents || []);
  }).catch((err) => {
    document.getElementById("stat-grid").innerHTML = `<div class="muted">${D.escapeHtml(err.message)}</div>`;
  });
})();
