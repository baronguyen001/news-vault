/* Important and trending posts from X.
 *
 * A card here is not a news card. What the reader has to weigh first is *who said it*:
 * the same sentence from a central bank and from an anonymous account with 40k likes are
 * different facts, and only one of them is reportable. So the author, their tier and a
 * "nguồn gốc" mark lead the card, and engagement counts sit last, deliberately quiet.
 *
 * Class names are NOT shared with the article/video card system (.cards, .card__*).
 * A shared presentational class plus a global selector is what once made `$("#app .cards")`
 * match the video list instead of the article list and blank out a whole day page.
 * `.xposts` / `.xpost__*` keep this section addressable on its own terms.
 *
 * Everything reaching the DOM does so as a text node. Titles and summaries here were
 * written by a language model from text a stranger wrote; treating either as markup is
 * how a day page becomes an injection surface.
 */
(function () {
  "use strict";

  if (!window.NV) window.NV = {};

  const T = {
    sectionTitle: "Tin nóng từ X",
    primary: "nguồn gốc",
    unverified: "chưa kiểm chứng",
    tierHigh: "nguồn chính thức",
    tierMid: "nguồn tin cậy",
    tierLow: "chưa xác thực",
    open: "Xem bài gốc",
    points: "Ý chính"
  };

  const IMPACT_MARK = { "cao": "🔴", "trung bình": "🟡", "thấp": "⚪" };

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
      const parsed = new URL(url);
      if (parsed.protocol !== "https:") return null;
    } catch (e) {
      return null;
    }
    return url;
  }

  function appendRuns(parent, runs) {
    if (!Array.isArray(runs)) return;
    for (let i = 0; i < runs.length; i++) {
      const run = runs[i];
      if (!Array.isArray(run) || typeof run[0] !== "string" || run[0] === "") continue;
      if (run[1]) {
        const strong = make("strong", "", parent);
        text(strong, run[0]);
      } else {
        parent.appendChild(document.createTextNode(run[0]));
      }
    }
  }

  function blocksInto(parent, blocks) {
    if (!Array.isArray(blocks)) return;
    let list = null;
    for (let i = 0; i < blocks.length; i++) {
      const block = blocks[i];
      if (!block || typeof block !== "object") continue;
      if (block.k === "b") {
        if (!list) list = make("ul", "xpost__bullets", parent);
        appendRuns(make("li", "", list), block.r);
        continue;
      }
      list = null;
      const el = make(block.k === "h" ? "h4" : "p", "xpost__" + (block.k === "h" ? "h" : "p"), parent);
      appendRuns(el, block.r);
    }
  }

  /* A number the reader can act on: 0.85 means "a wire or a named reporter", 0.2 means
   * "someone anonymous who is often early and sometimes wrong". Three bands is as much
   * precision as a badge can carry honestly. */
  function tierLabel(tier) {
    const value = typeof tier === "number" ? tier : 0.35;
    if (value >= 0.85) return { label: T.tierHigh, cls: "xpost__tier--high" };
    if (value >= 0.5) return { label: T.tierMid, cls: "xpost__tier--mid" };
    return { label: T.tierLow, cls: "xpost__tier--low" };
  }

  function compact(n) {
    const value = typeof n === "number" && isFinite(n) ? n : 0;
    if (value >= 1000000) return (value / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
    if (value >= 1000) return (value / 1000).toFixed(1).replace(/\.0$/, "") + "K";
    return "" + value;
  }

  function card(post) {
    const p = post && typeof post === "object" ? post : {};
    const li = make("li", "xpost");

    const topics = window.NV.topics;
    const topicClass = topics && typeof p.tp === "string" ? topics.className(p.tp) : "";
    if (topicClass) li.classList.add(topicClass);

    const header = make("div", "xpost__header", li);

    const author = make("span", "xpost__author", header);
    text(author, "@" + (typeof p.au === "string" ? p.au : ""));

    if (typeof p.an === "string" && p.an !== "") {
      const display = make("span", "xpost__name", header);
      text(display, p.an);
    }

    const tier = tierLabel(p.tr);
    const tierBadge = make("span", "xpost__tier " + tier.cls, header);
    text(tierBadge, p.pr ? T.primary : tier.label);

    if (typeof p.vl === "string" && p.vl !== "") {
      const vertical = make("span", "xpost__vertical", header);
      text(vertical, p.vl);
    }

    const impact = IMPACT_MARK[p.im];
    if (impact) {
      const mark = make("span", "xpost__impact", header);
      text(mark, impact);
      mark.title = String(p.im);
    }

    const title = make("h3", "xpost__title", li);
    text(title, p.t);

    const body = make("div", "xpost__body", li);
    blocksInto(body, p.bl);

    if (Array.isArray(p.kp) && p.kp.length) {
      const points = make("ul", "xpost__points", li);
      for (let i = 0; i < p.kp.length; i++) {
        if (typeof p.kp[i] !== "string" || p.kp[i] === "") continue;
        text(make("li", "", points), p.kp[i]);
      }
      if (!points.childNodes.length && points.parentNode) {
        points.parentNode.removeChild(points);
      }
    }

    const footer = make("div", "xpost__footer", li);
    const metrics = make("span", "xpost__metrics", footer);
    text(metrics, "♥ " + compact(p.lk) + " · ↺ " + compact(p.rt));

    const href = validHttpsUrl(p.u);
    if (href) {
      const link = make("a", "xpost__link", footer);
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
    const sec = make("section", "xposts");
    const h2 = make("h2", "xposts__title", sec);
    text(h2, T.sectionTitle);
    const count = make("span", "xposts__count", h2);
    text(count, "(" + list.length + ")");
    const ul = make("ul", "xposts__list", sec);
    for (let i = 0; i < list.length; i++) {
      try {
        ul.appendChild(card(list[i]));
      } catch (e) {
        // Drop a malformed entry rather than losing the section.
      }
    }
    return sec;
  }

  window.NV.posts = {
    card: card,
    section: section,
    tierLabel: tierLabel
  };
})();
