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
    details: "Xem chi tiết",
    points: "Ý chính",
    fold: "Xem tóm tắt",
    alsoBy: "cùng đưa tin:",
    impactLabel: "Tác động dự kiến — suy luận, không phải tin",
    confidence: "độ chắc chắn:"
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

  function card(post, index) {
    const p = post && typeof post === "object" ? post : {};
    const li = make("li", "xpost");
    if (index >= 0) li.id = "x-" + index;

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

    if (typeof p.tp === "string" && p.tp !== "") {
      const topic = make("span", "xpost__topic", header);
      text(topic, p.tp);
    }

    const impact = IMPACT_MARK[p.im];
    if (impact) {
      const mark = make("span", "xpost__impact", header);
      text(mark, impact);
      mark.title = String(p.im);
    }

    const title = make("h3", "xpost__title", li);
    text(title, p.t);

    if (Array.isArray(p.ab) && p.ab.length) {
      const names = [];
      for (let i = 0; i < p.ab.length && i < 3; i++) {
        if (typeof p.ab[i] === "string" && p.ab[i] !== "") {
          names.push("@" + p.ab[i].replace(/^@/, ""));
        }
      }
      if (names.length) {
        if (p.ab.length > 3) names.push("+" + (p.ab.length - 3));
        const also = make("p", "xpost__also", li);
        text(also, T.alsoBy + " " + names.join(", "));
      }
    }

    const imageUrl = validHttpsUrl(p.img);
    if (imageUrl) {
      const image = make("img", "xpost__image", li);
      image.src = imageUrl;
      image.loading = "lazy";
      image.decoding = "async";
      image.alt = typeof p.t === "string" ? p.t : "";
      image.onerror = function () {
        if (image.parentNode) image.parentNode.removeChild(image);
      };
    } else {
      li.classList.add("xpost--compact");
    }

    let bodyParent = li;
    if (!imageUrl) {
      const fold = make("details", "xpost__fold", li);
      const foldSummary = make("summary", "", fold);
      text(foldSummary, T.fold);
      bodyParent = fold;
    }
    const body = make("div", "xpost__body", bodyParent);
    blocksInto(body, p.bl);

    if (p.ia && typeof p.ia === "object") {
      const analysis = make("section", "xpost__impact", li);
      const label = make("p", "xpost__impact-label", analysis);
      text(label, T.impactLabel);

      if (typeof p.ia.ch === "string" && p.ia.ch !== "") {
        text(make("p", "xpost__impact-channel", analysis), p.ia.ch);
      }

      if (Array.isArray(p.ia.as) && p.ia.as.length) {
        const assets = make("div", "xpost__impact-assets", analysis);
        for (let i = 0; i < p.ia.as.length; i++) {
          if (typeof p.ia.as[i] !== "string" || p.ia.as[i] === "") continue;
          text(make("span", "xpost__impact-asset", assets), p.ia.as[i]);
        }
      }

      if (typeof p.ia.dir === "string" && p.ia.dir !== "") {
        const arrows = { "tăng": "▲", "giảm": "▼", "hai chiều": "⇅", "không rõ": "–" };
        const direction = make("p", "xpost__impact-direction", analysis);
        text(direction, (arrows[p.ia.dir] || "–") + " " + p.ia.dir);
      }

      if (typeof p.ia.cf === "string" && p.ia.cf !== "") {
        const confidence = make("p", "xpost__impact-confidence", analysis);
        text(confidence, T.confidence + " " + p.ia.cf);
      }

      if (typeof p.ia.why === "string" && p.ia.why !== "") {
        text(make("p", "xpost__impact-reasoning", analysis), p.ia.why);
      }
    }

    const hasPoints = Array.isArray(p.kp) && p.kp.some((point) => typeof point === "string" && point !== "");
    const hasInsight = typeof p.ins === "string" && p.ins !== "";
    if (hasPoints || hasInsight) {
      const details = make("details", "xpost__details", li);
      const summary = make("summary", "xpost__details-toggle", details);
      text(summary, T.details);
      if (hasInsight) {
        const insight = make("p", "xpost__insight", details);
        text(insight, p.ins);
      }
      const points = make("ul", "xpost__points", details);
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
    const filters = make("div", "xposts__filters", sec);
    filters.setAttribute("aria-label", "Lọc tin X");
    const ul = make("ul", "xposts__list", sec);
    const cards = [];
    for (let i = 0; i < list.length; i++) {
      try {
        const item = card(list[i], i);
        ul.appendChild(item);
        cards.push({ item: item, post: list[i] || {} });
      } catch (e) {
        // Drop a malformed entry rather than losing the section.
      }
    }
    const topics = Array.from(new Set(list.map((post) => post && post.tp).filter(Boolean))).slice(0, 6);
    const choices = [{ label: "Tất cả", match: () => true }]
      .concat(topics.map((topic) => ({ label: topic, match: (post) => post.tp === topic })))
      .concat([
        { label: "Nguồn gốc", match: (post) => !!post.pr },
        { label: "Tác động cao", match: (post) => post.im === "cao" },
      ]);
    for (let i = 0; i < choices.length; i++) {
      const choice = choices[i];
      const button = make("button", "xposts__filter", filters);
      button.type = "button";
      button.setAttribute("aria-pressed", i === 0 ? "true" : "false");
      text(button, choice.label);
      if (typeof button.addEventListener !== "function") continue;
      button.addEventListener("click", () => {
        const shown = cards.filter(({ item, post }) => {
          const keep = choice.match(post);
          item.hidden = !keep;
          return keep;
        }).length;
        for (const peer of filters.children) peer.setAttribute("aria-pressed", peer === button ? "true" : "false");
        text(count, "(" + shown + ")");
      });
    }
    return sec;
  }

  window.NV.posts = {
    card: card,
    section: section,
    tierLabel: tierLabel
  };
})();
