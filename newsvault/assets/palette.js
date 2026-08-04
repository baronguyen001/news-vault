"use strict";
window.NV = window.NV || {};

(function () {
  const palette = {
    _commands: {},
    _groups: [],
    _element: null,
    _input: null,
    _list: null,
    _selectedIndex: -1,
    _previousFocus: null,
    _isOpen: false,
  };

  // --- helpers ---
  function _fold(text) {
    if (NV.search && NV.search.fold) {
      return NV.search.fold(text);
    }
    // fallback
    return text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "d").replace(/\s+/g, " ").trim();
  }

  function _fuzzyMatch(query, label) {
    const q = _fold(query);
    const l = _fold(label);
    let qi = 0;
    for (let li = 0; li < l.length && qi < q.length; li++) {
      if (l[li] === q[qi]) qi++;
    }
    if (qi !== q.length) return null;
    // return match position (first char index)
    const firstIdx = l.indexOf(q[0]);
    return firstIdx;
  }

  function _buildList(filtered) {
    const list = palette._list;
    list.innerHTML = "";
    if (filtered.length === 0) {
      const empty = document.createElement("div");
      empty.className = "palette__empty";
      empty.textContent = "Không có kết quả";
      list.appendChild(empty);
      return;
    }
    // Group by group field
    const groups = {};
    filtered.forEach((cmd) => {
      const g = cmd.group || "";
      if (!groups[g]) groups[g] = [];
      groups[g].push(cmd);
    });
    let index = 0;
    for (const [groupName, cmds] of Object.entries(groups)) {
      if (groupName) {
        const heading = document.createElement("div");
        heading.className = "palette__group";
        heading.textContent = groupName;
        list.appendChild(heading);
      }
      cmds.forEach((cmd) => {
        const item = document.createElement("div");
        item.className = "palette__item";
        item.role = "option";
        item.dataset.index = index;
        item.id = `palette-opt-${index}`;
        item.setAttribute("aria-selected", "false");
        const labelSpan = document.createElement("span");
        labelSpan.className = "palette__label";
        labelSpan.textContent = cmd.label;
        item.appendChild(labelSpan);
        if (cmd.hint) {
          const hintSpan = document.createElement("span");
          hintSpan.className = "palette__hint";
          hintSpan.textContent = cmd.hint;
          item.appendChild(hintSpan);
        }
        item.addEventListener("click", () => {
          _runCommand(cmd);
        });
        list.appendChild(item);
        index++;
      });
    }
    palette._selectedIndex = -1;
    palette._list.setAttribute("aria-activedescendant", "");
  }

  function _runCommand(cmd) {
    palette.close();
    try {
      cmd.run();
    } catch (e) {
      // ignore
    }
  }

  function _updateSelection(delta) {
    const items = palette._list.querySelectorAll(".palette__item");
    if (items.length === 0) return;
    let newIndex = palette._selectedIndex + delta;
    if (newIndex < 0) newIndex = items.length - 1;
    if (newIndex >= items.length) newIndex = 0;
    // Remove old selection
    if (palette._selectedIndex >= 0 && items[palette._selectedIndex]) {
      items[palette._selectedIndex].setAttribute("aria-selected", "false");
      items[palette._selectedIndex].classList.remove("palette__item--selected");
    }
    palette._selectedIndex = newIndex;
    items[newIndex].setAttribute("aria-selected", "true");
    items[newIndex].classList.add("palette__item--selected");
    palette._list.setAttribute("aria-activedescendant", items[newIndex].id);
    items[newIndex].scrollIntoView({ block: "nearest" });
  }

  function _filter() {
    const query = palette._input.value;
    const commands = Object.values(palette._commands);
    const scored = [];
    commands.forEach((cmd) => {
      const pos = _fuzzyMatch(query, cmd.label);
      if (pos !== null) {
        scored.push({ cmd, pos, len: cmd.label.length });
      }
    });
    // Sort by match position, then label length
    scored.sort((a, b) => {
      if (a.pos !== b.pos) return a.pos - b.pos;
      return a.len - b.len;
    });
    const filtered = scored.map((s) => s.cmd);
    _buildList(filtered);
  }

  // --- keyboard handler ---
  function _onKeyDown(e) {
    if (e.key === "Escape") {
      palette.close();
      e.preventDefault();
      return;
    }
    if (e.key === "ArrowDown") {
      _updateSelection(1);
      e.preventDefault();
      return;
    }
    if (e.key === "ArrowUp") {
      _updateSelection(-1);
      e.preventDefault();
      return;
    }
    if (e.key === "Enter") {
      const items = palette._list.querySelectorAll(".palette__item");
      if (palette._selectedIndex >= 0 && items[palette._selectedIndex]) {
        const index = parseInt(items[palette._selectedIndex].dataset.index, 10);
        const cmds = Object.values(palette._commands);
        if (index >= 0 && index < cmds.length) {
          _runCommand(cmds[index]);
        }
      }
      e.preventDefault();
      return;
    }
    if (e.key === "Tab") {
      // Trap focus inside dialog
      const focusable = palette._element.querySelectorAll('input, button, [tabindex]:not([tabindex="-1"])');
      if (focusable.length > 0) {
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey) {
          if (document.activeElement === first) {
            last.focus();
            e.preventDefault();
          }
        } else {
          if (document.activeElement === last) {
            first.focus();
            e.preventDefault();
          }
        }
      }
      return;
    }
  }

  // --- global shortcut ---
  function _onGlobalKeyDown(e) {
    // Ctrl+K or Cmd+K
    if ((e.ctrlKey || e.metaKey) && e.key === "k") {
      // Do not intercept if focus is in an input/textarea/select/contenteditable
      const tag = document.activeElement ? document.activeElement.tagName : "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || document.activeElement && document.activeElement.isContentEditable) {
        return;
      }
      e.preventDefault();
      palette.toggle();
    }
  }

  // --- create DOM ---
  function _createElement() {
    const div = document.createElement("div");
    div.className = "palette";
    div.setAttribute("role", "dialog");
    div.setAttribute("aria-label", "Lệnh");
    div.style.display = "none";
    div.innerHTML = `
      <div class="palette__backdrop"></div>
      <div class="palette__box">
        <input class="palette__input" type="text" placeholder="Tìm lệnh..." aria-label="Tìm lệnh" autocomplete="off" role="combobox" aria-expanded="true" aria-haspopup="listbox" aria-autocomplete="list">
        <div class="palette__list" role="listbox" aria-label="Kết quả"></div>
      </div>
    `;
    document.body.appendChild(div);
    palette._element = div;
    palette._input = div.querySelector(".palette__input");
    palette._list = div.querySelector(".palette__list");

    // Backdrop click
    div.querySelector(".palette__backdrop").addEventListener("click", () => {
      palette.close();
    });

    // Input events
    palette._input.addEventListener("input", _filter);
    palette._input.addEventListener("keydown", _onKeyDown);

  }

  // --- public API ---
  palette.register = function (commands) {
    commands.forEach((cmd) => {
      if (cmd.id && cmd.label && cmd.run) {
        palette._commands[cmd.id] = cmd;
      }
    });
  };

  palette.open = function () {
    if (palette._isOpen) return;
    if (!palette._element) _createElement();
    palette._previousFocus = document.activeElement;
    palette._element.style.display = "block";
    palette._isOpen = true;
    palette._input.value = "";
    palette._input.focus();
    _filter();
  };

  palette.close = function () {
    if (!palette._isOpen) return;
    palette._element.style.display = "none";
    palette._isOpen = false;
    if (palette._previousFocus && palette._previousFocus.focus) {
      palette._previousFocus.focus();
    }
    palette._previousFocus = null;
  };

  palette.toggle = function () {
    if (palette._isOpen) {
      palette.close();
    } else {
      palette.open();
    }
  };

  palette.isOpen = function () {
    return palette._isOpen;
  };

  // Bind the shortcut at load, not inside _createElement(): that function only runs on
  // the first open, and the shortcut is the only way to open the palette.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      document.addEventListener("keydown", _onGlobalKeyDown);
    });
  } else {
    document.addEventListener("keydown", _onGlobalKeyDown);
  }

  NV.palette = palette;
})();
