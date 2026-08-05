(function () {
  "use strict";

  if (!window.NV) window.NV = {};

  const T = {
    expand: "Xem thêm",
    collapse: "Thu gọn",
    youtube: "YouTube",
    sectionTitle: "Video YouTube",
    typeMap: {
      tech: "Công nghệ",
      finance: "Tài chính",
      tutorial: "Hướng dẫn",
      business: "Kinh doanh",
      other: "Khác"
    }
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

  function formatDateTime(iso) {
    if (!isNonEmptyString(iso)) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    return two(d.getHours()) + ":" + two(d.getMinutes()) + " " +
           two(d.getDate()) + "/" + two(d.getMonth() + 1) + "/" + d.getFullYear();
  }

  function appendRuns(parent, runs) {
    if (!Array.isArray(runs)) return;
    for (let i = 0; i < runs.length; i++) {
      const run = runs[i];
      if (!Array.isArray(run) || run.length < 1) continue;
      const runText = run[0];
      const bold = !!run[1];
      if (bold) {
        const strong = make("strong");
        text(strong, runText);
        parent.appendChild(strong);
      } else {
        parent.appendChild(document.createTextNode(runText == null ? "" : String(runText)));
      }
    }
  }

  function setOpen(card, open) {
    if (!card || card.nodeType !== 1) return;
    const body = card.querySelector(".card__body");
    const btn = card.querySelector(".card__more");
    card.classList.toggle("card--closed", !open);
    if (body) body.hidden = !open;
    if (btn) {
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      text(btn, open ? T.collapse : T.expand);
    }
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

  function thumb(parent, url, alt, cls, fallbackUrl) {
    const primary = validHttpsUrl(url);
    if (!primary) return null;

    const fallback = validHttpsUrl(fallbackUrl);
    const wrapper = make("div", "card__thumb" + (cls ? " " + cls : ""), parent);
    const img = make("img", "", wrapper);
    img.src = primary;
    img.loading = "lazy";
    img.decoding = "async";
    img.referrerPolicy = "no-referrer";
    img.alt = alt == null ? "" : String(alt);

    let retried = false;
    img.onerror = function () {
      if (!retried && fallback) {
        retried = true;
        img.src = fallback;
        return;
      }
      if (wrapper && wrapper.parentNode) {
        wrapper.parentNode.removeChild(wrapper);
      }
    };
    return wrapper;
  }

  function card(video) {
    const v = video && typeof video === "object" ? video : {};
    const li = make("li", "card card--video card--closed");
    if (v.sh) li.classList.add("card--short");

    const header = make("div", "card__header", li);
    const typeKey = typeof v.ty === "string" ? v.ty : "";
    if (typeKey && T.typeMap[typeKey]) {
      // Same colour scheme as an article's topic, keyed off the Vietnamese label rather
      // than the raw type so "tech" and "Công nghệ/AI" land on one hue.
      const label = T.typeMap[typeKey];
      const topics = window.NV.topics;
      const topicClass = topics ? topics.className(label) : "";
      if (topicClass) li.classList.add(topicClass);
      const typeBadge = make("span", "badge badge--topic", header);
      text(typeBadge, label);
    }
    if (v.sh) {
      const shortBadge = make("span", "badge badge--short", header);
      text(shortBadge, "Short");
    }
    const ytBadge = make("span", "badge badge--video", header);
    text(ytBadge, T.youtube);

    const lead = make("div", "card__lead", li);
    thumb(lead, v.th, v.t, "", v.thf);

    const textWrap = make("div", "", lead);

    const h3 = make("h3", "card__title", textWrap);
    const link = make("a", "card__link", h3);
    if (isNonEmptyString(v.u)) {
      link.href = v.u;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
    text(link, v.t);

    const metaParts = [];
    if (isNonEmptyString(v.c)) metaParts.push(v.c);
    const when = formatDateTime(v.p);
    if (when) metaParts.push(when);
    if (metaParts.length) {
      const meta = make("div", "card__meta", textWrap);
      text(meta, metaParts.join(" · "));
    }

    const body = make("div", "card__body", li);
    body.hidden = true;

    const blocks = Array.isArray(v.bl) ? v.bl : [];
    let currentList = null;

    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      if (!b || typeof b !== "object") continue;
      const k = typeof b.k === "string" ? b.k : "";
      const runs = Array.isArray(b.r) ? b.r : [];

      if (k === "b") {
        if (!currentList) {
          currentList = make("ul", "vsum__list", body);
        }
        const item = make("li", "", currentList);
        appendRuns(item, runs);
      } else {
        currentList = null;
        if (k === "h") {
          const h = make("h4", "vsum__h", body);
          appendRuns(h, runs);
        } else {
          const p = make("p", "vsum__p", body);
          appendRuns(p, runs);
        }
      }
    }

    const foot = make("div", "card__foot", li);
    const more = make("button", "card__more", foot);
    more.type = "button";
    more.setAttribute("aria-expanded", "false");
    text(more, T.expand);
    more.addEventListener("click", function () {
      const opening = li.classList.contains("card--closed");
      setOpen(li, opening);
    });

    return li;
  }

  function section(videos) {
    const list = Array.isArray(videos) ? videos : [];
    if (!list.length) return null;
    const sec = make("section", "videos");
    const h2 = make("h2", "videos__title", sec);
    text(h2, T.sectionTitle);
    const count = make("span", "videos__count", h2);
    text(count, "(" + list.length + ")");
    const ul = make("ul", "cards videos__list", sec);
    for (let i = 0; i < list.length; i++) {
      try {
        ul.appendChild(card(list[i]));
      } catch (e) {
        // Drop malformed entries instead of breaking the whole page.
      }
    }
    return sec;
  }

  window.NV.videos = {
    thumb: thumb,
    card: card,
    section: section,
    setOpen: setOpen
  };
})();
