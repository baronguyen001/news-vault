/* Analyst reports use one compact card regardless of whether a source gave us a full body. */
(function () {
  "use strict";

  if (!window.NV) window.NV = {};

  const T = {
    section: "Báo cáo phân tích",
    empty: "Chưa có báo cáo phân tích nào.",
    full: "Đọc bản đầy đủ →",
    countOne: "1 báo cáo",
    countMany: " báo cáo",
    search: "Tìm theo tiêu đề hoặc nguồn…",
    allSources: "Tất cả nguồn",
    archiveCount: (n) => n === 1 ? "1 báo cáo toàn kho" : n + " báo cáo toàn kho",
    dayCount: (n, day) => n + " báo cáo ngày " + day,
    archiveLink: "Xem toàn kho",
    sortReceivedNewest: "Mới vào kho",
    sortReceivedOldest: "Cũ vào kho",
    sortPublishedNewest: "Xuất bản mới nhất",
    sortPublishedOldest: "Xuất bản cũ nhất",
    sortSource: "Theo nguồn A–Z",
    noResults: "Không có báo cáo phù hợp với bộ lọc.",
    clear: "Xóa bộ lọc"
  };

  function make(tag, cls, parent) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (parent) parent.appendChild(el);
    return el;
  }

  function text(el, val) {
    el.textContent = val == null ? "" : String(val);
  }

  function isNonEmptyString(v) {
    return typeof v === "string" && v !== "";
  }

  /* Same diacritic-insensitive fold substack.js/video-library.js use, so "kinh te" finds
   * "kinh tế". */
  function folded(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/đ/g, "d");
  }

  function formatDate(value) {
    if (typeof value !== "string" || value.length < 10) return "";
    return value.slice(8, 10) + "/" + value.slice(5, 7) + "/" + value.slice(0, 4);
  }

  function hasAnalysis(report) {
    return !!(report && report.an && typeof report.an === "object" && Object.keys(report.an).length);
  }

  function reportCard(item) {
    const report = item && typeof item === "object" ? item : {};
    const li = make("li", "card card--report report-card");
    const header = make("div", "card__head", li);
    const badge = make("span", "badge badge--deep", header);
    text(badge, T.section);
    if (hasAnalysis(report)) {
      const analysis = make("span", "badge badge--analysis", header);
      text(analysis, "Có phân tích sâu");
    }
    const lead = make("div", "card__lead", li);
    if (window.NV.videos && typeof window.NV.videos.thumb === "function") {
      window.NV.videos.thumb(lead, report.img, report.t || "");
    }
    const content = make("div", "report-card__content", lead);
    const title = make("h3", "card__title report-card__title", content);
    const link = make("a", "report-card__link", title);
    link.href = report.u || "#";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    text(link, report.t || "");
    const meta = make("p", "card__meta report-card__meta", content);
    text(meta, [report.s, formatDate(report.pi || report.fi || report.d)].filter(Boolean).join(" · "));
    if (report.sum) {
      const preview = make("p", "report-card__summary", content);
      text(preview, report.sum);
    }
    const detail = make("div", "card__body report-card__detail", li);
    if (report.sum) {
      const fullSummary = make("p", "report-card__full-summary", detail);
      text(fullSummary, report.sum);
    }
    if (hasAnalysis(report) && window.NV.app && typeof window.NV.app.renderAnalysisBlocks === "function") {
      detail.appendChild(window.NV.app.renderAnalysisBlocks(report, null));
    }
    detail.hidden = true;
    const foot = make("div", "card__foot", li);
    if (detail.childNodes.length) {
      const more = make("button", "card__more", foot);
      more.type = "button";
      more.addEventListener("click", () => {
        if (!window.NV.modal) return;
        detail.hidden = false;
        window.NV.modal.open({
          title: report.t || "",
          node: detail,
          onClose: () => { detail.hidden = true; }
        });
      });
      text(more, "Xem thêm");
    }
    const cta = make("a", "report-card__cta", foot);
    cta.href = report.u || "#";
    cta.target = "_blank";
    cta.rel = "noopener noreferrer";
    text(cta, T.full);
    return li;
  }

  function cardList(items, base, cls) {
    const list = Array.isArray(items) ? items : [];
    const ul = make("ul", "cards reports__list" + (cls ? " " + cls : ""));
    for (let index = 0; index < list.length; index += 1) {
      ul.appendChild(reportCard(list[index]));
    }
    return ul;
  }

  function daySection(items, base, day) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) return null;
    const section = make("section", "reports");
    const title = make("h2", "reports__title", section);
    text(title, T.section);
    const context = make("p", "reports__context", section);
    text(context, T.dayCount(list.length, formatDate(day || list[0].d || "")) + " · ");
    const archive = make("a", "reports__archive-link", context);
    archive.href = (base || "../../") + "r/";
    text(archive, T.archiveLink);
    section.appendChild(cardList(list, base, "reports__day-list"));
    return section;
  }

  function renderIndex(app, payload, config) {
    const data = payload && typeof payload === "object" ? payload : {};
    const items = Array.isArray(data.items) ? data.items : [];

    const header = make("header", "reports-index__head", app);
    const title = make("h1", "reports-index__title", header);
    text(title, T.section);
    const count = make("p", "reports-index__count", header);
    text(count, T.archiveCount(items.length));

    if (!items.length) {
      const empty = make("p", "reports-index__empty", app);
      text(empty, T.empty);
      return;
    }

    const state = { query: "", source: "", sort: "received-newest" };

    const controls = make("section", "reports-index__controls", app);
    controls.setAttribute("aria-label", "Lọc báo cáo phân tích");
    const input = make("input", "reports-index__search", controls);
    input.type = "search";
    input.placeholder = T.search;
    input.setAttribute("aria-label", T.search);

    const sourceSelect = make("select", "reports-index__select", controls);
    sourceSelect.setAttribute("aria-label", T.allSources);
    const allOption = make("option", "", sourceSelect);
    allOption.value = "";
    text(allOption, T.allSources);
    const sources = Array.from(new Set(items.map((item) => item && item.s).filter(isNonEmptyString)))
      .sort((a, b) => a.localeCompare(b, "vi"));
    for (let i = 0; i < sources.length; i++) {
      const option = make("option", "", sourceSelect);
      option.value = sources[i];
      text(option, sources[i]);
    }

    const sortSelect = make("select", "reports-index__select", controls);
    sortSelect.setAttribute("aria-label", "Sắp xếp");
    [["received-newest", T.sortReceivedNewest], ["received-oldest", T.sortReceivedOldest], ["published-newest", T.sortPublishedNewest], ["published-oldest", T.sortPublishedOldest], ["source", T.sortSource]].forEach(
      ([value, label]) => {
        const option = make("option", "", sortSelect);
        option.value = value;
        text(option, label);
      }
    );

    const clear = make("button", "reports-index__clear", controls);
    clear.type = "button";
    text(clear, T.clear);

    const wrap = make("div", "cards-wrap reports-index__wrap", app);
    const shownCount = make("p", "reports-index__shown", wrap);
    shownCount.setAttribute("aria-live", "polite");
    const list = make("ul", "cards reports__list reports-index__list", wrap);
    const empty = make("p", "reports-index__noresults", wrap);
    text(empty, T.noResults);
    empty.hidden = true;

    function time(item, key) {
      const value = Date.parse(String(item && item[key] || ""));
      return Number.isFinite(value) ? value : null;
    }

    function compareTime(a, b, key, direction) {
      const aTime = time(a, key);
      const bTime = time(b, key);
      if (aTime !== null && bTime !== null && aTime !== bTime) return direction * (aTime - bTime);
      if (aTime !== null && bTime === null) return -1;
      if (aTime === null && bTime !== null) return 1;
      return Number(a.i || 0) - Number(b.i || 0);
    }

    function matches(item) {
      if (state.source && item.s !== state.source) return false;
      if (!state.query) return true;
      const haystack = folded([item.t, item.to, item.s, item.sum].filter(isNonEmptyString).join(" "));
      return haystack.indexOf(folded(state.query)) !== -1;
    }

    function sorted(list) {
      return list.sort((a, b) => {
        if (state.sort === "source") {
          return String(a.s || "").localeCompare(String(b.s || ""), "vi") ||
            compareTime(a, b, "fi", -1);
        }
        if (state.sort === "received-oldest") return compareTime(a, b, "fi", 1);
        if (state.sort === "published-newest") return compareTime(a, b, "pi", -1) || compareTime(a, b, "fi", -1);
        if (state.sort === "published-oldest") return compareTime(a, b, "pi", 1) || compareTime(a, b, "fi", 1);
        return compareTime(a, b, "fi", -1);
      });
    }

    function paint() {
      const shown = sorted(items.filter(matches));
      text(shownCount, shown.length === 1 ? T.countOne : shown.length + T.countMany);
      text(list, "");
      for (let i = 0; i < shown.length; i++) {
        list.appendChild(reportCard(shown[i]));
      }
      empty.hidden = shown.length !== 0;
    }

    input.addEventListener("input", () => {
      state.query = input.value.trim();
      paint();
    });
    sourceSelect.addEventListener("change", () => {
      state.source = sourceSelect.value;
      paint();
    });
    sortSelect.addEventListener("change", () => {
      state.sort = sortSelect.value;
      paint();
    });
    clear.addEventListener("click", () => {
      state.query = "";
      state.source = "";
      state.sort = "received-newest";
      input.value = "";
      sourceSelect.value = "";
      sortSelect.value = "received-newest";
      paint();
    });

    paint();
  }

  window.NV.reports = {
    daySection: daySection,
    renderIndex: renderIndex,
    reportCard: reportCard,
    cardList: cardList
  };
})();
