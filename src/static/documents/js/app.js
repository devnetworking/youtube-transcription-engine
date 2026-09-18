// Shared helpers for the Documents module. No build step, no CDN
// dependency (same convention as templates/index.html) - plain
// functions attached to a `Docs` namespace and reused by each page's
// own small script.
window.Docs = (function () {
  "use strict";

  function el(tag, className, children) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    (children || []).forEach((c) => node.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
    return node;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }

  function formatBytes(bytes) {
    if (bytes == null) return "-";
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    return (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1) + " " + units[i];
  }

  function formatDuration(seconds) {
    if (seconds == null) return "-";
    if (seconds < 60) return Math.round(seconds) + "s";
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return m + "m " + s + "s";
  }

  function formatDate(iso) {
    if (!iso) return "-";
    try {
      const d = new Date(iso);
      return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch (e) {
      return iso;
    }
  }

  function timeAgo(iso) {
    if (!iso) return "-";
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
  }

  function debounce(fn, wait) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), wait);
    };
  }

  async function apiFetch(url, options) {
    const opts = Object.assign({}, options);
    if (opts.body && !(opts.body instanceof FormData)) {
      opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
      opts.body = JSON.stringify(opts.body);
    }
    let res;
    try {
      res = await fetch(url, opts);
    } catch (e) {
      throw new Error("Could not reach the server. Check that it is still running.");
    }
    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      /* empty body */
    }
    if (!res.ok) {
      const message = (data && data.error) || `Request failed (${res.status}).`;
      const err = new Error(message);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  // ---- toasts -----------------------------------------------------------

  function toastStack() {
    let stack = document.querySelector(".toast-stack");
    if (!stack) {
      stack = el("div", "toast-stack");
      document.body.appendChild(stack);
    }
    return stack;
  }

  function toast(message, opts) {
    opts = opts || {};
    const stack = toastStack();
    const node = el("div", "toast " + (opts.type || ""));
    node.appendChild(el("span", null, [message]));
    if (opts.actionLabel && opts.actionHref) {
      const a = el("a", "action", [opts.actionLabel]);
      a.href = opts.actionHref;
      node.appendChild(a);
    }
    stack.appendChild(node);
    setTimeout(() => node.remove(), opts.duration || 5000);
    return node;
  }

  // ---- confirm dialog -----------------------------------------------------

  function confirmDialog(opts) {
    return new Promise((resolve) => {
      const overlay = el("div", "overlay");
      const modal = el("div", "modal");
      modal.appendChild(el("h3", null, [opts.title || "Are you sure?"]));
      modal.appendChild(el("p", null, [opts.message || ""]));
      const actions = el("div", "actions");
      const cancelBtn = el("button", "btn ghost", [opts.cancelLabel || "Cancel"]);
      const confirmBtn = el("button", "btn " + (opts.danger ? "danger" : "primary"), [opts.confirmLabel || "Confirm"]);
      actions.appendChild(cancelBtn);
      actions.appendChild(confirmBtn);
      modal.appendChild(actions);
      function close(result) {
        overlay.remove();
        modal.remove();
        resolve(result);
      }
      cancelBtn.addEventListener("click", () => close(false));
      overlay.addEventListener("click", () => close(false));
      confirmBtn.addEventListener("click", () => close(true));
      document.body.appendChild(overlay);
      document.body.appendChild(modal);
      confirmBtn.focus();
    });
  }

  function promptDialog(opts) {
    return new Promise((resolve) => {
      const overlay = el("div", "overlay");
      const modal = el("div", "modal");
      modal.appendChild(el("h3", null, [opts.title || "Rename"]));
      const input = document.createElement("input");
      input.type = "text";
      input.value = opts.value || "";
      input.style.marginBottom = "18px";
      modal.appendChild(input);
      const actions = el("div", "actions");
      const cancelBtn = el("button", "btn ghost", ["Cancel"]);
      const confirmBtn = el("button", "btn primary", [opts.confirmLabel || "Save"]);
      actions.appendChild(cancelBtn);
      actions.appendChild(confirmBtn);
      modal.appendChild(actions);
      function close(result) { overlay.remove(); modal.remove(); resolve(result); }
      cancelBtn.addEventListener("click", () => close(null));
      overlay.addEventListener("click", () => close(null));
      confirmBtn.addEventListener("click", () => close(input.value));
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") close(input.value); if (e.key === "Escape") close(null); });
      document.body.appendChild(overlay);
      document.body.appendChild(modal);
      input.focus();
      input.select();
    });
  }

  // ---- icons (inline SVG, one consistent stroke set) -----------------------

  const ICONS = {
    documents: '<path d="M7 3h7l4 4v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"/><path d="M14 3v4h4"/>',
    overview: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    markdown: '<path d="M4 4h16v16H4z"/><path d="M7 15V9l3 3 3-3v6"/><path d="M17 9v6M14.5 12.5 17 15l2.5-2.5"/>',
    merge: '<path d="M8 3v6l4 4 4-4V3"/><path d="M12 13v8"/>',
    split: '<path d="M12 3v8"/><path d="M8 21V15l4-4 4 4v6"/>',
    youtube: '<rect x="3" y="5" width="18" height="14" rx="4"/><path d="M10 9.5v5l5-2.5z" fill="currentColor" stroke="none"/>',
    jobs: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    files: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    history: '<circle cx="12" cy="12" r="9"/><path d="M12 8v4l2.5 2.5"/><path d="M3.5 9A9 9 0 0 1 12 3"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9c.14.41.42.76.78 1H21a2 2 0 1 1 0 4h-.09c-.41 0-.79.24-1 .61Z"/>',
    upload: '<path d="M12 16V4"/><path d="M6 10l6-6 6 6"/><path d="M4 18v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    download: '<path d="M12 4v12"/><path d="M6 12l6 6 6-6"/><path d="M4 20h16"/>',
    trash: '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
    check: '<path d="M4 12l5 5 11-11"/>',
    x: '<path d="M5 5l14 14M19 5 5 19"/>',
    dots: '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    retry: '<path d="M4 4v6h6"/><path d="M5 13a8 8 0 1 0 2.6-7.4L4 10"/>',
    play: '<path d="M6 4l14 8-14 8Z"/>',
    zip: '<path d="M4 4h16v16H4z"/><path d="M12 4v16" stroke-dasharray="2 2"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>',
    command: '<rect x="4" y="4" width="6" height="6" rx="2"/><rect x="14" y="4" width="6" height="6" rx="2"/><rect x="4" y="14" width="6" height="6" rx="2"/><rect x="14" y="14" width="6" height="6" rx="2"/>',
  };

  function icon(name, extraClass) {
    const path = ICONS[name] || ICONS.files;
    return `<svg class="icon ${extraClass || ""}" viewBox="0 0 24 24">${path}</svg>`;
  }

  // ---- status badge ---------------------------------------------------------

  const STATUS_LABEL = {
    queued: "Queued", uploading: "Uploading", processing: "Processing",
    completed: "Completed", failed: "Failed", cancelled: "Cancelled",
    ready: "Ready", deleted: "Deleted",
  };

  function statusBadge(status) {
    return `<span class="badge ${status}"><span class="dot"></span>${STATUS_LABEL[status] || status}</span>`;
  }

  // ---- sidebar / mobile nav --------------------------------------------------

  function hydrateIcons(root) {
    (root || document).querySelectorAll("[data-icon]").forEach((node) => {
      node.innerHTML = icon(node.getAttribute("data-icon"), node.getAttribute("data-icon-class") || "");
    });
  }

  function initShell() {
    hydrateIcons();
    const btn = document.querySelector(".mobile-menu-btn");
    const sidebar = document.querySelector(".sidebar");
    if (btn && sidebar) {
      btn.addEventListener("click", () => sidebar.classList.toggle("open"));
      document.addEventListener("click", (e) => {
        if (sidebar.classList.contains("open") && !sidebar.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
          sidebar.classList.remove("open");
        }
      });
    }
    initCommandBar();
  }

  // ---- command palette (Ctrl/Cmd+K) -------------------------------------------

  const COMMANDS = [
    { label: "Upload document", href: "/documents/pdf-to-markdown", icon: "upload" },
    { label: "Convert PDF to Markdown", href: "/documents/pdf-to-markdown", icon: "markdown" },
    { label: "Merge PDFs", href: "/documents/merge", icon: "merge" },
    { label: "Split PDF", href: "/documents/split", icon: "split" },
    { label: "YouTube Transcript", href: "/documents/youtube-transcript", icon: "youtube" },
    { label: "Open files", href: "/documents/files", icon: "files" },
    { label: "View jobs", href: "/documents/jobs", icon: "jobs" },
    { label: "History", href: "/documents/history", icon: "history" },
    { label: "Settings", href: "/documents/settings", icon: "settings" },
  ];

  function initCommandBar() {
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openCommandBar();
      }
      if (e.key === "Escape") closeCommandBar();
    });
  }

  function closeCommandBar() {
    const overlay = document.querySelector(".command-overlay");
    if (overlay) overlay.remove();
  }

  function openCommandBar() {
    closeCommandBar();
    const overlay = el("div", "command-overlay");
    const bar = el("div", "command-bar");
    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Type a command...";
    const list = el("ul");
    bar.appendChild(input);
    bar.appendChild(list);
    overlay.appendChild(bar);
    document.body.appendChild(overlay);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) closeCommandBar(); });

    let active = 0;
    function render(filter) {
      const items = COMMANDS.filter((c) => c.label.toLowerCase().includes((filter || "").toLowerCase()));
      list.innerHTML = "";
      items.forEach((c, i) => {
        const li = el("li", i === active ? "active" : "");
        li.innerHTML = icon(c.icon) + "<span>" + escapeHtml(c.label) + "</span>";
        li.addEventListener("click", () => { window.location.href = c.href; });
        list.appendChild(li);
      });
      return items;
    }
    let items = render("");
    input.addEventListener("input", () => { active = 0; items = render(input.value); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { active = Math.min(active + 1, items.length - 1); render(input.value); }
      if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); render(input.value); }
      if (e.key === "Enter" && items[active]) { window.location.href = items[active].href; }
    });
    input.focus();
  }

  // ---- tiny Markdown -> HTML renderer -----------------------------------------
  // Only needs to render what markdown_builder.py actually produces, not
  // arbitrary CommonMark - so this stays a couple dozen lines instead of
  // pulling in a dependency for a local, offline-first tool.

  function renderMarkdown(md) {
    const lines = (md || "").replace(/\r\n/g, "\n").split("\n");
    let html = "";
    let i = 0;
    let inList = null;
    function closeList() { if (inList) { html += `</${inList}>`; inList = null; } }
    function inline(text) {
      text = escapeHtml(text);
      text = text.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img alt="$1" src="$2">');
      text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
      text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
      return text;
    }
    while (i < lines.length) {
      const line = lines[i];
      if (/^```/.test(line)) {
        closeList();
        const code = [];
        i++;
        while (i < lines.length && !/^```/.test(lines[i])) { code.push(lines[i]); i++; }
        html += `<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`;
        i++;
        continue;
      }
      if (/^<!--\s*page\s+\d+\s*-->$/.test(line.trim())) { i++; continue; }
      const heading = line.match(/^(#{1,6})\s+(.*)$/);
      if (heading) {
        closeList();
        const level = heading[1].length;
        html += `<h${level}>${inline(heading[2])}</h${level}>`;
        i++;
        continue;
      }
      if (/^>\s?/.test(line)) {
        closeList();
        const quote = [];
        while (i < lines.length && /^>\s?/.test(lines[i])) { quote.push(lines[i].replace(/^>\s?/, "")); i++; }
        html += `<blockquote>${inline(quote.join("<br>"))}</blockquote>`;
        continue;
      }
      if (/^\|(.+)\|$/.test(line) && lines[i + 1] && /^\|[\s:-]+\|$/.test(lines[i + 1])) {
        closeList();
        const headerCells = line.slice(1, -1).split("|").map((c) => c.trim());
        html += "<table><thead><tr>" + headerCells.map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>";
        i += 2;
        while (i < lines.length && /^\|(.+)\|$/.test(lines[i])) {
          const cells = lines[i].slice(1, -1).split("|").map((c) => c.trim());
          html += "<tr>" + cells.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>";
          i++;
        }
        html += "</tbody></table>";
        continue;
      }
      const ordered = line.match(/^\d+\.\s+(.*)$/);
      const bullet = line.match(/^-\s+(.*)$/);
      if (ordered || bullet) {
        const tag = ordered ? "ol" : "ul";
        if (inList !== tag) { closeList(); html += `<${tag}>`; inList = tag; }
        html += `<li>${inline((ordered || bullet)[1])}</li>`;
        i++;
        continue;
      }
      closeList();
      if (line.trim() === "") { i++; continue; }
      html += `<p>${inline(line)}</p>`;
      i++;
    }
    closeList();
    return html;
  }

  // ---- shared Markdown viewer/editor -----------------------------------------
  // Used by both PDF -> Markdown and YouTube Transcript (section 18: one
  // editor, not two) - Preview/Raw/Edit tabs, copy/download, an optional
  // Clean/Timestamped toggle for transcripts, and a client-side "unsaved
  // changes" indicator. Edits are in-memory only: there is no per-document
  // "save" API, so this never claims to persist anything it doesn't.

  function stripTimestamps(markdown) {
    return (markdown || "")
      .split("\n")
      .filter((line) => !/^\*\*Timestamp:\*\*/.test(line.trim()))
      .map((line) => line.replace(/^\[\d{1,2}:\d{2}(?::\d{2})?\]\s*/, ""))
      .join("\n")
      .replace(/\n{3,}/g, "\n\n");
  }

  function createMarkdownViewer(mount, opts) {
    const state = {
      mode: "preview",
      clean: false,
      text: opts.markdown || "",
      dirty: false,
    };

    function effectiveText() {
      return opts.supportsClean && state.clean ? stripTimestamps(state.text) : state.text;
    }

    function render() {
      const tabs = ["preview", "raw", "edit"];
      mount.innerHTML = `
        <div class="flex between center" style="margin-bottom:10px;flex-wrap:wrap;gap:8px;">
          <div class="tabs" style="margin-bottom:0;border-bottom:none;">
            ${tabs.map((t) => `<button data-mode="${t}" class="${state.mode === t ? "active" : ""}" style="margin-right:14px;">${t[0].toUpperCase()}${t.slice(1)}</button>`).join("")}
          </div>
          <div class="flex gap-8 center">
            ${opts.supportsClean ? `<button class="btn ghost small" data-action="toggle-clean">${state.clean ? "Timestamped" : "Clean"}</button>` : ""}
            ${state.dirty ? '<span class="muted" style="font-size:0.76rem;">Unsaved changes</span>' : ""}
            <button class="icon-btn" data-action="copy" title="Copy">${icon("files")}</button>
            ${opts.downloadUrl ? `<a class="icon-btn" href="${opts.downloadUrl}" title="Download .md">${icon("download")}</a>` : ""}
          </div>
        </div>
        <div class="panel" style="padding:0;min-height:320px;max-height:560px;overflow:auto;">
          ${state.mode === "preview" ? `<div class="markdown-body" style="padding:18px;">${renderMarkdown(effectiveText())}</div>` : ""}
          ${state.mode === "raw" ? `<pre style="margin:0;padding:18px;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:0.82rem;">${escapeHtml(effectiveText())}</pre>` : ""}
          ${state.mode === "edit" ? `<textarea class="markdown-editor" style="padding:18px;min-height:320px;box-sizing:border-box;">${escapeHtml(state.text)}</textarea>` : ""}
        </div>
      `;
      mount.querySelectorAll("[data-mode]").forEach((btn) => {
        btn.addEventListener("click", () => { state.mode = btn.dataset.mode; render(); });
      });
      const cleanBtn = mount.querySelector('[data-action="toggle-clean"]');
      if (cleanBtn) cleanBtn.addEventListener("click", () => { state.clean = !state.clean; render(); });
      mount.querySelector('[data-action="copy"]').addEventListener("click", async () => {
        await navigator.clipboard.writeText(effectiveText());
        toast("Copied to clipboard.", { type: "success" });
      });
      const textarea = mount.querySelector(".markdown-editor");
      if (textarea) {
        textarea.addEventListener("input", () => {
          state.text = textarea.value;
          // Flip the flag and splice in the indicator directly instead of
          // a full re-render, which would rebuild the textarea and throw
          // away the cursor position on every keystroke.
          if (!state.dirty) {
            state.dirty = true;
            const actionBar = mount.querySelector(".flex.gap-8.center");
            const indicator = document.createElement("span");
            indicator.className = "muted";
            indicator.style.fontSize = "0.76rem";
            indicator.textContent = "Unsaved changes";
            actionBar.insertBefore(indicator, actionBar.firstChild);
          }
        });
      }
    }

    render();
    return { getText: () => state.text };
  }

  return {
    el, escapeHtml, formatBytes, formatDuration, formatDate, timeAgo, debounce,
    apiFetch, toast, confirmDialog, promptDialog, icon, hydrateIcons, statusBadge, initShell, renderMarkdown,
    createMarkdownViewer,
  };
})();
