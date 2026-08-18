(function () {
  "use strict";

  if (!window.NV) window.NV = {};

  const T = {
    title: "Tìm kiếm kho tin",
    placeholder: "Tìm tiêu đề, nguồn, chủ đề hoặc dùng cú pháp tìm kiếm",
    clear: "Xoá",
    filters: "Bộ lọc",
    type: "Loại nội dung",
    topic: "Chủ đề",
    source: "Nguồn",
    sourceFind: "Lọc nguồn",
    impact: "Mức tác động",
    tier: "Trả phí / Miễn phí",
    date: "Khoảng ngày",
    from: "Từ ngày",
    to: "Đến ngày",
    score: "Điểm tối thiểu",
    sort: "Sắp xếp",
    relevant: "Liên quan nhất",
    newest: "Mới nhất",
    oldest: "Cũ nhất",
    highest: "Điểm cao nhất",
    all: "Tìm toàn kho",
    loading: "Đang nạp chỉ mục…",
    more: "Xem thêm",
    none: "Không có kết quả phù hợp.",
    reset: "Xoá hết bộ lọc",
    shortcuts: "Phím tắt: / để tìm · Esc để xoá · ↑ ↓ để chọn · Enter để mở",
    paid: "Trả phí",
    article: "Bài báo",
    post: "Bài X",
    video: "Video",
    curated: "Phân tích"
  };

  function make(tag, cls, parent) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (parent) parent.appendChild(el);
    return el;
  }

  function text(el, value) {
    el.textContent = value == null ? "" : String(value);
  }

  function values(params, key) {
    const value = params.get(key);
    return new Set(value ? value.split(",").filter(Boolean) : []);
  }

  function kindLabel(item) {
    if (item.k === "x") return T.post;
    if (item.k === "v") return T.video;
    if (item.k === "c") return T.curated;
    return T.article;
  }

  function href(item, base) {
    if (item.k === "c") return `${base}c/${item.i}/`;
    if (item.k === "v") return `${base}d/${item.d}/#v-${item.i}`;
    if (item.k === "x") return `${base}d/${item.d}/#x-${item.i}`;
    return `${base}d/${item.d}/#a-${item.i}`;
  }

  function render(app, config, secret) {
    if (!secret || !NV.crypto || !NV.search) return;

    const params = new URLSearchParams(window.location.search);
    const state = {
      q: params.get("q") || "",
      k: values(params, "k"),
      tp: values(params, "tp"),
      s: values(params, "s"),
      im: values(params, "im"),
      tr: values(params, "tr"),
      from: params.get("from") || "",
      to: params.get("to") || "",
      score: Number(params.get("score") || 0),
      sort: params.get("sort") || "relevant",
      all: params.get("all") === "1"
    };
    const months = (config.months || []).slice();
    const initialMonths = state.all ? months : months.slice(-3);
    let items = [];
    let shown = 100;
    let active = -1;
    let timer = 0;

    const root = make("section", "searchpage", app);
    const heading = make("h1", "searchpage__title", root);
    text(heading, T.title);
    const form = make("div", "searchpage__form", root);
    const input = make("input", "searchpage__input", form);
    input.type = "search";
    input.placeholder = T.placeholder;
    input.value = state.q;
    input.setAttribute("aria-label", T.placeholder);
    const clear = make("button", "searchpage__clear", form);
    clear.type = "button";
    text(clear, T.clear);
    const count = make("p", "searchpage__count", form);
    const shortcuts = make("p", "searchpage__shortcuts", root);
    text(shortcuts, T.shortcuts);
    const layout = make("div", "searchpage__layout", root);
    const details = make("details", "searchpage__filters", layout);
    details.open = true;
    const summary = make("summary", "", details);
    text(summary, T.filters);
    const filterBody = make("div", "searchpage__filterbody", details);
    const results = make("div", "searchpage__results", layout);
    const status = make("p", "searchpage__status", results);
    const list = make("div", "searchpage__list", results);
    const more = make("button", "searchpage__more", results);
    more.type = "button";
    text(more, T.more);

    function updateUrl() {
      const next = new URLSearchParams();
      if (state.q) next.set("q", state.q);
      ["k", "tp", "s", "im", "tr"].forEach(function (key) {
        if (state[key].size) next.set(key, Array.from(state[key]).join(","));
      });
      if (state.from) next.set("from", state.from);
      if (state.to) next.set("to", state.to);
      if (state.score) next.set("score", state.score);
      if (state.sort !== "relevant") next.set("sort", state.sort);
      if (state.all) next.set("all", "1");
      const query = next.toString();
      history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
    }

    function filtered() {
      const parsed = NV.search.parse(state.q);
      let found = NV.search.run(items, state.q, { sort: "paid" });
      found = found.filter(function (item) {
        return (!state.k.size || state.k.has(item.k || "a")) &&
          (!state.tp.size || state.tp.has(item.tp || "")) &&
          (!state.s.size || state.s.has(item.s || "")) &&
          (!state.im.size || state.im.has(item.im || "")) &&
          (!state.tr.size || state.tr.has(item.tr || "")) &&
          (!state.from || item.d >= state.from) &&
          (!state.to || item.d <= state.to) &&
          Number(item.sc || 0) >= state.score;
      });
      if (state.sort === "newest") found.sort(function (a, b) { return b.d.localeCompare(a.d); });
      if (state.sort === "oldest") found.sort(function (a, b) { return a.d.localeCompare(b.d); });
      if (state.sort === "score") found.sort(function (a, b) { return Number(b.sc || 0) - Number(a.sc || 0); });
      return { items: found, parsed: parsed };
    }

    function group(label, key, choices) {
      const section = make("section", "searchpage__group", filterBody);
      const title = make("h2", "", section);
      text(title, label);
      choices.forEach(function (choice) {
        const button = make("button", "searchpage__chip", section);
        button.type = "button";
        if (state[key].has(choice.value)) button.classList.add("is-active");
        text(button, `${choice.label} (${choice.count})`);
        button.addEventListener("click", function () {
          if (state[key].has(choice.value)) state[key].delete(choice.value);
          else state[key].add(choice.value);
          shown = 100;
          refresh();
        });
      });
    }

    /* Items that survive the query and every filter group EXCEPT `skip`.
     *
     * That exception is the whole point. Counting a facet against its own selection makes
     * every unselected chip read "(0)"; counting it against nothing makes the chips lie the
     * other way - the first build showed "Bài báo (2638)" sitting next to "81 kết quả". A
     * chip has to answer one question: how many more rows do I get if I click this. */
    function survivors(skip) {
      const base = NV.search.run(items, state.q, { sort: "paid" });
      return base.filter(function (item) {
        return (skip === "k" || !state.k.size || state.k.has(item.k || "a")) &&
          (skip === "tp" || !state.tp.size || state.tp.has(item.tp || "")) &&
          (skip === "s" || !state.s.size || state.s.has(item.s || "")) &&
          (skip === "im" || !state.im.size || state.im.has(item.im || "")) &&
          (skip === "tr" || !state.tr.size || state.tr.has(item.tr || "")) &&
          (!state.from || item.d >= state.from) &&
          (!state.to || item.d <= state.to) &&
          Number(item.sc || 0) >= state.score;
      });
    }

    function choices(key, labels, limit) {
      const counts = {};
      survivors(key).forEach(function (item) {
        const value = key === "k" ? (item.k || "a") : (item[key] || "");
        if (value) counts[value] = (counts[value] || 0) + 1;
      });
      // A chip already switched on stays visible even at zero, otherwise turning it off
      // again means hunting for a control that removed itself.
      state[key].forEach(function (value) {
        if (!(value in counts)) counts[value] = 0;
      });
      return Object.keys(counts).sort(function (a, b) {
        return counts[b] - counts[a] || a.localeCompare(b);
      }).slice(0, limit || Infinity).map(function (value) {
        return { value: value, label: labels && labels[value] ? labels[value] : value, count: counts[value] };
      });
    }

    function drawFilters() {
      text(filterBody, "");
      group(T.type, "k", choices("k", { a: T.article, x: T.post, v: T.video, c: T.curated }));
      group(T.topic, "tp", choices("tp"));
      const sourceSearch = make("input", "searchpage__sourcefind", filterBody);
      sourceSearch.type = "search";
      sourceSearch.placeholder = T.sourceFind;
      group(T.source, "s", choices("s", null, 12));
      sourceSearch.addEventListener("input", function () {
        const folded = NV.search.fold(sourceSearch.value);
        Array.prototype.forEach.call(filterBody.querySelectorAll(".searchpage__group:nth-of-type(3) .searchpage__chip"), function (button) {
          button.hidden = !!folded && NV.search.fold(button.textContent).indexOf(folded) === -1;
        });
      });
      group(T.impact, "im", choices("im"));
      group(T.tier, "tr", choices("tr", { paid: T.paid, free: "Miễn phí" }));

      const dates = make("section", "searchpage__group", filterBody);
      const dateTitle = make("h2", "", dates);
      text(dateTitle, T.date);
      ["from", "to"].forEach(function (key) {
        const field = make("input", "searchpage__date", dates);
        field.type = "date";
        field.value = state[key];
        field.setAttribute("aria-label", key === "from" ? T.from : T.to);
        field.addEventListener("change", function () { state[key] = field.value; refresh(); });
      });

      const scoreGroup = make("section", "searchpage__group", filterBody);
      const scoreTitle = make("h2", "", scoreGroup);
      text(scoreTitle, `${T.score}: ${state.score}`);
      const range = make("input", "searchpage__range", scoreGroup);
      range.type = "range";
      range.min = "0";
      range.max = "10";
      range.step = "1";
      range.value = String(state.score);
      range.addEventListener("input", function () {
        state.score = Number(range.value);
        refresh();
      });

      const sort = make("select", "searchpage__sort", filterBody);
      [["relevant", T.relevant], ["newest", T.newest], ["oldest", T.oldest], ["score", T.highest]].forEach(function (option) {
        const el = make("option", "", sort);
        el.value = option[0];
        text(el, option[1]);
      });
      sort.value = state.sort;
      sort.addEventListener("change", function () { state.sort = sort.value; refresh(); });
    }

    function drawResults() {
      const result = filtered();
      text(list, "");
      result.items.slice(0, shown).forEach(function (item, index) {
        const row = make("a", "searchpage__result", list);
        row.href = href(item, config.base || "../");
        row.tabIndex = index === active ? 0 : -1;
        if (index === active) row.classList.add("is-active");
        const meta = make("p", "searchpage__meta", row);
        text(meta, `${kindLabel(item)} · ${item.d.split("-").reverse().join("/")} · ${item.s || "Không rõ nguồn"}${item.tr === "paid" ? ` · ${T.paid}` : ""}`);
        const title = make("h2", "searchpage__resulttitle", row);
        title.innerHTML = NV.search.highlight(item.t || "", result.parsed);
        if (item.sn) {
          const snippet = make("p", "searchpage__snippet", row);
          text(snippet, item.sn);
        }
        const score = make("span", "searchpage__score", row);
        text(score, `Điểm ${item.sc || 0}`);
      });
      text(count, `${result.items.length} kết quả`);
      more.hidden = result.items.length <= shown;
      text(status, result.items.length ? "" : `${T.none} Đang lọc: ${state.q || "toàn bộ kho tin"}.`);
      if (!result.items.length) {
        const reset = make("button", "searchpage__reset", status);
        reset.type = "button";
        text(reset, T.reset);
        reset.addEventListener("click", function () {
          state.q = "";
          ["k", "tp", "s", "im", "tr"].forEach(function (key) { state[key].clear(); });
          state.from = "";
          state.to = "";
          state.score = 0;
          input.value = "";
          refresh();
        });
      }
    }

    function refresh() {
      updateUrl();
      drawFilters();
      drawResults();
    }

    async function load(targetMonths) {
      text(status, T.loading);
      const loaded = await Promise.all(targetMonths.map(function (month) {
        return NV.crypto.fetchJson(`${config.indexBase}${month}.enc`, secret);
      }));
      items = loaded.reduce(function (all, shard) {
        return all.concat(shard.items || []);
      }, []);
      refresh();
    }

    input.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        state.q = input.value;
        shown = 100;
        refresh();
      }, 150);
    });
    clear.addEventListener("click", function () { input.value = ""; state.q = ""; refresh(); });
    more.addEventListener("click", function () { shown += 100; drawResults(); });
    document.addEventListener("keydown", function (event) {
      const rows = list.querySelectorAll(".searchpage__result");
      if (event.key === "/" && document.activeElement !== input) { event.preventDefault(); input.focus(); }
      if (event.key === "Escape") { input.value = ""; state.q = ""; refresh(); }
      if ((event.key === "ArrowDown" || event.key === "ArrowUp") && rows.length) {
        event.preventDefault();
        active = Math.max(0, Math.min(rows.length - 1, active + (event.key === "ArrowDown" ? 1 : -1)));
        drawResults();
        list.querySelectorAll(".searchpage__result")[active].focus();
      }
      if (event.key === "Enter" && active >= 0 && rows[active]) rows[active].click();
    });

    if (!state.all && months.length > 3) {
      const allButton = make("button", "searchpage__all", root);
      allButton.type = "button";
      text(allButton, `${T.all} (${months.length} tháng)`);
      allButton.addEventListener("click", function () {
        state.all = true;
        allButton.disabled = true;
        load(months);
      });
    }
    load(initialMonths).then(function () { input.focus(); }).catch(function () {
      text(status, "Không thể nạp chỉ mục tìm kiếm.");
    });
  }

  NV.searchPage = { render: render };
}());
