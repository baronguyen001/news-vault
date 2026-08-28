/* Analyst reports: normal articles remain full cards; RSS-only rows stay compact. */
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
    sortNewest: "Mới nhất",
    sortOldest: "Cũ nhất",
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

  function teaserCard(item) {
    const report = item && typeof item === "object" ? item : {};
    const li = make("li", "card card--report-teaser card--closed report-teaser");
    const header = make("div", "card__head", li);
    const badge = make("span", "badge badge--deep", header);
    text(badge, T.section);
    const lead = make("div", "card__lead", li);
    if (window.NV.videos && typeof window.NV.videos.thumb === "function") {
      window.NV.videos.thumb(lead, report.img, report.t || "");
    }
    const content = make("div", "report-teaser__content", lead);
    const title = make("h3", "card__title report-teaser__title", content);
    const link = make("a", "report-teaser__link", title);
    link.href = report.u || "#";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    text(link, report.t || "");
    const meta = make("p", "card__meta report-teaser__meta", content);
    text(meta, [report.s, formatDate(report.pi || report.p || report.d)].filter(Boolean).join(" · "));
    const foot = make("div", "card__foot", li);
    if (report.sum) {
      const body = make("div", "card__body", content);
      const snippet = make("p", "report-teaser__snippet", body);
      text(snippet, report.sum);
      body.hidden = true;
      const more = make("button", "card__more", foot);
      more.type = "button";
      more.addEventListener("click", () => {
        if (!window.NV.modal) return;
        body.hidden = false;
        window.NV.modal.open({
          title: report.t || "",
          node: body,
          onClose: () => { body.hidden = true; }
        });
      });
      text(more, "Xem thêm");
    }
    const cta = make("a", "report-teaser__cta", foot);
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

    const state = { query: "", source: "", sort: "newest" };

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
    [["newest", T.sortNewest], ["oldest", T.sortOldest], ["source", T.sortSource]].forEach(
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

    function published(item) {
      return item.pi || item.p || "";
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
            published(b).localeCompare(published(a));
        }
        const direction = state.sort === "oldest" ? 1 : -1;
        return direction * published(a).localeCompare(published(b));
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
      state.sort = "newest";
      input.value = "";
      sourceSelect.value = "";
      sortSelect.value = "newest";
      paint();
    });

    paint();
  }

  window.NV.reports = {
    daySection: daySection,
    renderIndex: renderIndex,
    teaserCard: teaserCard,
    cardList: cardList
  };
})();
