/* Analyst reports: normal articles remain full cards; RSS-only rows stay compact. */
(function () {
  "use strict";

  if (!window.NV) window.NV = {};

  const T = {
    section: "Báo cáo phân tích",
    empty: "Chưa có báo cáo phân tích nào.",
    full: "Đọc bản đầy đủ →",
    countOne: "1 báo cáo",
    countMany: " báo cáo"
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

  function formatDate(value) {
    if (typeof value !== "string" || value.length < 10) return "";
    return value.slice(8, 10) + "/" + value.slice(5, 7) + "/" + value.slice(0, 4);
  }

  function teaserCard(item) {
    const report = item && typeof item === "object" ? item : {};
    const li = make("li", "report-teaser");
    const badge = make("span", "badge badge--deep", li);
    text(badge, T.section);
    const title = make("h3", "report-teaser__title", li);
    const link = make("a", "report-teaser__link", title);
    link.href = report.u || "#";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    text(link, report.t || "");
    const meta = make("p", "report-teaser__meta", li);
    text(meta, [report.s, formatDate(report.pi || report.p || report.d)].filter(Boolean).join(" · "));
    if (report.sum) {
      const snippet = make("p", "report-teaser__snippet", li);
      text(snippet, report.sum);
    }
    const cta = make("a", "report-teaser__cta", li);
    cta.href = report.u || "#";
    cta.target = "_blank";
    cta.rel = "noopener noreferrer";
    text(cta, T.full);
    return li;
  }

  function reportCard(item) {
    if (item && item.te) return teaserCard(item);
    if (window.NV.app && typeof window.NV.app.articleCard === "function") {
      return window.NV.app.articleCard(item || {});
    }
    return teaserCard(item);
  }

  function cardList(items, base, cls) {
    const list = Array.isArray(items) ? items : [];
    const ul = make("ul", "cards reports__list" + (cls ? " " + cls : ""));
    for (let index = 0; index < list.length; index += 1) {
      ul.appendChild(reportCard(list[index]));
    }
    return ul;
  }

  function daySection(items, base) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) return null;
    const section = make("section", "reports");
    const title = make("h2", "reports__title", section);
    text(title, T.section);
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
    text(count, items.length === 1 ? T.countOne : items.length + T.countMany);
    if (!items.length) {
      const empty = make("p", "reports-index__empty", app);
      text(empty, T.empty);
      return;
    }
    const wrap = make("div", "cards-wrap reports-index__wrap", app);
    wrap.appendChild(cardList(items, (config && config.base) || "../", "reports-index__list"));
  }

  window.NV.reports = {
    daySection: daySection,
    renderIndex: renderIndex,
    teaserCard: teaserCard,
    cardList: cardList
  };
})();
