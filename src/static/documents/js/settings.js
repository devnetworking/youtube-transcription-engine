(function () {
  "use strict";
  const D = window.Docs;
  const container = document.getElementById("settings-content");

  const SECTIONS = [
    {
      title: "Processing",
      rows: [
        ["max_concurrent_jobs", "Maximum concurrent jobs"],
        ["job_timeout_seconds", "Worker timeout (seconds)"],
        ["temp_file_retention_hours", "Temporary file retention (hours)"],
        ["output_retention_days", "Output file retention (days)"],
      ],
    },
    {
      title: "PDF -> Markdown",
      rows: [
        ["default_ocr_mode", "Default OCR behavior"],
        ["default_extract_images", "Extract images by default"],
        ["default_detect_tables", "Table detection by default"],
        ["ocr_language", "OCR language"],
      ],
    },
    {
      title: "Storage",
      rows: [
        ["data_dir", "Storage directory"],
        ["max_files_per_merge", "Maximum files per merge"],
      ],
    },
    {
      title: "Security",
      rows: [
        ["allowed_upload_extensions", "Allowed file types"],
        ["max_upload_size_mb", "Maximum upload size (MB)"],
        ["max_pages_per_document", "Maximum pages per document"],
      ],
    },
  ];

  function formatValue(v) {
    if (Array.isArray(v)) return v.join(", ");
    if (typeof v === "boolean") return v ? "Enabled" : "Disabled";
    return String(v);
  }

  D.apiFetch("/api/documents-settings").then((settings) => {
    container.innerHTML = SECTIONS.map((section) => `
      <div class="panel" style="margin-bottom:16px;">
        <h2 style="margin:0 0 14px;font-size:0.95rem;">${section.title}</h2>
        <table class="data-table">
          <tbody>
            ${section.rows.map(([key, label]) => `
              <tr><td class="cell-muted" style="width:260px;">${label}</td><td>${D.escapeHtml(formatValue(settings[key]))}</td></tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `).join("");
  }).catch((e) => {
    container.innerHTML = `<div class="text-err">${D.escapeHtml(e.message)}</div>`;
  });
})();
