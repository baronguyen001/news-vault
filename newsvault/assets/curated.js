/* Deep-dive analyses ("Phân tích sâu").
 *
 * These run 800-1200 words with a seven-section structure, which is a different reading
 * problem from the 300-600 word recaps in videos.js: a fold-out card cannot hold one, so
 * each gets its own page with a table of contents, a reading-progress bar and a measured
 * text column.
 *
 * Class names are deliberately NOT shared with the article/video card system (.cards,
 * .card__*). A shared presentational class plus a global selector is what once made
 * `$("#app .cards")` match the video list instead of the article list and blank out a
 * whole day page; `.dcards` / `.dcard__*` / `.deep__*` keep this section addressable on
 * its own terms.
 */
(function () {
  "use strict";

  if (!window.NV) window.NV = {};

  const T = {
    section: "Phân tích sâu",
    toc: "Nội dung bài",
    minutes: "phút đọc",
    words: "từ",
    watch: "Xem video gốc",
    back: "Về danh sách phân tích",
    backShort: "Danh sách",
    empty: "Chưa có bài phân tích nào.",
    countOne: "1 bài",
    countMany: " bài",
    readOn: "Đọc bài phân tích"
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

  function two(n) {
    return n < 10 ? "0" + n : "" + n;
  }

  function formatDate(iso) {
    if (!isNonEmptyString(iso)) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    return two(d.getDate()) + "/" + two(d.getMonth() + 1) + "/" + d.getFullYear();
  }

  function appendRuns(parent, runs) {
    if (!Array.isArray(runs)) return;
    for (let i = 0; i < runs.length; i++) {
      const run = runs[i];
      if (!Array.isArray(run) || run.length < 1) continue;
      const runText = run[0];
      if (run[1]) {
        const strong = make("strong");
        text(strong, runText);
        parent.appendChild(strong);
      } else {
        parent.appendChild(document.createTextNode(runText == null ? "" : String(runText)));
      }
    }
  }

  function runsText(runs) {
    if (!Array.isArray(runs)) return "";
    let out = "";
    for (let i = 0; i < runs.length; i++) {
      const run = runs[i];
      if (Array.isArray(run) && run.length) out += run[0] == null ? "" : String(run[0]);
    }
    return out;
  }

  /* Thumbnails come from a third party inside an encrypted payload; only https is accepted. */
  function validHttpsUrl(url) {
    if (!url) return null;
    try {
      if (new URL(url).protocol !== "https:") return null;
    } catch (e) {
      return null;
    }
    return url;
  }

  function appendEmptyThumbIcon(wrapper) {
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("viewBox", "0 0 24 24");
    icon.setAttribute("aria-hidden", "true");
    icon.setAttribute("focusable", "false");
    const frame = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    frame.setAttribute("x", "3");
    frame.setAttribute("y", "4");
    frame.setAttribute("width", "18");
    frame.setAttribute("height", "16");
    frame.setAttribute("rx", "2");
    const mountain = document.createElementNS("http://www.w3.org/2000/svg", "path");
    mountain.setAttribute("d", "m4 17 5-5 4 4 3-3 4 4");
    const sun = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    sun.setAttribute("cx", "16");
    sun.setAttribute("cy", "9");
    sun.setAttribute("r", "1.5");
    icon.appendChild(frame);
    icon.appendChild(mountain);
    icon.appendChild(sun);
    wrapper.appendChild(icon);
  }

  function emptyThumb(parent, cls) {
    const wrapper = make("div", (cls ? cls + " " : "") + "card__thumb--empty", parent);
    appendEmptyThumbIcon(wrapper);
    return wrapper;
  }

  function showEmptyThumb(wrapper) {
    while (wrapper.firstChild) wrapper.removeChild(wrapper.firstChild);
    wrapper.classList.add("card__thumb--empty");
    appendEmptyThumbIcon(wrapper);
  }

  function thumb(parent, url, alt, cls) {
    const primary = validHttpsUrl(url);
    if (!primary) return emptyThumb(parent, cls);
    const wrapper = make("div", cls, parent);
    const img = make("img", "", wrapper);
    img.src = primary;
    img.loading = "lazy";
    img.decoding = "async";
    img.referrerPolicy = "no-referrer";
    img.alt = alt == null ? "" : String(alt);
    img.onerror = function () { showEmptyThumb(wrapper); };
    return wrapper;
  }

  function metaLine(item) {
    const parts = [];
    if (isNonEmptyString(item.c)) parts.push(item.c);
    const when = formatDate(item.p);
    if (when) parts.push(when);
    const minutes = Number(item.m);
    if (minutes > 0) parts.push(minutes + " " + T.minutes);
    return parts.join(" · ");
  }

  /* One teaser card. `base` is the page's relative root, so the same builder serves the
   * listing page (base "../") and a day page (base "../../"). */
  function teaserCard(item, base) {
    const v = item && typeof item === "object" ? item : {};
    const href = (base == null ? "" : String(base)) + "c/" + encodeURIComponent(v.id || "") + "/";

    const li = make("li", "dcard");
    const a = make("a", "dcard__link", li);
    a.href = href;

    thumb(a, v.th, v.t, "dcard__thumb");

    const body = make("div", "dcard__body", a);

    const badges = make("div", "dcard__badges", body);
    const badge = make("span", "badge badge--deep", badges);
    text(badge, T.section);

    const h3 = make("h3", "dcard__title", body);
    text(h3, v.t);

    const meta = make("div", "dcard__meta", body);
    text(meta, metaLine(v));

    if (isNonEmptyString(v.lead)) {
      const lead = make("p", "dcard__lead", body);
      text(lead, v.lead);
    }

    const cta = make("span", "dcard__cta", body);
    text(cta, T.readOn);

    return li;
  }

  function cardList(items, base, cls) {
    const ul = make("ul", "dcards" + (cls ? " " + cls : ""));
    const list = Array.isArray(items) ? items : [];
    for (let i = 0; i < list.length; i++) {
      try {
        ul.appendChild(teaserCard(list[i], base));
      } catch (e) {
        // Drop a malformed entry rather than losing the whole section.
      }
    }
    return ul;
  }

  /* Section for a day page. Returns null when the day has none, so the caller can append
   * unconditionally without leaving an empty heading behind. */
  function daySection(items, base) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) return null;
    const sec = make("section", "deepteaser");
    const h2 = make("h2", "deepteaser__title", sec);
    text(h2, T.section);
    const count = make("span", "deepteaser__count", h2);
    text(count, "(" + list.length + ")");
    sec.appendChild(cardList(list, base, "deepteaser__list"));
    return sec;
  }

  /* ---------- listing page ---------- */

  function renderIndex(app, data, config) {
    const payload = data && typeof data === "object" ? data : {};
    const items = Array.isArray(payload.items) ? payload.items : [];
    const base = (config && config.base) || "../";

    const head = make("header", "deeplist__head", app);
    const h1 = make("h1", "deeplist__title", head);
    text(h1, T.section);
    const count = make("p", "deeplist__count", head);
    text(count, items.length === 1 ? T.countOne : items.length + T.countMany);

    if (!items.length) {
      const empty = make("p", "deeplist__empty", app);
      text(empty, T.empty);
      return;
    }
    const wrap = make("div", "dcards-wrap", app);
    wrap.appendChild(cardList(items, base, "deeplist__items"));
  }

  /* ---------- article page ---------- */

  function buildBody(parent, blocks) {
    const list = Array.isArray(blocks) ? blocks : [];
    const headings = [];
    let currentList = null;
    let index = 0;

    for (let i = 0; i < list.length; i++) {
      const b = list[i];
      if (!b || typeof b !== "object") continue;
      const kind = typeof b.k === "string" ? b.k : "";
      const runs = Array.isArray(b.r) ? b.r : [];

      if (kind === "b") {
        if (!currentList) currentList = make("ul", "deep__list", parent);
        appendRuns(make("li", "deep__li", currentList), runs);
        continue;
      }
      currentList = null;
      if (kind === "h") {
        index += 1;
        const h = make("h2", "deep__h", parent);
        // Anchors are positional and ASCII, matching the ids the build put in `toc`.
        h.id = "s" + index;
        appendRuns(h, runs);
        headings.push(h);
      } else {
        appendRuns(make("p", "deep__p", parent), runs);
      }
    }
    return headings;
  }

  function buildToc(parent, toc, headings) {
    const entries = Array.isArray(toc) ? toc : [];
    if (entries.length < 2) return null;

    const nav = make("nav", "deep__toc", parent);
    nav.setAttribute("aria-label", T.toc);
    const title = make("p", "deep__toc-title", nav);
    text(title, T.toc);
    const ul = make("ul", "deep__toc-list", nav);

    const links = [];
    for (let i = 0; i < entries.length; i++) {
      const entry = entries[i] && typeof entries[i] === "object" ? entries[i] : {};
      const anchor = isNonEmptyString(entry.a) ? entry.a : "s" + (i + 1);
      const li = make("li", "deep__toc-item", ul);
      const a = make("a", "deep__toc-link", li);
      a.href = "#" + anchor;
      text(a, entry.l);
      links.push(a);
    }

    watchHeadings(headings, links);
    return nav;
  }

  /* Highlight the table-of-contents entry for whatever section is on screen. Guarded:
   * IntersectionObserver is the only browser API here that could be missing, and losing
   * the highlight must not cost the reader the article. */
  function watchHeadings(headings, links) {
    if (!headings.length || !links.length) return;
    if (typeof window.IntersectionObserver !== "function") return;

    const visible = new Set();
    const observer = new IntersectionObserver(
      function (entries) {
        for (let i = 0; i < entries.length; i++) {
          const id = entries[i].target.id;
          if (entries[i].isIntersecting) visible.add(id);
          else visible.delete(id);
        }
        let activeIndex = -1;
        for (let i = 0; i < headings.length; i++) {
          if (visible.has(headings[i].id)) {
            activeIndex = i;
            break;
          }
        }
        for (let i = 0; i < links.length; i++) {
          links[i].classList.toggle("deep__toc-link--active", i === activeIndex);
        }
      },
      // Top margin clears the sticky topbar so a heading counts as "current" only once
      // it is genuinely in the reading area, not while hidden behind the bar.
      { rootMargin: "-96px 0px -55% 0px", threshold: 0 }
    );
    for (let i = 0; i < headings.length; i++) observer.observe(headings[i]);
  }

  /* Publish the sticky topbar's real height so an anchor jump can clear it.
   *
   * A fixed `scroll-margin` cannot work here: the bar wraps its nav onto extra rows as the
   * viewport narrows, so it is about 60px on a desktop and 115px on a phone. With the
   * margin hard-coded at 5rem/80px, tapping a table-of-contents entry on a phone landed
   * the heading at 80px — underneath a bar whose bottom edge is at 115px — so the section
   * you asked for was the one thing you could not see. Measured here and consumed by CSS
   * through `--nv-topbar-h`. */
  function trackTopbarHeight() {
    const root = document.documentElement;

    function update() {
      const bar = document.querySelector(".topbar");
      const height = bar ? Math.round(bar.getBoundingClientRect().height) : 0;
      if (height > 0) root.style.setProperty("--nv-topbar-h", height + "px");
    }

    update();
    window.addEventListener("resize", update, { passive: true });
    // The bar's height changes when its own content does — the saved-count chip and the
    // "forget this device" button appear after the unlock, one render later.
    if (typeof window.ResizeObserver === "function") {
      const bar = document.querySelector(".topbar");
      if (bar) new window.ResizeObserver(update).observe(bar);
    }
  }

  /* Reading progress across the article body only: measuring the whole document would
   * count the header and footer, so the bar would never reach either end. */
  function mountProgress(parent, article) {
    const track = make("div", "deep__progress", parent);
    const bar = make("div", "deep__progress-bar", track);
    track.setAttribute("role", "presentation");

    let ticking = false;
    function update() {
      ticking = false;
      const rect = article.getBoundingClientRect();
      const viewport = window.innerHeight || document.documentElement.clientHeight || 0;
      // Distance the article top travels from "just below the fold" to "fully read".
      const span = rect.height - viewport;
      let ratio;
      if (span <= 0) {
        ratio = rect.bottom <= viewport ? 1 : 0;
      } else {
        ratio = -rect.top / span;
      }
      if (!isFinite(ratio) || ratio < 0) ratio = 0;
      if (ratio > 1) ratio = 1;
      bar.style.width = (ratio * 100).toFixed(1) + "%";
    }
    function onScroll() {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(update);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    update();
    return track;
  }

  function renderArticle(app, data, config) {
    const payload = data && typeof data === "object" ? data : {};
    const base = (config && config.base) || "../../";

    const article = make("article", "deep", app);

    const header = make("header", "deep__header", article);
    const badges = make("div", "deep__badges", header);
    const badge = make("span", "badge badge--deep", badges);
    text(badge, T.section);

    const h1 = make("h1", "deep__title", header);
    text(h1, payload.t);

    const meta = make("p", "deep__meta", header);
    const parts = [];
    if (isNonEmptyString(payload.c)) parts.push(payload.c);
    const when = formatDate(payload.p);
    if (when) parts.push(when);
    const minutes = Number(payload.m);
    if (minutes > 0) parts.push(minutes + " " + T.minutes);
    const words = Number(payload.w);
    if (words > 0) parts.push(words + " " + T.words);
    text(meta, parts.join(" · "));

    const media = make("div", "deep__media", header);
    thumb(media, payload.th, payload.t, "deep__thumb");
    if (isNonEmptyString(payload.u)) {
      const watch = make("a", "deep__watch", media);
      watch.href = payload.u;
      watch.target = "_blank";
      watch.rel = "noopener noreferrer";
      text(watch, T.watch);
    }

    const layout = make("div", "deep__layout", article);
    const bodyWrap = make("div", "deep__body", layout);
    const headings = buildBody(bodyWrap, payload.bl);
    // The table of contents is built after the body so it can observe real headings, but
    // inserted before it so that source order matches reading order for a screen reader.
    const toc = buildToc(layout, payload.toc, headings);
    if (toc) layout.insertBefore(toc, bodyWrap);

    const foot = make("footer", "deep__foot", article);
    const back = make("a", "deep__back", foot);
    back.href = base + "c/";
    text(back, T.back);

    trackTopbarHeight();
    mountProgress(article, article);
  }

  window.NV.curated = {
    teaserCard: teaserCard,
    cardList: cardList,
    daySection: daySection,
    renderIndex: renderIndex,
    renderArticle: renderArticle,
    formatDate: formatDate,
    runsText: runsText,
    buildBody: buildBody
  };
})();
