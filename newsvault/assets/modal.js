"use strict";
window.NV = window.NV || {};

/* A generic dialog. It knows nothing about articles: the caller hands it a title and a DOM
 * node, the dialog borrows that node until it is closed and then puts it back exactly where
 * it came from. Borrowing rather than cloning is what keeps every listener, every highlight
 * and every open/closed flag on the node alive across the trip. */
(function () {
  const NV = window.NV;
  let root = null;
  let titleElement = null;
  let closeButton = null;
  let content = null;
  let openNode = null;
  let originParent = null;
  let originNextSibling = null;
  let previousFocus = null;
  let closeHandler = null;

  function createElement() {
    root = document.createElement("div");
    root.className = "modal";
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-labelledby", "modal-title");
    root.style.display = "none";

    const backdrop = document.createElement("div");
    backdrop.className = "modal__backdrop";

    const box = document.createElement("div");
    box.className = "modal__box";

    const head = document.createElement("div");
    head.className = "modal__head";

    titleElement = document.createElement("h2");
    titleElement.className = "modal__title";
    titleElement.setAttribute("id", "modal-title");

    closeButton = document.createElement("button");
    closeButton.className = "modal__close";
    closeButton.type = "button";
    closeButton.setAttribute("aria-label", "Đóng");
    closeButton.textContent = "✕";

    content = document.createElement("div");
    content.className = "modal__content";

    head.appendChild(titleElement);
    head.appendChild(closeButton);
    box.appendChild(head);
    box.appendChild(content);
    root.appendChild(backdrop);
    root.appendChild(box);
    document.body.appendChild(root);

    backdrop.addEventListener("click", function () {
      closeModal();
    });
    closeButton.addEventListener("click", function () {
      closeModal();
    });
  }

  function focusables() {
    const box = root.querySelector(".modal__box");
    if (!box || typeof box.querySelectorAll !== "function") {
      return [];
    }
    return box.querySelectorAll(
      "a[href], button, input, select, textarea, " +
      "[tabindex]:not([tabindex=\"-1\"])"
    );
  }

  function handleKeydown(event) {
    if (!openNode) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeModal();
      return;
    }
    if (event.key !== "Tab") {
      return;
    }

    const items = focusables();
    if (!items.length) {
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function closeModal() {
    if (!openNode) {
      return;
    }

    const node = openNode;
    const parent = originParent;
    const nextSibling = originNextSibling;
    const handler = closeHandler;
    const focusTarget = previousFocus;

    if (parent) {
      // insertBefore with a null reference appends, which is exactly right for a node
      // that was last in its parent.
      parent.insertBefore(node, nextSibling);
    } else {
      content.removeChild(node);
    }

    root.style.display = "none";
    document.body.classList.remove("modal-open");
    if (focusTarget && typeof focusTarget.focus === "function") {
      focusTarget.focus();
    }

    openNode = null;
    originParent = null;
    originNextSibling = null;
    closeHandler = null;
    previousFocus = null;

    try {
      if (typeof handler === "function") {
        handler(node);
      }
    } catch (error) {
      // Closing must finish even when the caller's handler fails.
    }
  }

  document.addEventListener("keydown", handleKeydown);

  const modal = {
    isOpen: function () {
      return !!openNode;
    },

    open: function (options) {
      options = options || {};
      if (!options.node) {
        return;
      }
      if (openNode) {
        closeModal();
      }
      if (!root) {
        createElement();
      }

      previousFocus = document.activeElement;
      openNode = options.node;
      originParent = openNode.parentNode;
      originNextSibling = openNode.nextSibling;
      closeHandler = options.onClose;
      titleElement.textContent = options.title || "";
      content.appendChild(openNode);
      openNode.hidden = false;
      // Grid, not block: .modal centres its box with place-items and an inline
      // display:block would quietly throw that away.
      root.style.display = "grid";
      document.body.classList.add("modal-open");
      closeButton.focus();
    },

    close: function () {
      closeModal();
    },

    element: function () {
      return root;
    }
  };

  NV.modal = modal;
})();
