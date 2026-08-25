/* Substack essays ("Từ Substack").
 *
 * A row here is a full essay from a followed Substack author, summarised with the same
 * emoji-led heading style as a curated deep dive — so this reading page mirrors curated.js
 * almost exactly (own table of contents, own progress bar, own measured text column). What
 * is different is the source, so it keeps its own class names rather than sharing curated's:
 * `.scard` / `.sub__*` / `.subteaser` are addressable on their own terms, same reasoning
 * curated.js documents for keeping `.dcard` / `.deep__*` off the shared `.cards` system.
 */
(function () {
  "use strict";

  if (!window.NV) window.NV = {};

  const T = {
    section: "Từ Substack",
    toc: "Nội dung bài",
    minutes: "phút đọc",
    words: "từ",
    read: "Đọc trên Substack",
    back: "Về danh sách bài Substack",
    backShort: "Danh sách",
    empty: "Chưa có bài Substack nào.",
    countOne: "1 bài",
    countMany: " bài",
    readOn: "Đọc bài",
    search: "Tìm theo tiêu đề hoặc tác giả…",
    allAuthors: "Tất cả tác giả",
    sortNewest: "Mới nhất",
    sortOldest: "Cũ nhất",
    sortAuthor: "Theo tác giả A–Z",
    noResults: "Không có bài phù hợp với bộ lọc.",
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

  function validHttpsUrl(url) {
    if (!isNonEmptyString(url)) return null;
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== "https:") return null;
    } catch (e) {
      return null;
    }
    return url;
  }

  /* Not every essay has a cover: og:image is often absent for a text-only Substack post,
   * so this returns null (rendering nothing) rather than a broken-image box. */
  function thumb(parent, url, alt) {
    const src = validHttpsUrl(url);
    if (!src) return null;
    const img = make("img", "scard__thumb", parent);
    img.src = src;
    img.loading = "lazy";
    img.decoding = "async";
    img.referrerPolicy = "no-referrer";
    img.alt = alt == null ? "" : String(alt);
    img.onerror = function () {
      if (img.parentNode) img.parentNode.removeChild(img);
    };
    return img;
  }

  function two(n) {
    return n < 10 ? "0" + n : "" + n;
  }

  /* Same diacritic-insensitive fold video-library.js uses, so "kinh te" finds "kinh tế". */
  function folded(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/đ/g, "d");
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
    const href = (base == null ? "" : String(base)) + "sub/" + encodeURIComponent(v.id || "") + "/";

    const li = make("li", "scard");
    const a = make("a", "scard__link", li);
    a.href = href;

    thumb(a, v.img, v.t);

    const body = make("div", "scard__body", a);

    const badges = make("div", "scard__badges", body);
    const badge = make("span", "badge badge--sub", badges);
    text(badge, T.section);

    const h3 = make("h3", "scard__title", body);
    text(h3, v.t);

    const meta = make("div", "scard__meta", body);
    text(meta, metaLine(v));

    if (isNonEmptyString(v.lead)) {
      const lead = make("p", "scard__lead", body);
      text(lead, v.lead);
    }

    const cta = make("span", "scard__cta", body);
    text(cta, T.readOn);

    return li;
  }

  function cardList(items, base, cls) {
    const ul = make("ul", "scards" + (cls ? " " + cls : ""));
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
    const sec = make("section", "subteaser");
    const h2 = make("h2", "subteaser__title", sec);
    text(h2, T.section);
    const count = make("span", "subteaser__count", h2);
    text(count, "(" + list.length + ")");
    sec.appendChild(cardList(list, base, "subteaser__list"));
    return sec;
  }

  /* ---------- listing page ---------- */

  function renderIndex(app, data, config) {
    const payload = data && typeof data === "object" ? data : {};
    const items = Array.isArray(payload.items) ? payload.items : [];
    const base = (config && config.base) || "../";

    const head = make("header", "sublist__head", app);
    const h1 = make("h1", "sublist__title", head);
    text(h1, T.section);
    const count = make("p", "sublist__count", head);
    text(count, items.length === 1 ? T.countOne : items.length + T.countMany);

    if (!items.length) {
      const empty = make("p", "sublist__empty", app);
      text(empty, T.empty);
      return;
    }

    const state = { query: "", author: "", sort: "newest" };

    const controls = make("section", "sublist__controls", app);
    controls.setAttribute("aria-label", "Lọc bài Substack");
    const input = make("input", "sublist__search", controls);
    input.type = "search";
    input.placeholder = T.search;
    input.setAttribute("aria-label", T.search);

    const authorSelect = make("select", "sublist__select", controls);
    authorSelect.setAttribute("aria-label", T.allAuthors);
    const allOption = make("option", "", authorSelect);
    allOption.value = "";
    text(allOption, T.allAuthors);
    const authors = Array.from(new Set(items.map((item) => item && item.c).filter(isNonEmptyString)))
      .sort((a, b) => a.localeCompare(b, "vi"));
    for (let i = 0; i < authors.length; i++) {
      const option = make("option", "", authorSelect);
      option.value = authors[i];
      text(option, authors[i]);
    }

    const sortSelect = make("select", "sublist__select", controls);
    sortSelect.setAttribute("aria-label", "Sắp xếp");
    [["newest", T.sortNewest], ["oldest", T.sortOldest], ["author", T.sortAuthor]].forEach(
      ([value, label]) => {
        const option = make("option", "", sortSelect);
        option.value = value;
        text(option, label);
      }
    );

    const clear = make("button", "sublist__clear", controls);
    clear.type = "button";
    text(clear, T.clear);

    const wrap = make("div", "scards-wrap", app);
    const shownCount = make("p", "sublist__shown", wrap);
    shownCount.setAttribute("aria-live", "polite");
    const list = make("ul", "scards sublist__items", wrap);
    const empty = make("p", "sublist__noresults", wrap);
    text(empty, T.noResults);
    empty.hidden = true;

    function matches(item) {
      if (state.author && item.c !== state.author) return false;
      if (!state.query) return true;
      const haystack = folded([item.t, item.c, item.lead].filter(isNonEmptyString).join(" "));
      return haystack.indexOf(folded(state.query)) !== -1;
    }

    function sorted(list) {
      return list.sort((a, b) => {
        if (state.sort === "author") {
          return String(a.c || "").localeCompare(String(b.c || ""), "vi") ||
            String(b.p || "").localeCompare(String(a.p || ""));
        }
        const direction = state.sort === "oldest" ? 1 : -1;
        return direction * String(a.p || "").localeCompare(String(b.p || ""));
      });
    }

    function paint() {
      const shown = sorted(items.filter(matches));
      text(shownCount, shown.length === 1 ? T.countOne : shown.length + T.countMany);
      text(list, "");
      for (let i = 0; i < shown.length; i++) {
        try {
          list.appendChild(teaserCard(shown[i], base));
        } catch (e) {
          // Drop a malformed entry rather than losing the whole page.
        }
      }
      empty.hidden = shown.length !== 0;
    }

    input.addEventListener("input", () => {
      state.query = input.value.trim();
      paint();
    });
    authorSelect.addEventListener("change", () => {
      state.author = authorSelect.value;
      paint();
    });
    sortSelect.addEventListener("change", () => {
      state.sort = sortSelect.value;
      paint();
    });
    clear.addEventListener("click", () => {
      state.query = "";
      state.author = "";
      state.sort = "newest";
      input.value = "";
      authorSelect.value = "";
      sortSelect.value = "newest";
      paint();
    });

    paint();
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
        if (!currentList) currentList = make("ul", "sub__list", parent);
        appendRuns(make("li", "sub__li", currentList), runs);
        continue;
      }
      currentList = null;
      if (kind === "h") {
        index += 1;
        const h = make("h2", "sub__h", parent);
        // Anchors are positional and ASCII, matching the ids the build put in `toc`.
        h.id = "s" + index;
        appendRuns(h, runs);
        headings.push(h);
      } else {
        appendRuns(make("p", "sub__p", parent), runs);
      }
    }
    return headings;
  }

  function buildToc(parent, toc, headings) {
    const entries = Array.isArray(toc) ? toc : [];
    if (entries.length < 2) return null;

    const nav = make("nav", "sub__toc", parent);
    nav.setAttribute("aria-label", T.toc);
    const title = make("p", "sub__toc-title", nav);
    text(title, T.toc);
    const ul = make("ul", "sub__toc-list", nav);

    const links = [];
    for (let i = 0; i < entries.length; i++) {
      const entry = entries[i] && typeof entries[i] === "object" ? entries[i] : {};
      const anchor = isNonEmptyString(entry.a) ? entry.a : "s" + (i + 1);
      const li = make("li", "sub__toc-item", ul);
      const a = make("a", "sub__toc-link", li);
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
          links[i].classList.toggle("sub__toc-link--active", i === activeIndex);
        }
      },
      // Top margin clears the sticky topbar so a heading counts as "current" only once
      // it is genuinely in the reading area, not while hidden behind the bar.
      { rootMargin: "-96px 0px -55% 0px", threshold: 0 }
    );
    for (let i = 0; i < headings.length; i++) observer.observe(headings[i]);
  }

  /* Publish the sticky topbar's real height so an anchor jump can clear it. Same fix as
   * curated.js's `trackTopbarHeight` and for the same reason: a fixed `scroll-margin`
   * cannot track the bar's height as it wraps onto extra rows on a phone. Consumed by CSS
   * through the shared `--nv-topbar-h` variable curated.js already maintains. */
  function trackTopbarHeight() {
    const root = document.documentElement;

    function update() {
      const bar = document.querySelector(".topbar");
      const height = bar ? Math.round(bar.getBoundingClientRect().height) : 0;
      if (height > 0) root.style.setProperty("--nv-topbar-h", height + "px");
    }

    update();
    window.addEventListener("resize", update, { passive: true });
    if (typeof window.ResizeObserver === "function") {
      const bar = document.querySelector(".topbar");
      if (bar) new window.ResizeObserver(update).observe(bar);
    }
  }

  /* Reading progress across the article body only. */
  function mountProgress(parent, article) {
    const track = make("div", "sub__progress", parent);
    const bar = make("div", "sub__progress-bar", track);
    track.setAttribute("role", "presentation");

    let ticking = false;
    function update() {
      ticking = false;
      const rect = article.getBoundingClientRect();
      const viewport = window.innerHeight || document.documentElement.clientHeight || 0;
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

    const article = make("article", "sub", app);

    const header = make("header", "sub__header", article);
    const badges = make("div", "sub__badges", header);
    const badge = make("span", "badge badge--sub", badges);
    text(badge, T.section);

    const h1 = make("h1", "sub__title", header);
    text(h1, payload.t);

    const meta = make("p", "sub__meta", header);
    const parts = [];
    if (isNonEmptyString(payload.c)) parts.push(payload.c);
    const when = formatDate(payload.p);
    if (when) parts.push(when);
    const minutes = Number(payload.m);
    if (minutes > 0) parts.push(minutes + " " + T.minutes);
    const words = Number(payload.w);
    if (words > 0) parts.push(words + " " + T.words);
    text(meta, parts.join(" · "));

    if (isNonEmptyString(payload.u)) {
      const media = make("div", "sub__media", header);
      const read = make("a", "sub__read", media);
      read.href = payload.u;
      read.target = "_blank";
      read.rel = "noopener noreferrer";
      text(read, T.read);
    }

    const heroSrc = validHttpsUrl(payload.img);
    if (heroSrc) {
      const hero = make("img", "sub__hero", article);
      hero.src = heroSrc;
      hero.loading = "lazy";
      hero.decoding = "async";
      hero.referrerPolicy = "no-referrer";
      hero.alt = isNonEmptyString(payload.t) ? payload.t : "";
      hero.onerror = function () {
        if (hero.parentNode) hero.parentNode.removeChild(hero);
      };
    }

    const layout = make("div", "sub__layout", article);
    const bodyWrap = make("div", "sub__body", layout);
    const headings = buildBody(bodyWrap, payload.bl);
    // The table of contents is built after the body so it can observe real headings, but
    // inserted before it so that source order matches reading order for a screen reader.
    const toc = buildToc(layout, payload.toc, headings);
    if (toc) layout.insertBefore(toc, bodyWrap);

    const foot = make("footer", "sub__foot", article);
    const back = make("a", "sub__back", foot);
    back.href = base + "sub/";
    text(back, T.back);

    trackTopbarHeight();
    mountProgress(article, article);
  }

  window.NV.substack = {
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
