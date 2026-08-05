(function () {
  "use strict";

  if (typeof window === "undefined" || !window) return;
  if (!window.NV) window.NV = {};

  const MODES = Object.freeze(["list", "two", "three", "grid"]);
  const DEFAULT = "list";
  const STORAGE_KEY = "nv.layout";

  const T = {
    groupLabel: "Kiểu hiển thị",
    list: "1 cột",
    two: "2 cột",
    three: "3 cột",
    grid: "Lưới"
  };

  const controls = [];

  function make(tag, cls, parent) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (parent) parent.appendChild(el);
    return el;
  }

  function text(el, val) {
    el.textContent = val == null ? "" : String(val);
  }

  function normalise(value) {
    if (value && MODES.indexOf(value) !== -1) return value;
    return DEFAULT;
  }

  function get() {
    try {
      return normalise(window.localStorage.getItem(STORAGE_KEY));
    } catch (err) {
      return DEFAULT;
    }
  }

  function apply(mode) {
    const value = arguments.length > 0 ? normalise(mode) : get();
    if (typeof document !== "undefined" && document && document.documentElement) {
      document.documentElement.setAttribute("data-layout", value);
    }
    return value;
  }

  function refreshControls(mode) {
    const current = arguments.length > 0 ? normalise(mode) : get();
    for (let i = 0; i < controls.length; i++) {
      const wrapper = controls[i];
      if (!wrapper || !wrapper.children) continue;
      for (let j = 0; j < wrapper.children.length; j++) {
        const btn = wrapper.children[j];
        const pressed = btn.getAttribute("data-mode") === current ? "true" : "false";
        btn.setAttribute("aria-pressed", pressed);
      }
    }
  }

  function set(mode) {
    const normalised = normalise(mode);
    try {
      window.localStorage.setItem(STORAGE_KEY, normalised);
    } catch (err) {
      // storage is unavailable, but we still apply the choice for this page
    }
    apply(normalised);
    refreshControls(normalised);
    return normalised;
  }

  function mount(parent) {
    const currentMode = get();
    const wrapper = make("div", "layout-switch");
    wrapper.setAttribute("role", "group");
    wrapper.setAttribute("aria-label", T.groupLabel);

    for (let i = 0; i < MODES.length; i++) {
      const mode = MODES[i];
      const btn = make("button", "layout-switch__btn", wrapper);
      btn.type = "button";
      btn.setAttribute("data-mode", mode);
      btn.setAttribute("aria-pressed", mode === currentMode ? "true" : "false");
      text(btn, T[mode]);
      btn.addEventListener("click", function () {
        set(mode);
      });
    }

    if (parent && parent.appendChild) parent.appendChild(wrapper);
    controls.push(wrapper);
    return wrapper;
  }

  window.NV.layout = {
    MODES: MODES,
    DEFAULT: DEFAULT,
    normalise: normalise,
    get: get,
    set: set,
    apply: apply,
    mount: mount
  };

  try {
    if (typeof document !== "undefined" && document && document.documentElement) {
      apply();
    }
  } catch (err) {
    // do not break module load in a context without DOM
  }
})();
