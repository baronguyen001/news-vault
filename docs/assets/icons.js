(function () {
  "use strict";

  window.NV = window.NV || {};

  /* Fixed category icons.
   *
   * These replaced per-day AI illustrations. An icon is keyed by the topic slug the
   * builder already computes, so the archive looks identical on every page, costs no
   * API call, and adds about a kilobyte to the payload instead of 60 per picture.
   *
   * Every path is a plain 24x24 stroke drawing using currentColor, so the icon follows
   * the theme with no extra CSS. */
  const PATHS = {
    "kinh-te-tai-chinh":
      "M3 19h18M6 16V9m4.5 7V5m4.5 11v-6m4.5 6V7",
    /* Candlesticks, not the bar chart used for kinh-te-tai-chinh: at 24px the two must be
     * tellable apart at a glance, which is the whole point of a fixed icon per topic. */
    "chung-khoan":
      "M3 20h18M6 7v10M4.8 9.5h2.4v5H4.8zM12 4v14M10.8 7h2.4v7h-2.4zM18 6v11M16.8 8.5h2.4v6h-2.4z",
    crypto:
      "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM9.5 8h4a2 2 0 1 1 0 4h-4Zm0 4h4.5a2 2 0 1 1 0 4H9.5Zm0-4V6.5m0 11V16m3-9.5V6.5m0 11V16",
    "chinh-tri-chinh-sach":
      "M3 20h18M5 20V10m4.67 10V10m4.66 10V10M19 20V10M12 3l8 5H4l8-5Z",
    "cong-nghe-ai":
      "M8.5 8.5h7v7h-7zM12 3v3m-4 0V4m8 2V4M3 12h3m-3 4h3m12-4h3m-3 4h3M8 21v-2m4 2v-3m4 3v-2",
    "xung-dot-chien-tranh":
      "M12 3 4 6v5.5c0 4.4 3.2 8.2 8 9.5 4.8-1.3 8-5.1 8-9.5V6l-8-3Zm-2.5 6 5 5m0-5-5 5",
    "phap-luat-nghi-dinh":
      "M12 4v16M8 20h8M4.5 8h15M6.5 8 4 13.5h5L6.5 8Zm11 0L15 13.5h5L17.5 8Z",
    "van-hoa-xa-hoi":
      "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8.5 0a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3 19v-1a5 5 0 0 1 5-5h2a5 5 0 0 1 5 5v1m1-6h1a4 4 0 0 1 4 4v2",
    "y-te-suc-khoe":
      "M12 4v16m-8-8h16M6.5 6.5 12 12l5.5-5.5",
    "moi-truong-nang-luong":
      "M12 3c3.5 3 5.5 6 5.5 9a5.5 5.5 0 0 1-11 0c0-3 2-6 5.5-9Zm0 6v9",
    khac:
      "M4 5h16v14H4zM7 9h6M7 12h10M7 15h10",
  };

  const FALLBACK = PATHS.khac;

  /** Return the 24x24 SVG source for a topic slug. Unknown slugs get the generic icon. */
  function svg(key) {
    const d = PATHS[key] || FALLBACK;
    return (
      '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" ' +
      'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="' +
      d +
      '"/></svg>'
    );
  }

  /**
   * Append the icon for `key` to `parent`.
   *
   * The markup is assembled from this file's own constants only - `key` selects a path,
   * it is never interpolated - so innerHTML here cannot carry archive text into the DOM.
   */
  function render(parent, key, cls) {
    const span = document.createElement("span");
    span.className = cls || "icon";
    span.setAttribute("aria-hidden", "true");
    span.innerHTML = svg(key);
    parent.appendChild(span);
    return span;
  }

  window.NV.icons = { svg, render, has: (key) => Object.hasOwn(PATHS, key) };
})();
