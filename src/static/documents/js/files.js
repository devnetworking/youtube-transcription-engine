(function () {
  "use strict";
  const D = window.Docs;

  const container = document.getElementById("files-container");
  const searchInput = document.getElementById("search-input");
  const bulkBar = document.getElementById("bulk-bar");
  const bulkCount = document.getElementById("bulk-count");
  const menuRoot = document.getElementById("menu-root");

  let view = "list";
  let documents = [];
  let selected = new Set();

  function isPdf(doc) { return doc.mime_type === "application/pdf"; }

  const TYPE_LABEL = { upload: "PDF", youtube: "YouTube Transcript", generated: "Generated", merge: "PDF", split: "PDF", conversion: "Markdown" };
  function typeBadge(doc) {
    let label = TYPE_LABEL[doc.source] || "File";
    if (doc.source === "upload" && !isPdf(doc)) label = "File";
    if (doc.mime_type === "text/markdown" && doc.source !== "youtube") label = "Markdown";
    return `<span class="badge" style="background:var(--bg);color:var(--muted);">${D.escapeHtml(label)}</span>`;
  }
  function thumbIcon(doc) {
    return isPdf(doc) ? "files" : doc.source === "youtube" ? "youtube" : "markdown";
  }

  function closeMenu() { menuRoot.innerHTML = ""; }

  function openMenu(anchor, doc) {
    closeMenu();
    const rect = anchor.getBoundingClientRect();
    const menu = D.el("div", "panel");
    menu.style.position = "fixed";
    menu.style.top = rect.bottom + 6 + "px";
    menu.style.left = Math.max(8, rect.right - 200) + "px";
    menu.style.width = "200px";
    menu.style.padding = "6px";
    menu.style.zIndex = "50";
    menu.style.boxShadow = "var(--shadow-md)";

    const items = [{ label: "Open", action: () => (window.location.href = `/documents/files/${doc.id}`) }];
    if (isPdf(doc)) {
      items.push(
        { label: "Convert to Markdown", action: () => (window.location.href = `/documents/pdf-to-markdown?document_id=${doc.id}`) },
        { label: "Merge with...", action: () => (window.location.href = `/documents/merge`) },
        { label: "Split", action: () => (window.location.href = `/documents/split?document_id=${doc.id}`) },
      );
    }
    items.push(
      { label: "Download", action: () => (window.location.href = `/api/documents/${doc.id}/download`) },
      { label: "Rename", action: () => renameDoc(doc) },
      { label: "Delete", danger: true, action: () => deleteDocs([doc.id]) },
    );
    items.forEach((item) => {
      const row = D.el("div", "nav-item transition", [item.label]);
      row.style.cursor = "pointer";
      row.style.color = item.danger ? "var(--err)" : "";
      row.addEventListener("click", () => { closeMenu(); item.action(); });
      menu.appendChild(row);
    });
    menuRoot.appendChild(menu);
    setTimeout(() => document.addEventListener("click", closeMenu, { once: true }), 0);
  }

  async function renameDoc(doc) {
    const name = await D.promptDialog({ title: "Rename document", value: doc.original_name });
    if (!name || name === doc.original_name) return;
    try {
      await D.apiFetch(`/api/documents/${doc.id}`, { method: "PATCH", body: { original_name: name } });
      D.toast("Document renamed.", { type: "success" });
      load();
    } catch (e) { D.toast(e.message, { type: "error" }); }
  }

  async function deleteDocs(ids) {
    const ok = await D.confirmDialog({
      title: ids.length > 1 ? `Delete ${ids.length} documents?` : "Delete document?",
      message: "This will permanently remove the original document and its generated outputs.",
      confirmLabel: "Delete",
      danger: true,
    });
    if (!ok) return;
    for (const id of ids) {
      try { await D.apiFetch(`/api/documents/${id}`, { method: "DELETE" }); }
      catch (e) { D.toast(e.message, { type: "error" }); }
    }
    selected.clear();
    updateBulkBar();
    load();
  }

  function toggleSelect(id, checked) {
    if (checked) selected.add(id); else selected.delete(id);
    updateBulkBar();
  }

  function updateBulkBar() {
    bulkBar.classList.toggle("hidden", selected.size === 0);
    bulkCount.textContent = `${selected.size} selected`;
  }

  document.getElementById("bulk-delete").addEventListener("click", () => deleteDocs(Array.from(selected)));
  document.getElementById("bulk-download").addEventListener("click", () => {
    Array.from(selected).forEach((id) => window.open(`/api/documents/${id}/download`, "_blank"));
  });

  function renderList() {
    if (!documents.length) return renderEmpty();
    container.innerHTML = `
      <table class="data-table">
        <thead><tr><th style="width:30px;"></th><th>Name</th><th>Type</th><th>Size</th><th>Pages</th><th>Status</th><th>Updated</th><th></th></tr></thead>
        <tbody>
          ${documents.map((d) => `
            <tr data-id="${d.id}">
              <td><input type="checkbox" class="row-check" ${selected.has(d.id) ? "checked" : ""}></td>
              <td class="cell-name" style="cursor:pointer;">${D.icon(thumbIcon(d))}<span class="ellipsis">${D.escapeHtml(d.original_name)}</span></td>
              <td>${typeBadge(d)}</td>
              <td class="cell-muted">${D.formatBytes(d.file_size)}</td>
              <td class="cell-muted">${d.page_count != null ? d.page_count : "-"}</td>
              <td>${D.statusBadge(d.status)}</td>
              <td class="cell-muted">${D.timeAgo(d.created_at)}</td>
              <td><button class="icon-btn menu-btn">${D.icon("dots")}</button></td>
            </tr>
          `).join("")}
        </tbody>
      </table>`;
    documents.forEach((d) => {
      const row = container.querySelector(`tr[data-id="${d.id}"]`);
      row.querySelector(".cell-name").addEventListener("click", () => (window.location.href = `/documents/files/${d.id}`));
      row.querySelector(".row-check").addEventListener("change", (e) => toggleSelect(d.id, e.target.checked));
      row.querySelector(".menu-btn").addEventListener("click", (e) => { e.stopPropagation(); openMenu(e.currentTarget, d); });
    });
  }

  function renderGrid() {
    if (!documents.length) return renderEmpty();
    container.innerHTML = `<div class="card-grid">
      ${documents.map((d) => `
        <div class="action-card" data-id="${d.id}" style="cursor:pointer;">
          <div class="flex between">
            <input type="checkbox" class="row-check" ${selected.has(d.id) ? "checked" : ""} onclick="event.stopPropagation()">
            <button class="icon-btn menu-btn" onclick="event.stopPropagation()">${D.icon("dots")}</button>
          </div>
          <div class="thumb" style="width:100%;height:120px;border-radius:8px;background:var(--bg);border:1px solid var(--border);overflow:hidden;display:flex;align-items:center;justify-content:center;color:var(--faint);">
            ${isPdf(d)
              ? `<img src="/api/documents/${d.id}/thumbnail/0?size=220" style="max-width:100%;max-height:100%;object-fit:contain;" loading="lazy">`
              : `<span style="width:32px;height:32px;display:inline-flex;">${D.icon(thumbIcon(d))}</span>`}
          </div>
          <h3 class="ellipsis" style="font-size:0.88rem;">${D.escapeHtml(d.original_name)}</h3>
          <p>${typeBadge(d)}</p>
          <p>${D.formatBytes(d.file_size)} &middot; ${d.page_count != null ? d.page_count + " pages" : "-"}</p>
        </div>
      `).join("")}
    </div>`;
    documents.forEach((d) => {
      const card = container.querySelector(`[data-id="${d.id}"]`);
      card.addEventListener("click", () => (window.location.href = `/documents/files/${d.id}`));
      card.querySelector(".row-check").addEventListener("change", (e) => toggleSelect(d.id, e.target.checked));
      card.querySelector(".menu-btn").addEventListener("click", (e) => { e.stopPropagation(); openMenu(e.currentTarget, d); });
    });
  }

  function renderEmpty() {
    const isSearch = !!searchInput.value.trim();
    container.innerHTML = `
      <div class="empty-state">
        <div class="glyph" data-icon="files"></div>
        <h3>${isSearch ? "No matching documents" : "No documents yet"}</h3>
        <p>${isSearch ? "Try a different search term." : "Upload a PDF to convert, merge or split your first document."}</p>
        ${isSearch ? "" : '<a class="btn primary" href="/documents/pdf-to-markdown">Upload PDF</a>'}
      </div>`;
    D.hydrateIcons(container);
  }

  async function load() {
    let data;
    try {
      data = await D.apiFetch("/api/documents?" + new URLSearchParams({ search: searchInput.value || "", limit: "100" }));
    } catch (e) {
      container.innerHTML = `<div class="text-err">${D.escapeHtml(e.message)}</div>`;
      return;
    }
    documents = data.documents;
    view === "grid" ? renderGrid() : renderList();
  }

  document.getElementById("view-list").addEventListener("click", () => { view = "list"; render_active(); load(); });
  document.getElementById("view-grid").addEventListener("click", () => { view = "grid"; render_active(); load(); });
  function render_active() {
    document.getElementById("view-list").classList.toggle("active", view === "list");
    document.getElementById("view-grid").classList.toggle("active", view === "grid");
  }
  render_active();

  searchInput.addEventListener("input", D.debounce(load, 300));
  load();
})();
