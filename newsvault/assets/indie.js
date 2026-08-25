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
    open: "Xem bài gốc"
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

  window.NV.indie = {
    card: card,
    section: section
  };
})();
