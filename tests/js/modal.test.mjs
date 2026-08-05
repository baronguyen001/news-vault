import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'modal.js');
const source = fs.readFileSync(modulePath, 'utf8');

function makeEl(tag, document) {
  const el = {
    tagName: String(tag).toUpperCase(),
    className: '',
    textContent: '',
    type: '',
    hidden: false,
    children: [],
    parentNode: null,
    style: {},
    attrs: {},
    listeners: {},
    classList: {
      add(name) {
        const names = el.className.split(/\s+/).filter(Boolean);
        if (!names.includes(name)) names.push(name);
        el.className = names.join(' ');
      },
      remove(name) {
        el.className = el.className.split(/\s+/).filter((item) => item !== name).join(' ');
      },
      contains(name) {
        return el.className.split(/\s+/).includes(name);
      },
    },
    appendChild(child) {
      if (child.parentNode) child.parentNode.removeChild(child);
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    insertBefore(node, ref) {
      if (node.parentNode) node.parentNode.removeChild(node);
      const index = ref === null ? this.children.length : this.children.indexOf(ref);
      node.parentNode = this;
      this.children.splice(index < 0 ? this.children.length : index, 0, node);
      return node;
    },
    removeChild(child) {
      const index = this.children.indexOf(child);
      if (index >= 0) this.children.splice(index, 1);
      child.parentNode = null;
      return child;
    },
    setAttribute(k, v) {
      this.attrs[k] = String(v);
    },
    getAttribute(k) {
      return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null;
    },
    addEventListener(type, fn) {
      (this.listeners[type] = this.listeners[type] || []).push(fn);
    },
    click() {
      (this.listeners.click || []).forEach((fn) => fn({ preventDefault() {} }));
    },
    focus() {
      document.activeElement = this;
    },
    querySelector(sel) {
      if (sel.startsWith(".") && this.className.split(/\s+/).includes(sel.slice(1))) {
        return this;
      }
      for (const child of this.children) {
        const found = child.querySelector(sel);
        if (found) return found;
      }
      return null;
    },
    querySelectorAll(sel) {
      if (!sel.includes("button") && !sel.includes("a[href")) return [];
      const result = [];
      const walk = (item) => {
        if (item.tagName === "BUTTON" || item.tagName === "A") result.push(item);
        item.children.forEach(walk);
      };
      walk(this);
      return result;
    },
  };
  Object.defineProperty(el, "nextSibling", {
    get() {
      if (!el.parentNode) return null;
      const siblings = el.parentNode.children;
      const index = siblings.indexOf(el);
      return index >= 0 ? siblings[index + 1] || null : null;
    },
  });
  return el;
}

function setup() {
  const document = {
    activeElement: null,
    listeners: {},
    createElement(tag) {
      return makeEl(tag, document);
    },
    addEventListener(type, fn) {
      (this.listeners[type] = this.listeners[type] || []).push(fn);
    },
    dispatch(event) {
      (this.listeners.keydown || []).forEach((fn) => fn(event));
    },
  };
  document.body = makeEl("body", document);
  const ctx = { window: { NV: {} }, document };
  vm.createContext(ctx);
  vm.runInContext(source, ctx, { filename: modulePath });
  return { modal: ctx.window.NV.modal, document };
}

function article(document, name) {
  const node = document.createElement("div");
  node.textContent = name;
  return node;
}

test("starts closed without an element", () => {
  const { modal } = setup();
  assert.equal(modal.isOpen(), false);
  assert.equal(modal.element(), null);
});

test("builds the documented DOM", () => {
  const { modal, document } = setup();
  modal.open({ node: article(document, "body") });
  const root = modal.element();
  assert.equal(root.className, "modal");
  assert.equal(root.getAttribute("role"), "dialog");
  assert.equal(root.getAttribute("aria-modal"), "true");
  assert.ok(root.querySelector(".modal__backdrop"));
  assert.ok(root.querySelector(".modal__box"));
  assert.ok(root.querySelector(".modal__head"));
  assert.equal(root.querySelector(".modal__title").tagName, "H2");
  assert.equal(root.querySelector(".modal__close").getAttribute("aria-label"), "Đóng");
  assert.ok(root.querySelector(".modal__content"));
});

test("moves the node and opens", () => {
  const { modal, document } = setup();
  const node = article(document, "body");
  modal.open({ node });
  assert.equal(node.parentNode, modal.element().querySelector(".modal__content"));
  assert.equal(node.hidden, false);
  assert.equal(modal.isOpen(), true);
});

test("shows the root as a grid so the box stays centred", () => {
  const { modal, document } = setup();
  modal.open({ node: article(document, "body") });
  assert.equal(modal.element().style.display, "grid");
  modal.close();
  assert.equal(modal.element().style.display, "none");
});

test("restores a middle node to its original position", () => {
  const { modal, document } = setup();
  const parent = document.createElement("div");
  const first = article(document, "first");
  const middle = article(document, "middle");
  const last = article(document, "last");
  parent.appendChild(first);
  parent.appendChild(middle);
  parent.appendChild(last);
  modal.open({ node: middle });
  modal.close();
  assert.deepEqual(parent.children, [first, middle, last]);
});

test("restores a last node at the end", () => {
  const { modal, document } = setup();
  const parent = document.createElement("div");
  const first = article(document, "first");
  const last = article(document, "last");
  parent.appendChild(first);
  parent.appendChild(last);
  modal.open({ node: last });
  modal.close();
  assert.deepEqual(parent.children, [first, last]);
});

test("sets the title or an empty string", () => {
  const { modal, document } = setup();
  modal.open({ title: "Tiêu đề", node: article(document, "body") });
  assert.equal(modal.element().querySelector(".modal__title").textContent, "Tiêu đề");
  modal.close();
  modal.open({ node: article(document, "body") });
  assert.equal(modal.element().querySelector(".modal__title").textContent, "");
});

test("Escape closes and calls onClose once", () => {
  const { modal, document } = setup();
  const node = article(document, "body");
  let calls = 0;
  modal.open({ node, onClose: (received) => {
    calls += 1;
    assert.equal(received, node);
  } });
  document.dispatch({ key: "Escape", preventDefault() {} });
  assert.equal(calls, 1);
  assert.equal(modal.isOpen(), false);
});

test("backdrop click closes", () => {
  const { modal, document } = setup();
  modal.open({ node: article(document, "body") });
  modal.element().querySelector(".modal__backdrop").click();
  assert.equal(modal.isOpen(), false);
});

test("close button click closes", () => {
  const { modal, document } = setup();
  modal.open({ node: article(document, "body") });
  modal.element().querySelector(".modal__close").click();
  assert.equal(modal.isOpen(), false);
});

test("focus moves to close and returns afterward", () => {
  const { modal, document } = setup();
  const previous = document.createElement("button");
  previous.focus();
  modal.open({ node: article(document, "body") });
  assert.equal(document.activeElement, modal.element().querySelector(".modal__close"));
  modal.close();
  assert.equal(document.activeElement, previous);
});

test("body is locked while open", () => {
  const { modal, document } = setup();
  modal.open({ node: article(document, "body") });
  assert.equal(document.body.classList.contains("modal-open"), true);
  modal.close();
  assert.equal(document.body.classList.contains("modal-open"), false);
});

test("opening another modal restores the first node", () => {
  const { modal, document } = setup();
  const parent = document.createElement("div");
  const first = article(document, "first");
  const second = article(document, "second");
  parent.appendChild(first);
  parent.appendChild(second);
  modal.open({ node: first });
  modal.open({ node: second });
  assert.equal(first.parentNode, parent);
  assert.equal(second.parentNode, modal.element().querySelector(".modal__content"));
});

test("closing while closed is harmless", () => {
  const { modal } = setup();
  assert.doesNotThrow(() => modal.close());
  assert.equal(modal.isOpen(), false);
});

test("opening without a node is a no-op", () => {
  const { modal } = setup();
  modal.open({ title: "No node" });
  assert.equal(modal.isOpen(), false);
  assert.equal(modal.element(), null);
});

test("handler errors do not prevent closing", () => {
  const { modal, document } = setup();
  modal.open({
    node: article(document, "body"),
    onClose: () => {
      throw new Error("failure");
    },
  });
  assert.doesNotThrow(() => modal.close());
  assert.equal(modal.isOpen(), false);
});

test("Escape while closed does nothing", () => {
  const { modal, document } = setup();
  let prevented = false;
  document.dispatch({
    key: "Escape",
    preventDefault() {
      prevented = true;
    },
  });
  assert.equal(prevented, false);
  assert.equal(modal.isOpen(), false);
});
