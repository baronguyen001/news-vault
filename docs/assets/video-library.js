/* Private channel-oriented library for videos that have completed summarisation. */
(function () {
  "use strict";
  if (!window.NV) window.NV = {};

  const T = {
    title: "Thư viện video",
    subtitle: "Các video đã được tóm tắt, sắp theo kênh.",
    search: "Tìm theo tiêu đề, kênh hoặc chủ đề…",
    allChannels: "Tất cả kênh",
    allTypes: "Mọi định dạng",
    longForm: "Video dài",
    shorts: "Short",
    allStatus: "Mọi trạng thái",
    summarized: "Đã tóm tắt",
    retry: "Cần tóm tắt lại",
    unavailable: "Không thể tóm tắt",
    result: (n) => `${n} video`,
    channel: (n) => `${n} kênh`,
    noResults: "Không có video phù hợp với bộ lọc.",
    clear: "Xóa bộ lọc",
    sortNewest: "Mới tóm tắt nhất",
    sortOldest: "Cũ nhất",
    sortChannel: "Theo kênh A–Z",
    channelList: "Kênh",
    total: "Tổng video",
    complete: "Đã tóm tắt",
    pending: "Cần xử lý"
  };

  function make(tag, cls, parent) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (parent) parent.appendChild(el);
    return el;
  }
  function text(el, value) { el.textContent = value == null ? "" : String(value); }
  function safeList(value) { return Array.isArray(value) ? value.filter((v) => v && typeof v === "object") : []; }
  function label(video) { return typeof video.c === "string" && video.c.trim() ? video.c.trim() : "Kênh chưa rõ"; }
  function folded(value) {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/đ/g, "d");
  }
  function timestamp(video) { return String(video.p || video.d || ""); }

  function addStat(parent, value, labelText) {
    const stat = make("div", "vlibrary__stat", parent);
    const n = make("strong", "vlibrary__stat-value", stat); text(n, value);
    const l = make("span", "vlibrary__stat-label", stat); text(l, labelText);
  }

  function render(app, data) {
    const payload = data && typeof data === "object" ? data : {};
    const videos = safeList(payload.videos);
    const state = { channel: "", query: "", type: "all", status: "all", sort: "newest" };

    const head = make("header", "vlibrary__head", app);
    const h1 = make("h1", "vlibrary__title", head); text(h1, T.title);
    const sub = make("p", "vlibrary__subtitle", head); text(sub, T.subtitle);
    const stats = make("div", "vlibrary__stats", head);
    addStat(stats, videos.length, T.total);
    addStat(stats, new Set(videos.map(label)).size, T.channel);
    addStat(stats, videos.filter((v) => (v.st || "summarized") === "summarized").length, T.complete);
    addStat(stats, videos.filter((v) => (v.st || "summarized") !== "summarized").length, T.pending);

    const controls = make("section", "vlibrary__controls", app);
    controls.setAttribute("aria-label", "Lọc thư viện video");
    const input = make("input", "vlibrary__search", controls);
    input.type = "search"; input.placeholder = T.search; input.setAttribute("aria-label", T.search);
    const channelSelect = make("select", "vlibrary__select", controls);
    channelSelect.setAttribute("aria-label", T.channelList);
    const all = make("option", "", channelSelect); all.value = ""; text(all, T.allChannels);
    const channels = Array.from(new Set(videos.map(label))).sort((a, b) => a.localeCompare(b, "vi"));
    for (const channel of channels) { const option = make("option", "", channelSelect); option.value = channel; text(option, channel); }
    const typeSelect = make("select", "vlibrary__select", controls);
    typeSelect.setAttribute("aria-label", "Định dạng video");
    [["all", T.allTypes], ["long", T.longForm], ["short", T.shorts]].forEach(([value, name]) => {
      const option = make("option", "", typeSelect); option.value = value; text(option, name);
    });
    const statusSelect = make("select", "vlibrary__select", controls);
    statusSelect.setAttribute("aria-label", "Trạng thái tóm tắt");
    [["all", T.allStatus], ["summarized", T.summarized], ["retry", T.retry], ["unavailable", T.unavailable]].forEach(([value, name]) => {
      const option = make("option", "", statusSelect); option.value = value; text(option, name);
    });
    const sortSelect = make("select", "vlibrary__select", controls);
    sortSelect.setAttribute("aria-label", "Sắp xếp");
    [["newest", T.sortNewest], ["oldest", T.sortOldest], ["channel", T.sortChannel]].forEach(([value, name]) => {
      const option = make("option", "", sortSelect); option.value = value; text(option, name);
    });
    const clear = make("button", "vlibrary__clear", controls); clear.type = "button"; text(clear, T.clear);

    const layout = make("div", "vlibrary__layout", app);
    const side = make("aside", "vlibrary__channels", layout);
    const sideTitle = make("h2", "vlibrary__channels-title", side); text(sideTitle, T.channelList);
    const channelButtons = make("div", "vlibrary__channel-buttons", side);
    const main = make("section", "vlibrary__main", layout);
    const count = make("p", "vlibrary__count", main); count.setAttribute("aria-live", "polite");
    const list = make("ul", "cards videos__list vlibrary__list", main);
    const empty = make("p", "vlibrary__empty", main); text(empty, T.noResults); empty.hidden = true;

    function setChannel(channel) { state.channel = channel; channelSelect.value = channel; paint(); }
    function buildChannelButtons() {
      text(channelButtons, "");
      const counts = new Map(); videos.forEach((video) => counts.set(label(video), (counts.get(label(video)) || 0) + 1));
      [["", T.allChannels, videos.length], ...channels.map((channel) => [channel, channel, counts.get(channel)])].forEach(([value, name, total]) => {
        const btn = make("button", "vlibrary__channel", channelButtons); btn.type = "button";
        btn.setAttribute("aria-pressed", value === state.channel ? "true" : "false");
        text(btn, `${name} (${total})`); btn.addEventListener("click", () => setChannel(value));
      });
    }
    function matches(video) {
      if (state.channel && label(video) !== state.channel) return false;
      if (state.type === "short" && !video.sh) return false;
      if (state.type === "long" && video.sh) return false;
      if (state.status !== "all" && (video.st || "summarized") !== state.status) return false;
      const haystack = folded([video.t, label(video), video.ty].join(" "));
      return !state.query || haystack.includes(folded(state.query));
    }
    function sorted(items) {
      return items.sort((a, b) => {
        if (state.sort === "channel") return label(a).localeCompare(label(b), "vi") || timestamp(b).localeCompare(timestamp(a));
        const direction = state.sort === "oldest" ? 1 : -1;
        return direction * timestamp(a).localeCompare(timestamp(b));
      });
    }
    function paint() {
      const shown = sorted(videos.filter(matches));
      text(count, T.result(shown.length)); text(list, "");
      for (const video of shown) {
        if (!window.NV.videos) continue;
        const card = window.NV.videos.card(video);
        const header = card.children && card.children[0];
        if (header) {
          const badge = make("span", `badge vlibrary__status vlibrary__status--${video.st || "summarized"}`, header);
          text(badge, T[video.st || "summarized"] || T.summarized);
        }
        list.appendChild(card);
      }
      empty.hidden = shown.length !== 0;
      buildChannelButtons();
    }
    input.addEventListener("input", () => { state.query = input.value.trim(); paint(); });
    channelSelect.addEventListener("change", () => setChannel(channelSelect.value));
    typeSelect.addEventListener("change", () => { state.type = typeSelect.value; paint(); });
    statusSelect.addEventListener("change", () => { state.status = statusSelect.value; paint(); });
    sortSelect.addEventListener("change", () => { state.sort = sortSelect.value; paint(); });
    clear.addEventListener("click", () => { state.channel = ""; state.query = ""; state.type = "all"; state.status = "all"; state.sort = "newest"; input.value = ""; channelSelect.value = ""; typeSelect.value = "all"; statusSelect.value = "all"; sortSelect.value = "newest"; paint(); });
    paint();
  }
  window.NV.videoLibrary = { render: render, folded: folded };
})();
