(function () {
  "use strict";
  const D = window.Docs;

  const table = document.getElementById("history-table");
  const searchInput = document.getElementById("search-input");
  const filterOperation = document.getElementById("filter-operation");
  const filterStatus = document.getElementById("filter-status");

  const OPERATION_LABEL = {
    pdf_to_markdown: "Convert &rarr; Markdown", merge: "Merge", split: "Split",
    youtube_transcript: "YouTube Transcript",
  };
  let documentNames = {};

  function durationOf(job) {
    if (!job.started_at || !job.completed_at) return "-";
    return D.formatDuration((new Date(job.completed_at) - new Date(job.started_at)) / 1000);
  }

  function fileLabel(job) {
    const id = (job.input_document_ids || [])[0];
    return documentNames[id] || (job.operation === "merge" ? `${job.input_document_ids.length} file(s)` : "-");
  }

  async function load() {
    const [jobsData, docsData] = await Promise.all([
      D.apiFetch("/api/document-jobs?" + new URLSearchParams({
        status: filterStatus.value, operation: filterOperation.value, limit: "200",
      })),
      D.apiFetch("/api/documents?limit=200"),
    ]).catch((e) => { table.innerHTML = `<div class="text-err">${D.escapeHtml(e.message)}</div>`; return [null, null]; });
    if (!jobsData) return;

    documentNames = {};
    (docsData.documents || []).forEach((d) => { documentNames[d.id] = d.original_name; });

    let jobs = jobsData.jobs.filter((j) => ["completed", "failed", "cancelled"].includes(j.status));
    const search = searchInput.value.trim().toLowerCase();
    if (search) jobs = jobs.filter((j) => fileLabel(j).toLowerCase().includes(search));

    render(jobs);
  }

  function render(jobs) {
    if (!jobs.length) {
      table.innerHTML = `
        <div class="empty-state">
          <div class="glyph" data-icon="history"></div>
          <h3>No history yet</h3>
          <p>Completed conversions, merges and splits will be recorded here.</p>
        </div>`;
      D.hydrateIcons(table);
      return;
    }
    table.innerHTML = `
      <table class="data-table">
        <thead><tr><th>File</th><th>Operation</th><th>Date</th><th>Status</th><th>Duration</th><th></th></tr></thead>
        <tbody>
          ${jobs.map((j) => `
            <tr>
              <td class="ellipsis">${D.escapeHtml(fileLabel(j))}</td>
              <td>${OPERATION_LABEL[j.operation] || j.operation}</td>
              <td class="cell-muted">${D.formatDate(j.completed_at || j.created_at)}</td>
              <td>${D.statusBadge(j.status)}</td>
              <td class="cell-muted">${durationOf(j)}</td>
              <td class="flex gap-8" data-id="${j.id}"></td>
            </tr>
          `).join("")}
        </tbody>
      </table>`;

    jobs.forEach((j) => {
      const cell = table.querySelector(`td[data-id="${j.id}"]`);
      const view = D.el("a", "btn ghost small", ["View"]);
      view.href = `/documents/jobs?open=${j.id}`;
      cell.appendChild(view);
      if (j.status === "completed") {
        const dl = D.el("button", "icon-btn", []);
        dl.innerHTML = D.icon("download");
        dl.title = "Download";
        dl.addEventListener("click", async () => {
          const data = await D.apiFetch(`/api/document-jobs/${j.id}`);
          const target = data.outputs.find((o) => o.output_type === "zip") || data.outputs[0];
          if (target) window.location.href = `/api/document-jobs/${j.id}/download/${target.id}`;
        });
        cell.appendChild(dl);
      }
      const repeatBtn = D.el("button", "icon-btn", []);
      repeatBtn.innerHTML = D.icon("retry");
      repeatBtn.title = "Run again";
      repeatBtn.addEventListener("click", async () => {
        try { await D.apiFetch(`/api/document-jobs/${j.id}/repeat`, { method: "POST" }); D.toast("Started a new job.", { type: "success" }); load(); }
        catch (e) { D.toast(e.message, { type: "error" }); }
      });
      cell.appendChild(repeatBtn);
      const delBtn = D.el("button", "icon-btn", []);
      delBtn.innerHTML = D.icon("trash");
      delBtn.title = "Delete record";
      delBtn.addEventListener("click", async () => {
        const ok = await D.confirmDialog({ title: "Delete this record?", message: "This removes the job's output files. The original document is kept.", confirmLabel: "Delete", danger: true });
        if (!ok) return;
        try { await D.apiFetch(`/api/document-jobs/${j.id}`, { method: "DELETE" }); load(); }
        catch (e) { D.toast(e.message, { type: "error" }); }
      });
      cell.appendChild(delBtn);
    });
  }

  searchInput.addEventListener("input", D.debounce(load, 300));
  filterOperation.addEventListener("change", load);
  filterStatus.addEventListener("change", load);
  load();
})();
