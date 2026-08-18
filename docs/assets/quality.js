(function () {
  "use strict";

  if (!window.NV) window.NV = {};

  const T = {
    title: "Chất lượng đường ống — tuần",
    // Không phải "dựng lúc mấy giờ": mốc này neo vào ngày CUỐI của tuần, cố ý, để payload
    // không đổi băm mỗi lần dựng lại. Gọi nó là ngày dựng thì tuần đang chạy sẽ khoe một
    // ngày còn ở tương lai.
    generated: "Số liệu tính tới hết ngày",
    missing: "Không có dữ liệu từ",
    missingReason: "vì CSDL của hệ này không đọc được lúc dựng.",
    emptyTable: "Không có mục nào.",
    systems: {
      "news-hunter": "News Hunter",
      "x-pulse": "X Pulse",
      youtube: "YouTube Summarizer",
      translation: "Máy đo chất lượng dịch"
    }
  };

  const KNOWN_SYSTEMS = ["news-hunter", "x-pulse", "youtube", "translation"];

  function make(tag, cls, parent) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (parent) parent.appendChild(el);
    return el;
  }

  function text(el, val) {
    el.textContent = val == null ? "" : String(val);
  }

  function formatDate(date) {
    if (!date) return "";
    const parts = String(date).slice(0, 10).split("-");
    if (parts.length !== 3) return String(date);
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }

  function formatRange(start, end) {
    const startParts = String(start || "").slice(0, 10).split("-");
    const endParts = String(end || "").slice(0, 10).split("-");
    if (startParts.length !== 3 || endParts.length !== 3) {
      return `${formatDate(start)} – ${formatDate(end)}`;
    }
    return `${startParts[2]}/${startParts[1]} – ${endParts[2]}/${endParts[1]}/${endParts[0]}`;
  }

  function systemId(key, index) {
    return `quality-system-${String(key || "unknown")}-${index}`;
  }

  function renderHeader(parent, payload) {
    const header = make("header", "quality__header", parent);
    const title = make("h1", "quality__title", header);
    text(title, `${T.title} ${payload.week || ""}`.trim());

    const range = make("p", "quality__range", header);
    text(range, formatRange(payload.start, payload.end));

    if (payload.generated_at) {
      const generated = make("p", "quality__generated", header);
      text(generated, `${T.generated} ${formatDate(payload.generated_at)}`);
    }
  }

  function renderQuickNav(parent, systems) {
    if (!systems.length) return;

    const nav = make("nav", "quality__nav", parent);
    nav.setAttribute("aria-label", "Đi tới hệ thống");

    for (let index = 0; index < systems.length; index += 1) {
      const system = systems[index] || {};
      const button = make("button", "quality__nav-button", nav);
      button.type = "button";
      text(button, system.label || T.systems[system.key] || system.key || "Hệ thống");
      button.addEventListener("click", () => {
        const target = document.getElementById(systemId(system.key, index));
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }

  function renderStats(parent, stats) {
    if (!stats.length) return;

    const grid = make("div", "quality__stats", parent);
    for (const stat of stats) {
      const item = make("article", "quality__stat", grid);
      if (stat.tone === "ok" || stat.tone === "warn" || stat.tone === "bad") {
        item.classList.add(`quality__stat--${stat.tone}`);
      }

      const valueRow = make("div", "quality__stat-value-row", item);
      const value = make("strong", "quality__stat-value", valueRow);
      text(value, stat.value);

      if (stat.sub) {
        const sub = make("span", "quality__stat-sub", valueRow);
        text(sub, stat.sub);
      }

      const label = make("span", "quality__stat-label", item);
      text(label, stat.label);
    }
  }

  function renderTable(parent, table) {
    const section = make("section", "quality__table-section", parent);
    const rows = Array.isArray(table.rows) ? table.rows : [];

    if (!rows.length) {
      const title = make("h3", "quality__table-title", section);
      text(title, table.title);
      const empty = make("p", "quality__empty", section);
      text(empty, T.emptyTable);
      return;
    }

    const wrap = make("div", "quality__table-wrap", section);
    const element = make("table", "quality__table", wrap);
    const caption = make("caption", "", element);
    text(caption, table.title);

    const head = make("thead", "", element);
    const headRow = make("tr", "", head);
    for (const col of table.cols || []) {
      const cell = make("th", "", headRow);
      cell.scope = "col";
      text(cell, col);
    }

    const body = make("tbody", "", element);
    for (const row of rows) {
      const tr = make("tr", "", body);
      for (const value of row || []) {
        const cell = make("td", "", tr);
        text(cell, value);
      }
    }
  }

  function renderSystem(parent, system, index) {
    const section = make("section", "quality__system", parent);
    section.id = systemId(system.key, index);

    const header = make("header", "quality__system-header", section);
    const title = make("h2", "quality__system-title", header);
    text(title, system.label || T.systems[system.key] || system.key || "Hệ thống");

    if (system.note) {
      const note = make("p", "quality__system-note", header);
      text(note, system.note);
    }

    renderStats(section, Array.isArray(system.stats) ? system.stats : []);
    for (const table of Array.isArray(system.tables) ? system.tables : []) {
      renderTable(section, table || {});
    }
  }

  function renderMissing(parent, systems) {
    if (systems.length >= KNOWN_SYSTEMS.length) return;

    const received = {};
    for (const system of systems) {
      if (system && system.key) received[system.key] = true;
    }

    const missing = [];
    for (const key of KNOWN_SYSTEMS) {
      if (!received[key]) missing.push(T.systems[key]);
    }
    if (!missing.length) return;

    const note = make("p", "quality__missing", parent);
    text(note, `${T.missing} ${missing.join(", ")} ${T.missingReason}`);
  }

  function render(app, payload) {
    const data = payload || {};
    const systems = Array.isArray(data.systems) ? data.systems : [];

    renderHeader(app, data);
    renderQuickNav(app, systems);

    const content = make("div", "quality__systems", app);
    for (let index = 0; index < systems.length; index += 1) {
      renderSystem(content, systems[index] || {}, index);
    }

    renderMissing(app, systems);
  }

  window.NV.quality = { render: render };
}());
