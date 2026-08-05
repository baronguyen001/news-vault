import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'layout.js');
const source = fs.readFileSync(modulePath, 'utf8');

function makeEl(tag) {
  const el = {
    tagName: String(tag).toUpperCase(),
    className: '',
    textContent: '',
    type: '',
    children: [],
    attrs: {},
    listeners: {},
    appendChild(child) { this.children.push(child); return child; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    click() { (this.listeners.click || []).forEach((fn) => fn({ preventDefault() {} })); },
  };
  return el;
}

function makeSandbox(options) {
  const opts = options || {};
  const store = new Map(opts.seed || []);
  const root = makeEl('html');
  const localStorage = opts.brokenStorage
    ? { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } }
    : {
        getItem(k) { return store.has(k) ? store.get(k) : null; },
        setItem(k, v) { store.set(k, String(v)); },
      };
  const document = { documentElement: root, createElement: makeEl };
  const window = { localStorage, document };
  const ctx = vm.createContext({ window, document, localStorage });
  vm.runInContext(source, ctx, { filename: modulePath });
  return { layout: ctx.window.NV.layout, root, store, document };
}

test('MODES is exactly ["list", "two", "three", "grid"]', () => {
  const { layout } = makeSandbox();
  // Copy first: the array is built inside the vm realm, so its prototype is that
  // realm's Array.prototype and deepStrictEqual would reject it on prototype identity.
  assert.deepEqual(Array.from(layout.MODES), ['list', 'two', 'three', 'grid']);
  assert.equal(Object.isFrozen(layout.MODES), true);
});

test('normalise maps each valid mode to itself', () => {
  const { layout } = makeSandbox();
  assert.equal(layout.normalise('list'), 'list');
  assert.equal(layout.normalise('two'), 'two');
  assert.equal(layout.normalise('three'), 'three');
  assert.equal(layout.normalise('grid'), 'grid');
});

test('normalise maps invalid values to "list"', () => {
  const { layout } = makeSandbox();
  assert.equal(layout.normalise(null), 'list');
  assert.equal(layout.normalise(undefined), 'list');
  assert.equal(layout.normalise(''), 'list');
  assert.equal(layout.normalise('TWO'), 'list');
  assert.equal(layout.normalise('masonry'), 'list');
  assert.equal(layout.normalise(0), 'list');
  assert.equal(layout.normalise({}), 'list');
});

test('get() returns "list" when nothing is stored', () => {
  const { layout } = makeSandbox();
  assert.equal(layout.get(), 'list');
});

test('get() returns the seeded valid mode', () => {
  const { layout } = makeSandbox({ seed: [['nv.layout', 'three']] });
  assert.equal(layout.get(), 'three');
});

test('get() returns "list" for a corrupt stored value', () => {
  const { layout } = makeSandbox({ seed: [['nv.layout', 'nonsense']] });
  assert.equal(layout.get(), 'list');
});

test('module load applies the stored mode to <html> immediately', () => {
  const { root } = makeSandbox({ seed: [['nv.layout', 'grid']] });
  assert.equal(root.getAttribute('data-layout'), 'grid');
});

test('set("two") writes "two" to storage and returns "two"', () => {
  const { layout, store } = makeSandbox();
  const result = layout.set('two');
  assert.equal(result, 'two');
  assert.equal(store.get('nv.layout'), 'two');
});

test('set("bogus") stores and returns "list"', () => {
  const { layout, store } = makeSandbox();
  const result = layout.set('bogus');
  assert.equal(result, 'list');
  assert.equal(store.get('nv.layout'), 'list');
});

test('set() updates data-layout on the root element', () => {
  const { layout, root } = makeSandbox();
  layout.set('three');
  assert.equal(root.getAttribute('data-layout'), 'three');
});

test('broken storage does not throw and the current choice is still applied', () => {
  const { layout, root } = makeSandbox({ brokenStorage: true });
  assert.doesNotThrow(() => layout.get());
  assert.equal(layout.set('two'), 'two');
  assert.equal(root.getAttribute('data-layout'), 'two');
  assert.doesNotThrow(() => layout.apply());
});

test('mount(null) returns a correctly built control', () => {
  const { layout } = makeSandbox();
  const ctrl = layout.mount(null);
  assert.equal(ctrl.className, 'layout-switch');
  assert.equal(ctrl.getAttribute('role'), 'group');
  assert.equal(ctrl.getAttribute('aria-label'), 'Kiểu hiển thị');
  assert.equal(ctrl.children.length, 4);

  const labels = ctrl.children.map((b) => b.textContent);
  assert.deepEqual(labels, ['1 cột', '2 cột', '3 cột', 'Lưới']);

  const modes = ctrl.children.map((b) => b.getAttribute('data-mode'));
  assert.deepEqual(modes, ['list', 'two', 'three', 'grid']);
});

test('mount(parent) appends the control to the parent', () => {
  const { layout } = makeSandbox();
  const parent = makeEl('div');
  const ctrl = layout.mount(parent);
  assert.equal(parent.children.length, 1);
  assert.equal(parent.children[0], ctrl);
});

test('mount marks exactly the stored-mode button as pressed', () => {
  const { layout } = makeSandbox({ seed: [['nv.layout', 'three']] });
  const ctrl = layout.mount(null);
  const pressed = ctrl.children.filter((b) => b.getAttribute('aria-pressed') === 'true');
  assert.equal(pressed.length, 1);
  assert.equal(pressed[0].getAttribute('data-mode'), 'three');
});

test('clicking the grid button updates storage, layout and pressed state', () => {
  const { layout, root, store } = makeSandbox({ seed: [['nv.layout', 'two']] });
  const ctrl = layout.mount(null);
  const twoBtn = ctrl.children.filter((b) => b.getAttribute('data-mode') === 'two')[0];
  const gridBtn = ctrl.children.filter((b) => b.getAttribute('data-mode') === 'grid')[0];
  assert.equal(twoBtn.getAttribute('aria-pressed'), 'true');

  gridBtn.click();

  assert.equal(store.get('nv.layout'), 'grid');
  assert.equal(root.getAttribute('data-layout'), 'grid');
  assert.equal(gridBtn.getAttribute('aria-pressed'), 'true');
  assert.equal(twoBtn.getAttribute('aria-pressed'), 'false');
});

test('two mounted controls stay in sync after a click', () => {
  const { layout } = makeSandbox({ seed: [['nv.layout', 'list']] });
  const a = layout.mount(null);
  const b = layout.mount(null);

  a.children[1].click();

  assert.equal(a.children[1].getAttribute('aria-pressed'), 'true');
  assert.equal(b.children[1].getAttribute('aria-pressed'), 'true');
  assert.equal(a.children[0].getAttribute('aria-pressed'), 'false');
  assert.equal(b.children[0].getAttribute('aria-pressed'), 'false');
});

test('exported object has exactly the required keys', () => {
  const { layout } = makeSandbox();
  assert.deepEqual(Object.keys(layout).sort(), ['DEFAULT', 'MODES', 'apply', 'get', 'mount', 'normalise', 'set'].sort());
});
