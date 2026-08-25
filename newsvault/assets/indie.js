/* Build-in-public / indie-hacker posts, from a small hand-picked account list.
 *
 * Deliberately the simplest card in the archive: no tier, no vertical, no topic, no
 * impact analysis - `xpulse/indie.py` only decides keep-or-drop and translates, so there
 * is nothing else here to render. Own classes (`.iposts` / `.ipost__*`), same reasoning
 * posts.js documents for `.xposts`: a shared class plus a global selector is how one
 * section's fix once broke another's layout.
 */
(function () {
  "use strict";

  if (!window.NV) window.NV = {};

  const T = {
    sectionTitle: "Indie Hacker",
    open: "Xem bài gốc",
    listTitle: "Indie Hacker",
    search: "Tìm theo nội dung hoặc tác giả…",
    allAuthors: "Tất cả tác giả",
    sortNewest: "Mới nhất",
    sortOldest: "Cũ nhất",
    sortAuthor: "Theo tác giả A–Z",
    noResults: "Không có bài phù hợp với bộ lọc.",
    clear: "Xóa bộ lọc",
    empty: "Chưa có bài Indie Hacker nào.",
    countOne: "1 bài",
    countMany: " bài"
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

  /* Same diacritic-insensitive fold substack.js/reports.js/video-library.js use. */
  function folded(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/đ/g, "d");
  }

  function validHttpsUrl(url) {
    if (!url) return null;
    try {
      if (new URL(url).protocol !== "https:") return null;
    } catch (e) {
      return null;
    }
    return url;
  }

  function compact(n) {
    const value = typeof n === "number" && isFinite(n) ? n : 0;
    if (value >= 1000000) return (value / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
    if (value >= 1000) return (value / 1000).toFixed(1).replace(/\.0$/, "") + "K";
    return "" + value;
  }

  function card(post, index) {
    const p = post && typeof post === "object" ? post : {};
    const li = make("li", "ipost");
    if (index >= 0) li.id = "i-" + index;

    const header = make("div", "ipost__header", li);
    const author = make("span", "ipost__author", header);
    text(author, "@" + (typeof p.au === "string" ? p.au : ""));
    if (typeof p.an === "string" && p.an !== "") {
      const name = make("span", "ipost__name", header);
      text(name, p.an);
    }

    const body = make("p", "ipost__body", li);
    text(body, p.vi);

    const footer = make("div", "ipost__footer", li);
    const metrics = make("span", "ipost__metrics", footer);
    text(metrics, "♥ " + compact(p.lk) + " · ↺ " + compact(p.rt));

    const href = validHttpsUrl(p.u);
    if (href) {
      const link = make("a", "ipost__link", footer);
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      text(link, T.open);
    }

    return li;
  }

  function section(posts) {
    const list = Array.isArray(posts) ? posts : [];
    if (!list.length) return null;
    const sec = make("section", "iposts");
    const h2 = make("h2", "iposts__title", sec);
    text(h2, T.sectionTitle);
    const count = make("span", "iposts__count", h2);
    text(count, "(" + list.length + ")");
    const ul = make("ul", "iposts__list", sec);
    for (let i = 0; i < list.length; i++) {
      try {
        ul.appendChild(card(list[i], i));
      } catch (e) {
        // Drop a malformed entry rather than losing the section.
      }
    }
    return sec;
  }

  /* ---------- listing page ---------- */

  function renderIndex(app, data, config) {
    const payload = data && typeof data === "object" ? data : {};
    const items = Array.isArray(payload.items) ? payload.items : [];

    const head = make("header", "ilist__head", app);
    const h1 = make("h1", "ilist__title", head);
    text(h1, T.listTitle);
    const count = make("p", "ilist__count", head);
    text(count, items.length === 1 ? T.countOne : items.length + T.countMany);

    if (!items.length) {
      const empty = make("p", "ilist__empty", app);
      text(empty, T.empty);
      return;
    }

    const state = { query: "", author: "", sort: "newest" };

    const controls = make("section", "ilist__controls", app);
    controls.setAttribute("aria-label", "Lọc bài Indie Hacker");
    const input = make("input", "ilist__search", controls);
    input.type = "search";
    input.placeholder = T.search;
    input.setAttribute("aria-label", T.search);

    const authorSelect = make("select", "ilist__select", controls);
    authorSelect.setAttribute("aria-label", T.allAuthors);
    const allOption = make("option", "", authorSelect);
    allOption.value = "";
    text(allOption, T.allAuthors);
    const authors = Array.from(new Set(items.map((item) => item && item.au).filter(isNonEmptyString)))
      .sort((a, b) => a.localeCompare(b, "vi"));
    for (let i = 0; i < authors.length; i++) {
      const option = make("option", "", authorSelect);
      option.value = authors[i];
      text(option, "@" + authors[i]);
    }

    const sortSelect = make("select", "ilist__select", controls);
    sortSelect.setAttribute("aria-label", "Sắp xếp");
    [["newest", T.sortNewest], ["oldest", T.sortOldest], ["author", T.sortAuthor]].forEach(
      ([value, label]) => {
        const option = make("option", "", sortSelect);
        option.value = value;
        text(option, label);
      }
    );

    const clear = make("button", "ilist__clear", controls);
    clear.type = "button";
    text(clear, T.clear);

    const wrap = make("div", "ilist__wrap", app);
    const shownCount = make("p", "ilist__shown", wrap);
    shownCount.setAttribute("aria-live", "polite");
    const list = make("ul", "iposts__list ilist__items", wrap);
    const empty = make("p", "ilist__noresults", wrap);
    text(empty, T.noResults);
    empty.hidden = true;

    function matches(item) {
      if (state.author && item.au !== state.author) return false;
      if (!state.query) return true;
      const haystack = folded([item.vi, item.au, item.an].filter(isNonEmptyString).join(" "));
      return haystack.indexOf(folded(state.query)) !== -1;
    }

    function sorted(list) {
      return list.sort((a, b) => {
        if (state.sort === "author") {
          return String(a.au || "").localeCompare(String(b.au || ""), "vi") ||
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
          list.appendChild(card(shown[i], i));
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

  window.NV.indie = {
    card: card,
    section: section,
    renderIndex: renderIndex
  };
})();
