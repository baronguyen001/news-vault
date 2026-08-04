"use strict";
window.NV = window.NV || {};

(function () {
  const STORAGE_KEYS = {
    saved: "nv.saved",
    read: "nv.read",
    watch: "nv.watch",
    visit: "nv.visit",
    theme: "nv.theme",
  };
  const MAX_READ = 5000;

  // In-memory state
  let _saved = new Set();
  let _read = new Set();
  let _watchlist = [];
  let _lastVisit = null;
  let _theme = "";
  let _initialized = false;

  // Event emitter
  const _handlers = {};

  function _emit(event, ...args) {
    const list = _handlers[event];
    if (list) {
      list.forEach((fn) => {
        try {
          fn(...args);
        } catch (e) {
          // ignore handler errors
        }
      });
    }
  }

  // Storage helpers with try/catch
  function _readJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) return fallback;
      return JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  }

  function _writeJson(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      // Safari private mode – silently ignore
    }
  }

  // Persist sets to storage
  function _persistSaved() {
    _writeJson(STORAGE_KEYS.saved, Array.from(_saved));
  }

  function _persistRead() {
    _writeJson(STORAGE_KEYS.read, Array.from(_read));
  }

  function _persistWatchlist() {
    _writeJson(STORAGE_KEYS.watch, _watchlist);
  }

  // Public API
  const user = {
    init() {
      if (_initialized) return;
      _initialized = true;

      // Load saved
      const savedArr = _readJson(STORAGE_KEYS.saved, []);
      _saved = new Set(savedArr);

      // Load read (capped)
      const readArr = _readJson(STORAGE_KEYS.read, []);
      _read = new Set(readArr.slice(-MAX_READ));

      // Load watchlist
      _watchlist = _readJson(STORAGE_KEYS.watch, []);

      // Load last visit timestamp (previous visit)
      _lastVisit = _readJson(STORAGE_KEYS.visit, null);

      // Apply theme synchronously
      const storedTheme = _readJson(STORAGE_KEYS.theme, "");
      _theme = storedTheme;
      if (storedTheme) {
        document.documentElement.dataset.theme = storedTheme;
      } else {
        delete document.documentElement.dataset.theme;
      }

      // Write current visit timestamp (for next page load)
      _writeJson(STORAGE_KEYS.visit, Date.now());
    },

    isSaved(url) {
      return _saved.has(url);
    },

    toggleSave(url) {
      let newState;
      if (_saved.has(url)) {
        _saved.delete(url);
        newState = false;
      } else {
        _saved.add(url);
        newState = true;
      }
      _persistSaved();
      _emit("change");
      return newState;
    },

    isRead(url) {
      return _read.has(url);
    },

    markRead(url) {
      if (_read.has(url)) return;
      _read.add(url);
      // Cap read set
      if (_read.size > MAX_READ) {
        const arr = Array.from(_read);
        const overflow = arr.length - MAX_READ;
        arr.splice(0, overflow);
        _read = new Set(arr);
      }
      _persistRead();
      _emit("change");
    },

    savedUrls() {
      return Array.from(_saved);
    },

    clearRead() {
      _read.clear();
      _persistRead();
      _emit("change");
    },

    watchlist() {
      return _watchlist.slice();
    },

    setWatchlist(terms) {
      _watchlist = terms.slice();
      _persistWatchlist();
      _emit("watchlist");
      _emit("change");
    },

    matchesWatchlist(item) {
      if (_watchlist.length === 0) return false;
      const foldFn = (NV.search && NV.search.fold) || function (v) {
        // fallback fold (simplified)
        return v.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "d").replace(/\s+/g, " ").trim();
      };
      const searchText = item.f ? item.f : foldFn(item.t);
      return _watchlist.some((term) => {
        const foldedTerm = foldFn(term);
        return searchText.indexOf(foldedTerm) !== -1;
      });
    },

    lastVisit() {
      return _lastVisit;
    },

    touchVisit() {
      // Called on page load after init? Actually init already writes the new timestamp.
      // This method is for explicit touch if needed.
      _writeJson(STORAGE_KEYS.visit, Date.now());
    },

    theme() {
      return _theme;
    },

    setTheme(value) {
      _theme = value;
      if (value) {
        document.documentElement.dataset.theme = value;
      } else {
        delete document.documentElement.dataset.theme;
      }
      _writeJson(STORAGE_KEYS.theme, value);
      _emit("theme", value);
    },

    on(event, handler) {
      if (!_handlers[event]) _handlers[event] = [];
      _handlers[event].push(handler);
    },

    stats() {
      return {
        saved: _saved.size,
        read: _read.size,
      };
    },
  };

  NV.user = user;
})();
