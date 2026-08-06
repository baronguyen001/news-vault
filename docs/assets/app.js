(function () {
  "use strict";

  /* ---------- Vietnamese user-facing strings ---------- */
  const T = {
    site: "Kho tin",
    gateHint: "Nhập mật khẩu để mở nội dung.",
    gateErrConfig: "Thiếu cấu hình trang. Không thể khởi động.",
    gateErrMalformed: "Cấu hình trang không hợp lệ.",
    badPassword: "Sai mật khẩu. Thử lại.",
    loadFailed: "Không tải được dữ liệu. Thử tải lại trang.",
    unlock: "Mở",
    unlocking: "Đang mở…",
    home: "Trang chủ",
    prev: "← Trước",
    next: "Sau →",
    briefTitle: "Tóm tắt ngày",
    analysisPanels: "Chuyên mục · Biểu đồ · Xu hướng",
    videosTitle: "Video YouTube",
    hideShorts: (n) => `Ẩn ${n} Short`,
    showShorts: (n) => `Hiện ${n} Short`,
    categoriesTitle: "Chuyên mục",
    trendingTitle: "Xu hướng",
    blindspotsTitle: "Góc chưa phủ",
    searchPlaceholder: "Tìm kiếm…",
    sortLabel: "Sắp xếp",
    searchVault: "Tìm toàn kho (!)",
    all: "Tất cả",
    highImpact: "Tác động cao",
    domestic: "Trong nước",
    international: "Quốc tế",
    law: "Pháp luật",
    analysis: "Có phân tích",
    saved: "Đã lưu",
    unread: "Chưa đọc",
    paid: "Trả phí",
    free: "Miễn phí",
    paidFirst: "Trả phí trước",
    score: "Điểm",
    newest: "Mới nhất",
    source: "Nguồn",
    readMore: "Xem thêm",
    readLess: "Thu gọn",
    expandAll: "Mở tất cả",
    collapseAll: "Thu gọn tất cả",
    analysisTitle: "Phân tích",
    context: "Bối cảnh",
    cause: "Nguyên nhân",
    purpose: "Mục đích",
    connection: "Liên hệ",
    sourcesN: (n) => `${n} nguồn`,
    clusterMore: "Các bài cùng chủ đề",
    save: "Lưu",
    savedBtn: "Đã lưu",
    copy: "Sao chép link",
    share: "Chia sẻ",
    open: "Mở",
    copyDone: "Đã sao chép link.",
    shareDone: "Đã tải ảnh chia sẻ.",
    exportMd: "Xuất Markdown",
    print: "In / PDF",
    telegram: "Gửi Telegram",
    watchlist: "Danh sách theo dõi",
    watchlistTitle: "Sửa danh sách theo dõi",
    watchlistHint: "Mỗi từ khóa một dòng",
    saveWatchlist: "Lưu",
    cancel: "Hủy",
    emptyResults: "Không có kết quả.",
    clearFilters: "Xóa bộ lọc",
    resetFilters: "Về mặc định",
    resetFiltersHint: "Xóa từ khóa, bộ lọc, thứ tự sắp xếp và thu gọn mọi thẻ",
    resultCount: (n) => `${n} kết quả`,
    loadingVault: "Đang tìm trong kho lưu trữ…",
    loadAllMonths: "Tìm toàn bộ các tháng",
    archiveSearchHint: "Kết quả toàn kho",
    calendarTitle: "Lịch tin",
    calNoNews: "Không có tin",
    calDayCount: (d, n) => `Ngày ${d}: ${n} tin`,
    monthNames: ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12"],
    weekdays: ["CN", "T2", "T3", "T4", "T5", "T6", "T7"],
    latestTitle: "Ngày mới nhất",
    forYou: "Cho bạn",
    noMatches: "Chưa có bài phù hợp.",
    sinceLast: (n) => `${n} bài mới từ lần trước`,
    entityTotal: (n) => `${n} bài`,
    paidOfTotal: (n) => `${n} bài trả phí`,
    weekRange: (a, b) => `Tuần ${a} – ${b}`,
    statsTitle: "Thống kê",
    topStories: "Tin nổi bật",
    themeToggle: "Đổi giao diện",
    serviceWorkerErr: "Không đăng ký được bộ nhớ ngoại tuyến.",
    errorGeneric: "Đã xảy ra lỗi."
  };

  /* ---------- Module root ---------- */
  const NV = window.NV || {};
  window.NV = NV;

  /* ---------- State ---------- */
  let config = null;
  let payload = null;
  let password = null;
  let manifest = null;
  let clusterInfo = {};
  let currentText = "";
  const DEFAULT_SORT = "paid";
  let currentSort = DEFAULT_SORT;
  let expandAll = false;
  let archiveCache = {};
  let selectedCardIndex = -1;
  let userWired = false;
  let gPrefix = false;

  /* ---------- DOM helpers ---------- */
  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return Array.from(document.querySelectorAll(sel)); }

  /** Create an element with optional class and parent. */
  function make(tag, cls, parent) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (parent) parent.appendChild(el);
    return el;
  }

  /** Safely set textContent. */
  function text(el, val) {
    el.textContent = val == null ? "" : String(val);
  }

  /** Escape a string for use in a RegExp. */
  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  /** Debounce a function by ms milliseconds. */
  function debounce(fn, ms) {
    let t;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  /** Format YYYY-MM-DD to DD/MM/YYYY. */
  function fmtDay(iso) {
    if (!iso || iso.length < 10) return iso || "";
    return `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
  }

  /** Return a friendly display time from a compact article. */
  function getTimeText(a) {
    const raw = a.pi || a.p || "";
    if (!raw) return "";
    if (/T\d{2}:/.test(raw)) {
      try {
        const d = new Date(raw);
        if (!isNaN(d)) return d.toLocaleString("vi-VN");
      } catch {}
    }
    return raw;
  }

  /** Split summary into paragraphs on blank lines. */
  function splitParagraphs(s) {
    return s.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  }

  /** Map impact level to a CSS-safe suffix. */
  function impactClass(im) {
    const map = { "cao": "cao", "trung bình": "tb", "thấp": "thap" };
    return map[im] || "tb";
  }

  /** Show a temporary toast message. */
  function toast(msg) {
    const t = make("div", "toast", document.body);
    text(t, msg);
    t.setAttribute("role", "status");
    setTimeout(() => t.classList.add("toast--out"), 2500);
    setTimeout(() => t.remove(), 3000);
  }

  /* ---------- Configuration ---------- */
  function parseConfig() {
    const el = document.getElementById("nv-config");
    if (!el) return null;
    try {
      return JSON.parse(el.textContent.trim());
    } catch {
      return null;
    }
  }

  function isValidConfig(cfg) {
    return cfg && typeof cfg === "object" && cfg.kind && cfg.base != null && cfg.dataUrl;
  }

  /* ---------- Manifest ---------- */
  async function loadManifest() {
    if (manifest) return;
    const res = await fetch(config.manifestUrl);
    if (!res.ok) throw new Error("manifest fetch failed");
    manifest = await res.json();
  }

  /* ---------- Service worker ---------- */
  function registerSW() {
    if (location.protocol === "file:") return;
    if (!("serviceWorker" in navigator)) return;
    try {
      navigator.serviceWorker.register(config.base + "sw.js").catch(() => {});
    } catch {
      toast(T.serviceWorkerErr);
    }
  }

  /* ---------- Gate ---------- */
  function showGateError(msg) {
    const err = $("#gate-err");
    if (err) {
      text(err, msg);
      err.hidden = false;
    }
  }

  function showGate() {
    const form = $("#gate-form");
    const input = $("#gate-pass");
    if (!form) return;
    form.addEventListener("submit", onGateSubmit);
    if (input) input.focus();
  }

  async function onGateSubmit(ev) {
    ev.preventDefault();
    const input = $("#gate-pass");
    const btn = $("#gate-go");
    const err = $("#gate-err");
    if (!input || !btn) return;
    const pw = input.value;
    if (!pw) return;
    btn.disabled = true;
    btn.classList.add("spinner");
    text(btn, T.unlocking);
    err.hidden = true;
    try {
      await unlock(pw);
    } catch (e) {
      btn.disabled = false;
      btn.classList.remove("spinner");
      text(btn, T.unlock);
      if (e && e.name === "BadPasswordError") {
        showGateError(T.badPassword);
        input.focus();
        input.select();
      } else {
        showGateError(T.loadFailed);
      }
    }
  }

  async function tryAutoUnlock() {
    const pw = NV.crypto.loadPassword();
    if (pw) {
      try {
        await unlock(pw);
        return;
      } catch {
        NV.crypto.clearPassword();
      }
    }
    showGate();
  }

  /** Unlock the payload and render the page. */
  async function unlock(pw) {
    const data = await NV.crypto.fetchJson(config.dataUrl, pw);
    payload = data;
    password = pw;
    try { await loadManifest(); } catch {}
    NV.crypto.savePassword(pw);
    hideGate();
    render();
    return true;
  }

  function hideGate() {
    const gate = $("#gate");
    const app = $("#app");
    if (gate) gate.hidden = true;
    if (app) {
      app.hidden = false;
      app.tabIndex = -1;
      app.focus();
    }
  }

  /* ---------- Rendering dispatch ---------- */
  function render() {
    if (!payload) return;
    clusterInfo = buildClusterMap(payload.clusters || []);
    if (config.kind === "day") renderDay();
    else if (config.kind === "home") renderHomeAfterUnlock();
    else if (config.kind === "entity") renderEntity();
    else if (config.kind === "week") renderWeek();
    wireUser();
    applyHash();
    scrollToAnchor();
  }

  function buildClusterMap(clusters) {
    const map = {};
    for (const c of clusters) {
      if (!c || !Array.isArray(c.members)) continue;
      for (const idx of c.members) {
        map[idx] = { cluster: c, isLead: idx === c.lead };
      }
    }
    return map;
  }

  /* ---------- Collapsible panels ----------
   * Everything above the headline list is analysis, not news. On a phone the panels
   * pushed the first headline three screens down, so they open closed and remember the
   * choice; the list itself is always the first thing under the search bar. */
  const PANEL_KEY = "nv.panels";
  const SHORTS_KEY = "nv.hideShorts";

  function panelState() {
    try {
      const raw = localStorage.getItem(PANEL_KEY);
      const data = raw ? JSON.parse(raw) : null;
      return data && typeof data === "object" ? data : {};
    } catch (err) {
      return {};
    }
  }

  function setPanelState(id, open) {
    try {
      const data = panelState();
      data[id] = !!open;
      localStorage.setItem(PANEL_KEY, JSON.stringify(data));
    } catch (err) {
      /* private mode: the panel still works, it just will not be remembered */
    }
  }

  /**
   * Create a <details> panel and return the body element callers fill in.
   *
   * Panels are closed unless the reader opened them before. `defaultOpen` flips that
   * for panels that carry content rather than analysis — the day's videos are things to
   * read, not a chart to consult, so they start open until the reader closes them.
   */
  function makePanel(parent, id, title, extraClass, defaultOpen) {
    const details = make("details", `panel panel--fold ${extraClass || ""}`.trim(), parent);
    const remembered = panelState()[id];
    details.open = remembered === undefined ? !!defaultOpen : remembered === true;
    const summary = make("summary", "panel__toggle", details);
    const label = make("span", "panel__toggle-label", summary);
    text(label, title);
    make("span", "panel__toggle-mark", summary);
    details.addEventListener("toggle", () => setPanelState(id, details.open));
    return make("div", "panel__body", details);
  }

  /* ---------- Day page ---------- */
  function renderDay() {
    const app = $("#app");
    text(app, "");
    app.className = "app app--day";
    renderDayTopbar(app);
    renderBrief(app);
    // One outer fold for all the analysis. Six separate collapsed panels still cost six
    // rows before the first headline; nested inside one row they cost none.
    const analysis = makePanel(app, "day-analysis", T.analysisPanels, "panel--outer");
    renderCategoryGrid(analysis);
    renderDayCharts(analysis);
    renderTrending(analysis);
    renderBlindspots(analysis);
    renderSearchbar(app);
    renderVideos(app);
    const wrap = make("div", "cards-wrap", app);
    const countEl = make("div", "result-count sr-only", wrap);
    countEl.setAttribute("aria-live", "polite");
    make("ul", "cards", wrap);
    const empty = make("div", "empty", wrap);
    empty.hidden = true;
    // Populate the list now. applyHash() only refreshes when a #q= hash is present,
    // so without this the first paint leaves an empty container.
    refresh();
  }

  function renderDayTopbar(parent) {
    const bar = make("header", "topbar", parent);
    const site = make("a", "topbar__site", bar);
    site.href = config.base || "./";
    text(site, config.site || T.site);
    const title = make("h1", "topbar__title", bar);
    text(title, fmtDay(config.day || payload.day));
    const nav = make("nav", "topbar__nav", bar);
    if (config.prev) {
      const a = make("a", "topbar__link topbar__link--prev", nav);
      a.href = `../${config.prev}/`;
      text(a, T.prev);
    }
    if (config.next) {
      const a = make("a", "topbar__link topbar__link--next", nav);
      a.href = `../${config.next}/`;
      text(a, T.next);
    }
    const home = make("a", "topbar__link topbar__link--home", nav);
    home.href = config.base || "./";
    text(home, T.home);
    // Column choice is a desktop affordance; the stylesheet hides it below 1024px.
    if (NV.layout) NV.layout.mount(nav);
    const theme = make("button", "topbar__btn", nav);
    theme.type = "button";
    text(theme, T.themeToggle);
    theme.addEventListener("click", toggleTheme);
    if (NV.user) {
      const saved = make("button", "topbar__chip", nav);
      saved.type = "button";
      updateSavedChip(saved);
      saved.addEventListener("click", () => setQuery("saved:true"));
      const watch = make("button", "topbar__btn", nav);
      watch.type = "button";
      text(watch, T.watchlist);
      watch.addEventListener("click", openWatchlist);
    }
    if (NV.share) {
      const md = make("button", "topbar__btn", nav);
      md.type = "button";
      text(md, T.exportMd);
      md.addEventListener("click", exportMarkdown);
      const print = make("button", "topbar__btn", nav);
      print.type = "button";
      text(print, T.print);
      print.addEventListener("click", () => NV.share.printPage());
      const tg = make("button", "topbar__btn", nav);
      tg.type = "button";
      text(tg, T.telegram);
      tg.addEventListener("click", shareTelegram);
    }
  }

  function updateSavedChip(el) {
    if (!el) return;
    const stats = NV.user ? NV.user.stats() : { saved: 0 };
    text(el, `${T.saved}: ${stats.saved}`);
  }

  function renderBrief(parent) {
    const bullets = payload.brief || [];
    if (!bullets.length) return;
    const sec = make("section", "brief", parent);
    const h = make("h2", "brief__title", sec);
    text(h, T.briefTitle);
    const ul = make("ul", "brief__list", sec);
    for (const b of bullets) {
      const li = make("li", "brief__item", ul);
      li.appendChild(document.createTextNode(b));
    }
  }

  /**
   * The day's YouTube summaries, folded like the analysis panels.
   *
   * They live in their own section rather than mixed into the article list because they
   * are a different kind of thing: no relevance score, no impact level, no topic from
   * the news taxonomy. Sorting them together would mean inventing numbers for them.
   */
  function renderVideos(parent) {
    if (!NV.videos) return;
    const list = payload.videos || [];
    if (!list.length) return;
    const shorts = list.filter((v) => v && v.sh);
    const body = makePanel(parent, "day-videos", `${T.videosTitle} (${list.length})`, "", true);
    // Shorts are 42% of the archive and a minute long. Someone here for the 40-minute
    // interviews should be able to put them away without losing them.
    if (shorts.length) body.appendChild(renderShortsToggle(shorts.length, list, body));
    fillVideos(body, list);
  }

  /** Replace the video list inside `body`, honouring the current Shorts preference. */
  function fillVideos(body, list) {
    const previous = body.querySelector(".videos");
    // The dialog may be holding one video card's body. Dropping the old section under it
    // would leave the dialog showing a card that no longer exists on the page.
    if (previous && NV.modal && NV.modal.isOpen()) NV.modal.close();
    if (previous) body.removeChild(previous);
    const visible = hideShorts() ? list.filter((v) => !(v && v.sh)) : list;
    const section = NV.videos.section(visible);
    if (!section) return;
    // The fold's own summary already names the section. While the panel opened closed
    // nobody saw the second copy; now that it starts open, the heading would appear twice.
    const heading = section.querySelector(".videos__title");
    if (heading) section.removeChild(heading);
    body.appendChild(section);
  }

  function hideShorts() {
    try {
      return localStorage.getItem(SHORTS_KEY) === "1";
    } catch (err) {
      return false;
    }
  }

  function renderShortsToggle(count, list, body) {
    const btn = make("button", "videos__filter", null);
    btn.type = "button";
    const paint = () => {
      const hidden = hideShorts();
      btn.setAttribute("aria-pressed", hidden ? "true" : "false");
      text(btn, hidden ? T.showShorts(count) : T.hideShorts(count));
    };
    btn.addEventListener("click", () => {
      try {
        localStorage.setItem(SHORTS_KEY, hideShorts() ? "0" : "1");
      } catch (err) {
        /* private mode: the choice still applies to this page, it is just not remembered */
      }
      paint();
      fillVideos(body, list);
    });
    paint();
    return btn;
  }

  function renderCategoryGrid(parent) {
    const cats = (payload.categories || []).filter(Boolean);
    if (!cats.length) return;
    const body = makePanel(parent, "day-categories", T.categoriesTitle);
    const sec = make("div", "grid", body);
    for (const c of cats) {
      const card = make("button", "cat", sec);
      card.type = "button";
      if (NV.icons) NV.icons.render(card, c.key, "cat__icon");
      const label = make("span", "cat__label", card);
      text(label, c.label);
      const count = make("span", "cat__count", card);
      text(count, String(c.count || 0));
      const cap = make("span", "cat__caption", card);
      // Paid coverage is the reason to open a category first, so surface it here.
      text(cap, c.paid ? T.paidOfTotal(c.paid) : "");
      card.addEventListener("click", () => setQuery(`topic:"${c.label}"`));
    }
  }

  function renderDayCharts(parent) {
    const charts = payload.charts || {};
    const titles = { topics: "Chủ đề", sources: "Nguồn", impact: "Tác động" };
    for (const key of ["topics", "sources", "impact"]) {
      const svg = charts[key];
      if (!svg) continue;
      const body = makePanel(parent, `day-chart-${key}`, titles[key], "panel--chart");
      const wrap = make("div", "panel__chart", body);
      wrap.style.overflowX = "auto";
      wrap.innerHTML = svg;
    }
  }

  function renderTrending(parent) {
    const list = payload.trending || [];
    if (!list.length) return;
    const panel = makePanel(parent, "day-trending", T.trendingTitle, "panel--trending");
    const ul = make("ul", "trending__list", panel);
    for (const t of list) {
      const li = make("li", "trending__item", ul);
      const btn = make("button", "trending__term", li);
      btn.type = "button";
      text(btn, t.label || t.term);
      btn.addEventListener("click", () => setQuery(String(t.label || t.term)));
      const meta = make("span", "trending__meta", li);
      text(meta, `${t.today || 0} · z ${(t.z || 0).toFixed(1)}`);
    }
  }

  function renderBlindspots(parent) {
    const list = payload.blindspots || [];
    if (!list.length) return;
    const panel = makePanel(parent, "day-blindspots", T.blindspotsTitle, "panel--blindspots");
    const ul = make("ul", "blindspots__list", panel);
    for (const b of list) {
      const li = make("li", "blindspots__item", ul);
      const topic = make("span", "blindspots__topic", li);
      text(topic, b.topic);
      const meta = make("span", "blindspots__meta", li);
      const today = Math.round((b.share_today || 0) * 100);
      const base = Math.round((b.share_baseline || 0) * 100);
      text(meta, `hôm nay ${today}% · trung bình ${base}%`);
    }
  }

  /* ---------- Search bar & chips ---------- */
  function renderSearchbar(parent) {
    const bar = make("div", "searchbar", parent);
    const input = make("input", "searchbar__input", bar);
    input.type = "search";
    input.id = "search-input";
    input.placeholder = T.searchPlaceholder;
    input.setAttribute("aria-label", T.searchPlaceholder);
    input.addEventListener("input", debounce(() => {
      currentText = input.value;
      updateHash();
      refresh();
    }, 150));
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && input.value.trim().startsWith("!")) {
        ev.preventDefault();
        runArchiveSearch();
      }
    });
    const sortWrap = make("label", "searchbar__sort", bar);
    const sort = make("select", "searchbar__select", sortWrap);
    sort.setAttribute("aria-label", T.sortLabel);
    const options = [["paid", T.paidFirst], ["score", T.score], ["newest", T.newest], ["source", T.source]];
    for (const [val, lab] of options) {
      const o = make("option", "", sort);
      o.value = val;
      text(o, lab);
    }
    sort.value = currentSort;
    sort.addEventListener("change", () => { currentSort = sort.value; refresh(); });
    // One button back to the default view. Chips, a typed query, the sort order and the
    // expand-all toggle are four separate pieces of state and clearing them one at a time
    // is how a reader ends up convinced the archive has lost half its articles.
    const reset = make("button", "searchbar__reset", bar);
    reset.type = "button";
    text(reset, T.resetFilters);
    reset.title = T.resetFiltersHint;
    reset.addEventListener("click", resetFilters);
    const toggleAll = make("button", "searchbar__expand", bar);
    toggleAll.type = "button";
    text(toggleAll, expandAll ? T.collapseAll : T.expandAll);
    toggleAll.addEventListener("click", () => {
      expandAll = !expandAll;
      text(toggleAll, expandAll ? T.collapseAll : T.expandAll);
      for (const card of $$("#app .card")) setCardOpen(card, expandAll);
    });
    const vault = make("button", "searchbar__vault", bar);
    vault.type = "button";
    text(vault, T.searchVault);
    vault.addEventListener("click", () => {
      if (!input.value.trim().startsWith("!")) input.value = "! " + input.value;
      currentText = input.value;
      updateHash();
      runArchiveSearch();
    });
    const chips = make("div", "chips", bar);
    renderChips(chips);
  }

  const QUICK_CHIPS = [
    { label: T.all, token: null },
    { label: T.paid, token: "tier:paid" },
    { label: T.free, token: "tier:free" },
    { label: T.highImpact, token: "impact:cao" },
    { label: T.domestic, token: "region:domestic" },
    { label: T.international, token: "region:international" },
    { label: T.law, token: "law:true" },
    { label: T.analysis, token: "analysis:true" }
  ];

  function allKnownFilterTokens() {
    const tokens = QUICK_CHIPS.filter((c) => c.token).map((c) => c.token);
    const topics = new Set((payload.articles || []).map((a) => a.tp).filter(Boolean));
    for (const tp of topics) tokens.push(`topic:"${tp}"`);
    return tokens;
  }

  function renderChips(parent) {
    const chips = QUICK_CHIPS.slice();
    if (NV.user) {
      chips.push({ label: T.saved, token: "saved:true" });
      chips.push({ label: T.unread, token: "unread:true" });
    }
    const topics = new Set((payload.articles || []).map((a) => a.tp).filter(Boolean));
    for (const tp of topics) chips.push({ label: tp, token: `topic:"${tp}"` });
    for (const c of chips) {
      const btn = make("button", "chip", parent);
      btn.type = "button";
      btn.dataset.token = c.token || "";
      text(btn, c.label);
      updateChipState(btn);
      btn.addEventListener("click", () => toggleChip(btn));
    }
  }

  function filterTokenRegex(token) {
    const idx = token.indexOf(":");
    if (idx < 0) return new RegExp(escapeRegExp(token), "i");
    const key = escapeRegExp(token.slice(0, idx));
    let val = token.slice(idx + 1).trim();
    let quoted = false;
    if (val.startsWith('"') && val.endsWith('"')) {
      quoted = true;
      val = val.slice(1, -1);
    }
    const escVal = escapeRegExp(val);
    return quoted
      ? new RegExp(`${key}\\s*:\\s*"${escVal}"`, "i")
      : new RegExp(`(?:^|\\s)${key}\\s*:\\s*${escVal}(?:\\s|$)`, "i");
  }

  function hasFilter(val, token) {
    return filterTokenRegex(token).test(" " + val + " ");
  }

  function hasAnyFilter(val) {
    return allKnownFilterTokens().some((t) => hasFilter(val, t));
  }

  function removeFilter(val, token) {
    return val.replace(filterTokenRegex(token), " ").replace(/\s+/g, " ").trim();
  }

  function stripAllFilters(val) {
    let out = val;
    for (const t of allKnownFilterTokens()) out = removeFilter(out, t);
    return out;
  }

  function updateChipState(btn) {
    const token = btn.dataset.token;
    const input = $("#search-input");
    const val = input ? input.value : currentText || "";
    const on = token ? hasFilter(val, token) : !hasAnyFilter(val);
    btn.classList.toggle("chip--on", on);
  }

  function updateAllChips() {
    for (const btn of $$(".chip")) updateChipState(btn);
  }

  function toggleChip(btn) {
    const token = btn.dataset.token;
    const input = $("#search-input");
    let val = input ? input.value : currentText || "";
    if (!token) {
      val = stripAllFilters(val);
    } else if (hasFilter(val, token)) {
      val = removeFilter(val, token);
    } else {
      val = (val.trim() + " " + token).trim();
    }
    if (input) input.value = val;
    currentText = val;
    updateHash();
    refresh();
    updateAllChips();
  }

  /* ---------- Filtering & results ---------- */
  function buildSearchItems(articles, day) {
    return (articles || []).map((a, i) => ({
      d: day,
      i: i,
      t: a.t || "",
      f: NV.search.fold(`${a.t || ""} ${(a.tg || []).join(" ")} ${a.sum || ""} ${a.s || ""} ${a.tp || ""} ${a.c || ""}`),
      s: a.s || "",
      sk: a.sk || "",
      tr: a.tr || "free",
      tp: a.tp || "",
      im: a.im || "",
      sc: a.sc ?? 0,
      r: a.r || "",
      tg: a.tg || [],
      u: a.u || "",
      law: !!a.law,
      analyzed: hasAnalysis(a),
      raw: a
    }));
  }

  function setUserFlags(items) {
    if (!NV.user) return;
    for (const it of items) {
      it.saved = NV.user.isSaved(it.u);
      it.unread = !NV.user.isRead(it.u);
    }
  }

  function refresh() {
    if (config.kind !== "day") return;
    const input = $("#search-input");
    const full = (input ? input.value : currentText || "").trim();
    if (full.startsWith("!")) {
      runArchiveSearch();
      return;
    }
    const items = buildSearchItems(payload.articles || [], config.day || payload.day);
    setUserFlags(items);
    const results = NV.search.run(items, full, { sort: currentSort });
    renderResults(results, NV.search.parse(full || ""));
    updateAllChips();
  }

  function renderResults(results, parsed) {
    const list = $("#app .cards-wrap .cards");
    const empty = $("#app .cards-wrap .empty");
    const countEl = $("#app .cards-wrap .result-count");
    if (!list) return;
    // The list is about to be wiped. A dialog is holding one card's body, and it would
    // survive the wipe with its content orphaned, so it closes first.
    if (NV.modal && NV.modal.isOpen()) NV.modal.close();
    text(list, "");
    const queryActive = (currentText || "").trim() !== "";
    let shown = 0;
    for (const it of results) {
      const a = it.raw;
      const ci = clusterInfo[it.i];
      if (!queryActive && ci && !ci.isLead) continue;
      list.appendChild(renderCard(a, it, parsed));
      shown++;
    }
    if (countEl) text(countEl, T.resultCount(shown));
    if (empty) {
      empty.hidden = shown > 0;
      text(empty, "");
      if (shown === 0) {
        const p = make("p", "empty__msg", empty);
        text(p, T.emptyResults);
        const btn = make("button", "empty__btn", empty);
        btn.type = "button";
        text(btn, T.clearFilters);
        btn.addEventListener("click", resetFilters);
      }
    }
    observeCards();
  }

  /* ---------- Article card ----------
   * A card shows a headline and nothing else until it is asked to. The summary, the key
   * points and the four analysis sections run to a couple of hundred words per article;
   * at ninety articles a day that is an unreadable wall on a phone. They all live in
   * .card__body, which is built once and then shown or hidden. */
  function renderCard(a, item, parsed) {
    const li = make("li", "card");
    li.id = `a-${a.i}`;
    // The topic drives a hue on both the card and its chip; NV.topics decides which.
    if (NV.topics) {
      const topicClass = NV.topics.className(a.tp);
      if (topicClass) li.classList.add(topicClass);
    }
    if (NV.user && NV.user.isRead(a.u)) li.classList.add("card--read");
    if (NV.user && NV.user.isSaved(a.u)) li.classList.add("card--saved");
    li.appendChild(renderCardHeader(a));
    // The article's own picture, when news-hunter found one. NV.videos owns the helper
    // because it enforces the https-only rule and the drop-on-error behaviour that a
    // url scraped off an arbitrary publisher page needs.
    const lead = make("div", "card__lead", li);
    if (NV.videos && a.img) NV.videos.thumb(lead, a.img, "");
    const textWrap = make("div", "", lead);
    const title = make("h3", "card__title", textWrap);
    const link = make("a", "card__link", title);
    link.href = a.u;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    if (parsed && !parsed.isEmpty && a.t) {
      link.innerHTML = NV.search.highlight(a.t, parsed);
    } else {
      text(link, a.t || "");
    }
    link.addEventListener("click", () => { if (NV.user) NV.user.markRead(a.u); });
    const meta = make("div", "card__meta", textWrap);
    // The topic has moved to a coloured chip in the header, so it comes out of the grey
    // meta line rather than being printed twice.
    text(meta, [a.s, getTimeText(a)].filter(Boolean).join(" · "));

    const body = make("div", "card__body", li);
    body.id = `b-${a.i}`;
    renderSummary(body, a, parsed);
    renderKeyPoints(body, a, parsed);
    renderTags(body, a);
    if (hasAnalysis(a)) body.appendChild(renderAnalysis(a, parsed));
    const ci = clusterInfo[a.i];
    if (ci && ci.isLead && ci.cluster.members.length > 1) {
      body.appendChild(renderCluster(ci.cluster));
    }
    body.appendChild(renderCardActions(a));

    // Saving is the one action worth doing straight off a headline, so it stays out of
    // the fold; copy, share and open live inside with the rest of the detail.
    const foot = make("div", "card__foot", li);
    const more = make("button", "card__more", foot);
    more.type = "button";
    more.setAttribute("aria-controls", body.id);
    more.addEventListener("click", () => {
      const closed = li.classList.contains("card--closed");
      if (closed && useModal()) {
        openCardModal(li);
        return;
      }
      setCardOpen(li, closed);
    });
    if (NV.user) renderSaveButton(a, foot);

    // Open on a text query so the highlighted match is visible without a second click.
    const hasQuery = parsed && !parsed.isEmpty && (parsed.terms.length || parsed.phrases.length);
    setCardOpen(li, expandAll || !!hasQuery);
    return li;
  }

  function hasAnalysis(a) {
    return !!(a.an && Object.values(a.an).some((v) => v && String(v).trim()));
  }

  /* A mouse user reading a three-column grid loses their place when a card grows under the
   * pointer and pushes its neighbours around, so on a fine pointer the body opens in a
   * dialog instead. Touch keeps the inline fold: there is one column, nothing to lose.
   * Bulk expansion (expand-all, a text query) stays inline in both - forty dialogs is not
   * a thing. */
  function useModal() {
    return !!(NV.modal && NV.read && NV.read.pointerFine());
  }

  /** Lend the card's own body to the dialog - not a copy, so every listener and every
   * search highlight travels with it - and fold the card back up when it returns. */
  function openCardModal(card) {
    const body = card.querySelector(".card__body");
    const more = card.querySelector(".card__more");
    const link = card.querySelector(".card__link");
    if (!body || !more) return;
    body.hidden = false;
    more.setAttribute("aria-expanded", "true");
    NV.modal.open({
      title: link ? link.textContent : "",
      node: body,
      onClose: () => setCardOpen(card, false)
    });
  }

  /** Show or hide one card's body and keep the toggle's label and ARIA state in step. */
  function setCardOpen(card, open) {
    const body = card.querySelector(".card__body");
    const more = card.querySelector(".card__more");
    if (!body || !more) return;
    card.classList.toggle("card--closed", !open);
    body.hidden = !open;
    more.setAttribute("aria-expanded", open ? "true" : "false");
    text(more, open ? T.readLess : T.readMore);
  }

  function renderCardHeader(a) {
    const header = make("div", "card__header", null);
    const score = make("span", "badge badge--score", header);
    text(score, a.sc ?? 0);
    if (a.tr === "paid") {
      const paid = make("span", "badge badge--paid", header);
      text(paid, T.paid);
    }
    if (a.tp) {
      const topic = make("span", "badge badge--topic", header);
      text(topic, a.tp);
    }
    if (a.im && a.im !== "không xác định") {
      const imp = make("span", `badge badge--impact impact-${impactClass(a.im)}`, header);
      text(imp, a.im);
    }
    if (hasAnalysis(a)) {
      const an = make("span", "badge badge--analysis", header);
      text(an, T.analysisTitle);
    }
    const ci = clusterInfo[a.i];
    if (ci && ci.isLead && ci.cluster.members.length > 1) {
      const src = make("span", "badge badge--sources", header);
      text(src, T.sourcesN(ci.cluster.members.length));
    }
    return header;
  }

  function setHighlighted(el, val, parsed) {
    if (parsed && !parsed.isEmpty && val) {
      el.innerHTML = NV.search.highlight(val, parsed);
    } else {
      text(el, val);
    }
  }

  // The whole card body is now behind one toggle, so the summary no longer needs a
  // second "read more" of its own - every paragraph is rendered.
  function renderSummary(parent, a, parsed) {
    const paras = splitParagraphs(a.sum || "");
    if (!paras.length) return;
    const wrap = make("div", "card__summary", parent);
    for (let i = 0; i < paras.length; i++) {
      const p = make("p", i === 0 ? "card__summary__first" : "", wrap);
      setHighlighted(p, paras[i], parsed);
    }
  }

  function renderKeyPoints(parent, a, parsed) {
    const kp = a.kp || [];
    if (!kp.length) return;
    const ul = make("ul", "card__points", parent);
    for (const p of kp) {
      const li = make("li", "", ul);
      setHighlighted(li, p, parsed);
    }
  }

  function findEntity(label) {
    if (!manifest || !manifest.entities) return null;
    const folded = NV.search.fold(label || "");
    return manifest.entities.find((e) => e.label === label || NV.search.fold(e.label || "") === folded);
  }

  function renderTags(parent, a) {
    const tags = a.tg || [];
    if (!tags.length) return;
    const wrap = make("div", "card__tags", parent);
    for (const tag of tags) {
      const entity = findEntity(tag);
      const el = make(entity ? "a" : "button", "card__tag", wrap);
      if (entity) {
        el.href = `${config.base}e/${entity.slug}/`;
      } else {
        el.type = "button";
        el.addEventListener("click", () => setQuery(`tag:"${tag}"`));
      }
      text(el, tag);
    }
  }

  function renderAnalysis(a, parsed) {
    const details = make("details", "card__analysis");
    const summary = make("summary", "card__analysis__title", details);
    text(summary, T.analysisTitle);
    const body = make("div", "card__analysis__body", details);
    const sections = [
      { key: "boi_canh", label: T.context },
      { key: "nguyen_nhan", label: T.cause },
      { key: "muc_dich", label: T.purpose },
      { key: "lien_he", label: T.connection }
    ];
    for (const sec of sections) {
      const val = a.an[sec.key];
      const h = make("h4", "card__analysis__section", body);
      text(h, sec.label);
      const p = make("p", "", body);
      setHighlighted(p, val || "", parsed);
    }
    return details;
  }

  function renderCluster(cluster) {
    const details = make("details", "cluster cluster__more");
    const summary = make("summary", "cluster__title", details);
    text(summary, T.clusterMore);
    const list = make("ul", "cluster__list", details);
    for (const idx of cluster.members) {
      if (idx === cluster.lead) continue;
      const m = payload.articles[idx];
      if (!m) continue;
      const li = make("li", "cluster__item", list);
      const link = make("a", "cluster__link", li);
      link.href = m.u;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      text(link, m.t || "");
      if (NV.user) link.addEventListener("click", () => NV.user.markRead(m.u));
      const meta = make("span", "cluster__meta", li);
      text(meta, [m.s, getTimeText(m)].filter(Boolean).join(" · "));
    }
    return details;
  }

  /** The save button, which stays out of the fold - see renderCard. */
  function renderSaveButton(a, parent) {
    const save = make("button", "card__action card__action--save", parent);
    save.type = "button";
    updateSaveButton(save, a.u);
    save.addEventListener("click", () => {
      NV.user.toggleSave(a.u);
      updateSaveButton(save, a.u);
      updateSavedChip($(".topbar__chip"));
      NV.app.refresh();
    });
    return save;
  }

  function renderCardActions(a) {
    const actions = make("div", "card__actions", null);
    const copy = make("button", "card__action", actions);
    copy.type = "button";
    text(copy, T.copy);
    copy.addEventListener("click", async () => {
      try {
        if (NV.share && NV.share.copyText) {
          await NV.share.copyText(a.u);
        } else {
          await navigator.clipboard.writeText(a.u);
        }
        toast(T.copyDone);
      } catch {
        toast(T.errorGeneric);
      }
    });
    if (NV.share && NV.share.cardPng) {
      const share = make("button", "card__action", actions);
      share.type = "button";
      text(share, T.share);
      share.addEventListener("click", async () => {
        try {
          const blob = await NV.share.cardPng(a, {});
          const url = URL.createObjectURL(blob);
          const dl = document.createElement("a");
          dl.href = url;
          dl.download = `card-${a.i}.png`;
          dl.click();
          setTimeout(() => URL.revokeObjectURL(url), 5000);
          toast(T.shareDone);
        } catch {
          toast(T.errorGeneric);
        }
      });
    }
    const open = make("button", "card__action", actions);
    open.type = "button";
    text(open, T.open);
    open.addEventListener("click", () => {
      if (NV.user) NV.user.markRead(a.u);
      window.open(a.u, "_blank", "noopener,noreferrer");
    });
    return actions;
  }

  function updateSaveButton(btn, url) {
    const saved = NV.user && NV.user.isSaved(url);
    btn.classList.toggle("card__action--saved", saved);
    text(btn, saved ? T.savedBtn : T.save);
  }

  /* Read-marking. NV.read owns the *rule* - dwell on a mouse, scrolled-past on a phone -
   * and this owns what "read" means here: the stored set plus the dimmed class, applied
   * live so the reader gets some confirmation rather than a silent state change. The old
   * handle is dropped on every render; the cards it was watching no longer exist. */
  let readHandle = null;

  function observeCards() {
    if (!NV.user || !NV.read) return;
    if (readHandle) readHandle.disconnect();
    readHandle = NV.read.observe($$(".cards-wrap .card"), {
      onRead: (url, card) => {
        NV.user.markRead(url);
        card.classList.add("card--read");
      }
    });
  }

  /* ---------- Archive search ---------- */
  async function runArchiveSearch(forceAll = false) {
    const input = $("#search-input");
    const full = (input ? input.value : currentText || "").trim();
    if (!full.startsWith("!")) return;
    const query = full.slice(1).trim();
    const list = $("#app .cards-wrap .cards");
    const empty = $("#app .cards-wrap .empty");
    const countEl = $("#app .cards-wrap .result-count");
    if (list) text(list, T.loadingVault + "…");
    try {
      if (!manifest) await loadManifest();
      const items = await loadArchiveItems(query, forceAll);
      setUserFlags(items);
      const parsed = NV.search.parse(query);
      const results = NV.search.run(items, query, { sort: currentSort });
      renderArchiveResults(results, parsed, forceAll);
      if (countEl) text(countEl, T.resultCount(results.length));
      if (empty) empty.hidden = results.length > 0;
    } catch {
      if (list) text(list, "");
      if (empty) {
        empty.hidden = false;
        text(empty, T.loadFailed);
      }
    }
  }

  async function loadArchiveItems(query, forceAll) {
    const parsed = NV.search.parse(query);
    const hasDay = parsed.filters && parsed.filters.day;
    const months = pickMonths(manifest.months || [], forceAll || hasDay);
    let items = [];
    for (const m of months) {
      if (!archiveCache[m]) {
        const url = (config.indexBase || "") + m + ".enc";
        const shard = await NV.crypto.fetchJson(url, password);
        archiveCache[m] = shard.items || [];
      }
      items = items.concat(archiveCache[m]);
    }
    return items;
  }

  function pickMonths(months, all) {
    const sorted = [...months].sort().reverse();
    return all ? sorted : sorted.slice(0, 3);
  }

  function renderArchiveResults(results, parsed, forceAll) {
    const list = $("#app .cards-wrap .cards");
    if (!list) return;
    text(list, "");
    const header = make("li", "archive__header", list);
    const h = make("h3", "", header);
    text(h, T.archiveSearchHint);
    if (!forceAll) {
      const btn = make("button", "archive__load-all", header);
      btn.type = "button";
      text(btn, T.loadAllMonths);
      btn.addEventListener("click", () => runArchiveSearch(true));
    }
    for (const it of results) {
      const li = make("li", "archive__hit", list);
      const dayLink = make("a", "archive__day", li);
      dayLink.href = `${config.base}d/${it.d}/#a-${it.i}`;
      text(dayLink, fmtDay(it.d));
      const src = make("span", "archive__source", li);
      text(src, it.tr === "paid" ? `${it.s || ""} · ${T.paid}` : it.s || "");
      const score = make("span", "archive__score", li);
      text(score, it.sc ?? 0);
      const title = make("a", "archive__title", li);
      title.href = `${config.base}d/${it.d}/#a-${it.i}`;
      if (parsed && !parsed.isEmpty && it.t) {
        title.innerHTML = NV.search.highlight(it.t, parsed);
      } else {
        text(title, it.t || "");
      }
    }
  }

  /* ---------- Query & hash ---------- */
  /** Every filter back to how the page opens: no query, no chip, default sort, cards folded. */
  function resetFilters() {
    currentSort = DEFAULT_SORT;
    const sort = $("#app .searchbar__select");
    if (sort) sort.value = DEFAULT_SORT;
    if (expandAll) {
      expandAll = false;
      const toggle = $("#app .searchbar__expand");
      if (toggle) text(toggle, T.expandAll);
    }
    // Last: it repaints the list, so every flag above must already be right.
    setQuery("");
  }

  function setQuery(q) {
    const input = $("#search-input");
    if (input) input.value = q;
    currentText = q;
    updateHash();
    refresh();
  }

  function updateHash() {
    const q = (currentText || "").trim();
    if (q) {
      const hash = "#q=" + encodeURIComponent(q);
      if (location.hash !== hash) location.hash = hash;
    } else if (location.hash.startsWith("#q=")) {
      history.replaceState("", document.title, location.pathname + location.search);
    }
  }

  function applyHash() {
    const hash = location.hash;
    const input = $("#search-input");
    if (hash.startsWith("#q=")) {
      const q = decodeURIComponent(hash.slice(3));
      if (input && input.value !== q) {
        input.value = q;
        currentText = q;
        if (q.startsWith("!")) runArchiveSearch(); else refresh();
      } else if (!input) {
        currentText = q;
      }
    } else if (input && input.value !== "") {
      input.value = "";
      currentText = "";
      refresh();
    }
  }

  function scrollToAnchor() {
    if (!location.hash.startsWith("#a-")) return;
    const el = document.getElementById(location.hash.slice(1));
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("card--target");
    }
  }

  /* ---------- Home page ---------- */
  async function drawHomeCalendar() {
    try {
      await loadManifest();
      const app = $("#app");
      app.hidden = false;
      renderCalendar(app);
    } catch {
      const app = $("#app");
      if (app) {
        app.hidden = false;
        text(app, T.loadFailed);
      }
    }
  }

  function renderCalendar(parent) {
    const sec = make("section", "cal", parent);
    const h = make("h2", "cal__title", sec);
    text(h, T.calendarTitle);
    const days = (manifest.days || []).slice().sort((a, b) => a.d.localeCompare(b.d));
    const counts = days.map((d) => d.n || 0);
    const max = Math.max(...counts, 1);
    const byMonth = new Map();
    for (const d of days) {
      const m = d.d.slice(0, 7);
      if (!byMonth.has(m)) byMonth.set(m, []);
      byMonth.get(m).push(d);
    }
    for (const [m, mDays] of byMonth) {
      const monthSec = make("section", "cal__month", sec);
      const mh = make("h3", "cal__month-name", monthSec);
      const [y, mo] = m.split("-");
      text(mh, `${T.monthNames[parseInt(mo, 10) - 1]} ${y}`);
      const grid = make("div", "cal__grid", monthSec);
      for (const wd of T.weekdays) {
        const th = make("div", "cal__weekday", grid);
        text(th, wd);
      }
      // T.weekdays starts on Sunday, so the leading pad must be the Sunday-based day
      // index. Using a Monday-based one put every date one column off.
      const year = parseInt(y, 10);
      const month = parseInt(mo, 10);
      const pad = new Date(year, month - 1, 1).getDay();
      for (let i = 0; i < pad; i++) make("div", "cal__cell cal__cell--pad", grid);

      // Walk every date of the month, not just the ones that have articles: skipping a
      // quiet day used to shift every following date into the wrong weekday column.
      const counted = new Map(mDays.map((d) => [d.d, d.n || 0]));
      const lastDay = new Date(year, month, 0).getDate();
      for (let dayNum = 1; dayNum <= lastDay; dayNum++) {
        const key = `${m}-${String(dayNum).padStart(2, "0")}`;
        const n = counted.get(key);
        if (n === undefined) {
          const blank = make("div", "cal__cell cal__cell--empty", grid);
          text(blank, dayNum);
          blank.title = T.calNoNews;
          continue;
        }
        const cell = make("a", "cal__cell", grid);
        cell.href = `${config.base}d/${key}/`;
        text(cell, dayNum);
        cell.title = T.calDayCount(dayNum, n);
        const bucket = Math.min(4, Math.ceil((n / max) * 4)) || 1;
        cell.classList.add(`cal__cell--l${bucket}`);
      }
    }
  }

  function renderHomeAfterUnlock() {
    const app = $("#app");
    const latest = payload;
    if (!latest || latest.kind !== "day") return;
    const latestSec = make("section", "latest", app);
    const h = make("h2", "latest__title", latestSec);
    text(h, T.latestTitle);
    if (latest.brief && latest.brief.length) {
      const brief = make("div", "brief brief--latest", latestSec);
      const bh = make("h3", "brief__title", brief);
      text(bh, T.briefTitle);
      const ul = make("ul", "brief__list", brief);
      for (const b of latest.brief) {
        const li = make("li", "brief__item", ul);
        li.appendChild(document.createTextNode(b));
      }
    }
    const wrap = make("div", "cards-wrap", latestSec);
    make("div", "result-count sr-only", wrap).setAttribute("aria-live", "polite");
    const list = make("ul", "cards", wrap);
    const parsed = NV.search.parse("");
    for (const a of (latest.articles || []).slice(0, 10)) {
      list.appendChild(renderCard(a, { raw: a, u: a.u, i: a.i }, parsed));
    }
    if (NV.user) renderForYou(app, latest);
  }

  function renderForYou(parent, latest) {
    const sec = make("section", "for-you", parent);
    const h = make("h2", "for-you__title", sec);
    text(h, T.forYou);
    const items = buildSearchItems(latest.articles || [], latest.day || config.latest).filter((it) => NV.user.matchesWatchlist(it));
    const list = make("ul", "cards", sec);
    const parsed = NV.search.parse("");
    for (const it of items.slice(0, 10)) {
      list.appendChild(renderCard(it.raw, it, parsed));
    }
    if (!items.length) {
      const p = make("p", "", sec);
      text(p, T.noMatches);
    }
    const last = NV.user.lastVisit();
    if (last) {
      const count = (latest.articles || []).filter((a) => {
        const raw = a.pi || a.p;
        if (!raw) return false;
        try { return new Date(raw).getTime() > last; } catch { return false; }
      }).length;
      const p = make("p", "for-you__since", sec);
      text(p, T.sinceLast(count));
    }
    NV.user.touchVisit();
  }

  /* ---------- Entity page ---------- */
  /** Minimal topbar for the entity and week pages: without it those pages are a dead end. */
  function renderSimpleTopbar(parent) {
    // No title here: the page already carries its own <h1> immediately below, and
    // repeating it in the bar just wastes a line of a phone screen.
    const bar = make("header", "topbar", parent);
    const site = make("a", "topbar__site", bar);
    site.href = config.base || "./";
    text(site, config.site || T.site);
    const nav = make("nav", "topbar__nav", bar);
    const home = make("a", "topbar__link topbar__link--home", nav);
    home.href = config.base || "./";
    text(home, T.home);
    if (config.latest || (manifest && manifest.days && manifest.days.length)) {
      const latest = config.latest ||
        manifest.days[manifest.days.length - 1].d;
      const day = make("a", "topbar__link", nav);
      day.href = `${config.base || ""}d/${latest}/`;
      text(day, T.latestTitle);
    }
    if (NV.layout) NV.layout.mount(nav);
    const theme = make("button", "topbar__btn", nav);
    theme.type = "button";
    text(theme, T.themeToggle);
    theme.addEventListener("click", toggleTheme);
    return bar;
  }

  function renderEntity() {
    const app = $("#app");
    text(app, "");
    app.className = "app app--entity";
    renderSimpleTopbar(app);
    const header = make("header", "entity__header", app);
    const h = make("h1", "entity__title", header);
    text(h, payload.label || config.label);
    const total = make("span", "entity__total", header);
    text(total, T.entityTotal(payload.total || 0));
    if (payload.charts && payload.charts.timeline) {
      const panel = make("section", "panel panel--chart", app);
      const wrap = make("div", "panel__chart", panel);
      wrap.style.overflowX = "auto";
      wrap.innerHTML = payload.charts.timeline;
    }
    const grouped = new Map();
    for (const a of payload.articles || []) {
      if (!grouped.has(a.d)) grouped.set(a.d, []);
      grouped.get(a.d).push(a);
    }
    const days = Array.from(grouped.keys()).sort().reverse();
    const parsed = NV.search.parse("");
    for (const d of days) {
      const sec = make("section", "day-group", app);
      const dh = make("h2", "day-group__title", sec);
      const link = make("a", "", dh);
      link.href = `${config.base}d/${d}/`;
      text(link, fmtDay(d));
      const list = make("ul", "cards", make("div", "cards-wrap", sec));
      for (const a of grouped.get(d)) {
        list.appendChild(renderCard(a, { raw: a, u: a.u, i: a.i }, parsed));
      }
    }
  }

  /* ---------- Week page ---------- */
  function renderWeek() {
    const app = $("#app");
    text(app, "");
    app.className = "app app--week";
    renderSimpleTopbar(app);
    const header = make("header", "week__header", app);
    const h = make("h1", "week__title", header);
    text(h, T.weekRange(fmtDay(payload.start), fmtDay(payload.end)));
    if (payload.stats) renderWeekStats(app, payload.stats);
    const charts = payload.charts || {};
    const titles = { topics: "Chủ đề", volume: "Khối lượng", sources: "Nguồn" };
    for (const key of ["topics", "volume", "sources"]) {
      if (!charts[key]) continue;
      const panel = make("section", "panel panel--chart", app);
      const wrap = make("div", "panel__chart", panel);
      wrap.style.overflowX = "auto";
      wrap.innerHTML = charts[key];
    }
    renderTrending(app);
    const topSec = make("section", "top-stories", app);
    const th = make("h2", "top-stories__title", topSec);
    text(th, T.topStories);
    const list = make("ul", "cards", make("div", "cards-wrap", topSec));
    const parsed = NV.search.parse("");
    for (const a of payload.top || []) {
      list.appendChild(renderCard(a, { raw: a, u: a.u, i: a.i }, parsed));
    }
  }

  function renderWeekStats(parent, stats) {
    const sec = make("section", "stats", parent);
    const h = make("h2", "stats__title", sec);
    text(h, T.statsTitle);
    const grid = make("div", "stats__grid", sec);
    const blocks = [
      { label: "Tổng số bài", val: stats.total },
      { label: "Số nguồn", val: stats.sources }
    ];
    for (const b of blocks) {
      const cell = make("div", "stats__cell", grid);
      const v = make("span", "stats__value", cell);
      text(v, b.val);
      const l = make("span", "stats__label", cell);
      text(l, b.label);
    }
  }

  /* ---------- Optional module wiring ---------- */
  function wireUser() {
    if (!NV.user || userWired) return;
    userWired = true;
    NV.user.on("change", () => {
      updateSavedChip($(".topbar__chip"));
      NV.app.refresh();
    });
  }

  function exportMarkdown() {
    if (!NV.share || !NV.share.toMarkdown) return;
    const items = getVisibleArticles();
    const md = NV.share.toMarkdown(payload, items);
    NV.share.download("kho-tin.md", md, "text/markdown");
  }

  function getVisibleArticles() {
    const cards = $$(".cards-wrap .card");
    return cards.map((c) => {
      const id = c.id.replace("a-", "");
      if (config.kind === "day") {
        const idx = parseInt(id, 10);
        return payload.articles[idx];
      }
      return null;
    }).filter(Boolean);
  }

  function shareTelegram() {
    if (!NV.share || !NV.share.telegramUrl) return;
    const url = location.href.split("#")[0];
    const text = `${config.site || T.site}${config.day ? " " + fmtDay(config.day) : ""}`;
    window.open(NV.share.telegramUrl(url, text), "_blank", "noopener,noreferrer");
  }

  function toggleChipByToken(token) {
    for (const btn of $$(".chip")) {
      if (btn.dataset.token === token) {
        toggleChip(btn);
        return;
      }
    }
    setQuery(token);
  }

  function toggleTheme() {
    if (NV.user) {
      const next = NV.user.theme() === "dark" ? "light" : "dark";
      NV.user.setTheme(next);
    } else {
      const html = document.documentElement;
      const cur = html.dataset.theme || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      html.dataset.theme = cur === "dark" ? "light" : "dark";
    }
  }

  function openWatchlist() {
    if (!NV.user) return;
    let dlg = document.getElementById("watchlist-dialog");
    if (!dlg) {
      dlg = make("dialog", "dialog dialog--watchlist", document.body);
      dlg.id = "watchlist-dialog";
      const form = make("form", "dialog__form", dlg);
      const h = make("h2", "dialog__title", form);
      text(h, T.watchlistTitle);
      const hint = make("p", "dialog__hint", form);
      text(hint, T.watchlistHint);
      const ta = make("textarea", "dialog__input", form);
      ta.id = "watchlist-input";
      const actions = make("div", "dialog__actions", form);
      const save = make("button", "dialog__btn dialog__btn--primary", actions);
      save.type = "submit";
      text(save, T.saveWatchlist);
      const cancel = make("button", "dialog__btn", actions);
      cancel.type = "button";
      text(cancel, T.cancel);
      cancel.addEventListener("click", () => dlg.close());
      form.addEventListener("submit", (ev) => {
        ev.preventDefault();
        const terms = ta.value.split(/\n/).map((s) => s.trim()).filter(Boolean);
        NV.user.setWatchlist(terms);
        dlg.close();
        NV.app.refresh();
      });
    }
    const ta = $("#watchlist-input");
    ta.value = NV.user.watchlist().join("\n");
    dlg.showModal();
  }

  function wirePalette() {
    if (!NV.palette) return;
    const commands = [
      { id: "focus-search", label: "Tìm kiếm", hint: "/", group: "Điều hướng", run: () => $("#search-input")?.focus() },
      { id: "toggle-theme", label: "Đổi giao diện", hint: "t", group: "Giao diện", run: toggleTheme },
      { id: "prev-day", label: "Ngày trước", hint: "h", group: "Điều hướng", run: () => { if (config.prev) location.href = `../${config.prev}/`; } },
      { id: "next-day", label: "Ngày sau", hint: "l", group: "Điều hướng", run: () => { if (config.next) location.href = `../${config.next}/`; } },
      { id: "go-home", label: "Trang chủ", hint: "g h", group: "Điều hướng", run: () => { location.href = config.base || "./"; } },
      { id: "export-md", label: "Xuất Markdown", hint: "e", group: "Chia sẻ", run: exportMarkdown },
      { id: "print", label: "In / PDF", hint: "p", group: "Chia sẻ", run: () => { if (NV.share) NV.share.printPage(); } },
      { id: "toggle-saved", label: "Chỉ tin đã lưu", hint: "f", group: "Lọc", run: () => toggleChipByToken("saved:true") },
      { id: "only-paid", label: "Chỉ nguồn trả phí", group: "Lọc", run: () => toggleChipByToken("tier:paid") },
      { id: "only-unread", label: "Chỉ tin chưa đọc", group: "Lọc", run: () => toggleChipByToken("unread:true") },
      { id: "expand-card", label: "Mở rộng bài đang chọn", hint: "x", group: "Đọc", run: expandSelected },
      { id: "clear-filters", label: "Xóa bộ lọc", hint: "c", group: "Lọc", run: resetFilters },
      { id: "watchlist", label: "Danh sách theo dõi", hint: "w", group: "Cá nhân", run: openWatchlist }
    ];
    NV.palette.register(commands);
  }

  /* ---------- Keyboard shortcuts ---------- */
  function isTypingTarget(el) {
    if (!el) return false;
    const tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
  }

  function moveSelection(dir) {
    const cards = $$(".cards-wrap .card");
    if (!cards.length) return;
    if (selectedCardIndex >= 0) cards[selectedCardIndex].classList.remove("card--selected");
    selectedCardIndex += dir;
    if (selectedCardIndex < 0) selectedCardIndex = cards.length - 1;
    if (selectedCardIndex >= cards.length) selectedCardIndex = 0;
    const card = cards[selectedCardIndex];
    card.classList.add("card--selected");
    card.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function openSelectedArticle() {
    const cards = $$(".cards-wrap .card");
    if (selectedCardIndex < 0 || selectedCardIndex >= cards.length) return;
    const link = cards[selectedCardIndex].querySelector(".card__link");
    if (link) {
      if (NV.user) NV.user.markRead(link.href);
      window.open(link.href, "_blank", "noopener,noreferrer");
    }
  }

  /** Expand or collapse the card the keyboard cursor is on. */
  function expandSelected() {
    const cards = $$(".cards-wrap .card");
    if (selectedCardIndex < 0 || selectedCardIndex >= cards.length) return;
    const card = cards[selectedCardIndex];
    setCardOpen(card, card.classList.contains("card--closed"));
  }

  function toggleSelectedSave() {
    const cards = $$(".cards-wrap .card");
    if (selectedCardIndex < 0 || selectedCardIndex >= cards.length) return;
    const link = cards[selectedCardIndex].querySelector(".card__link");
    if (!link || !NV.user) return;
    NV.user.toggleSave(link.href);
    updateSavedChip($(".topbar__chip"));
    NV.app.refresh();
  }

  function onKeyDown(ev) {
    if (isTypingTarget(ev.target)) return;
    if (ev.key === "/") {
      ev.preventDefault();
      $("#search-input")?.focus();
      return;
    }
    if (ev.key === "?") {
      ev.preventDefault();
      if (NV.palette) NV.palette.open();
      return;
    }
    if (ev.key === "g") {
      gPrefix = true;
      setTimeout(() => { gPrefix = false; }, 1000);
      return;
    }
    if (gPrefix) {
      gPrefix = false;
      if (ev.key.toLowerCase() === "h") {
        ev.preventDefault();
        location.href = config.base || "./";
      }
      return;
    }
    switch (ev.key) {
      case "j":
      case "ArrowDown":
        ev.preventDefault();
        moveSelection(1);
        break;
      case "k":
      case "ArrowUp":
        ev.preventDefault();
        moveSelection(-1);
        break;
      case "o":
        ev.preventDefault();
        openSelectedArticle();
        break;
      case "Enter":
      case "x":
        ev.preventDefault();
        expandSelected();
        break;
      case "s":
        ev.preventDefault();
        toggleSelectedSave();
        break;
      case "t":
        ev.preventDefault();
        toggleTheme();
        break;
      case "f":
        ev.preventDefault();
        toggleChipByToken("saved:true");
        break;
      case "c":
        ev.preventDefault();
        resetFilters();
        break;
      case "w":
        ev.preventDefault();
        openWatchlist();
        break;
      case "e":
        ev.preventDefault();
        exportMarkdown();
        break;
      case "p":
        ev.preventDefault();
        if (NV.share) NV.share.printPage();
        break;
    }
  }

  /* ---------- Boot ---------- */
  function boot() {
    const cfg = parseConfig();
    if (!cfg || !isValidConfig(cfg)) {
      const gate = $("#gate");
      if (gate) {
        const err = make("p", "gate__err", gate);
        text(err, cfg === null ? T.gateErrConfig : T.gateErrMalformed);
        err.hidden = false;
      }
      return;
    }
    config = cfg;
    // Must run before anything reads saved/read/watchlist state or paints, otherwise the
    // stored theme flashes in late and every saved article looks unsaved.
    if (NV.user) NV.user.init();
    registerSW();
    wirePalette();
    loadManifest().catch(() => {});
    if (config.kind === "home") drawHomeCalendar();
    tryAutoUnlock();
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("hashchange", applyHash);
  }

  /* ---------- Public API ---------- */
  NV.app = {
    get config() { return config; },
    get data() { return payload; },
    get password() { return password; },
    refresh: refresh,
    setQuery: setQuery,
    unlock: unlock
  };

  document.addEventListener("DOMContentLoaded", boot);
})();
