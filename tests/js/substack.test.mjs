import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'substack.js');
const source = fs.readFileSync(modulePath, 'utf8');

function makeEl(tag) {
  let _text = '';
  const el = {
    tagName: String(tag).toUpperCase(),
    className: '',
    value: '',
    href: '',
    target: '',
    rel: '',
    alt: '',
    src: '',
    hidden: false,
    children: [],
    childNodes: [],
    parentNode: null,
    attrs: {},
    listeners: {},
    // Real DOM: assigning textContent removes every existing child. renderIndex()'s
    // repaint relies on exactly this (`text(list, "")` before re-appending the filtered
    // cards) - a plain data property here would silently accumulate stale <li> across
    // repaints instead of replacing them.
    get textContent() { return _text; },
    set textContent(v) {
      _text = v == null ? '' : String(v);
      this.children.length = 0;
      this.childNodes.length = 0;
    },
    appendChild(child) {
      child.parentNode = this;
      this.children.push(child);
      this.childNodes.push(child);
      return child;
    },
    removeChild(child) {
      const i = this.children.indexOf(child);
      if (i !== -1) { this.children.splice(i, 1); child.parentNode = null; }
      const j = this.childNodes.indexOf(child);
      if (j !== -1) this.childNodes.splice(j, 1);
      return child;
    },
    insertBefore(child, ref) {
      const at = this.children.indexOf(ref);
      child.parentNode = this;
      if (at === -1) this.children.push(child);
      else this.children.splice(at, 0, child);
      this.childNodes = this.children;
      return child;
    },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    fire(type) { (this.listeners[type] || []).forEach((fn) => fn({})); },
    querySelector(sel) { return find(this, sel); },
    querySelectorAll(sel) { return findAll(this, sel); },
    get classList() {
      const self = this;
      return {
        add(...names) { self.className = (self.className + ' ' + names.join(' ')).trim(); },
        contains(name) { return self.className.split(/\s+/).indexOf(name) !== -1; },
      };
    },
  };
  return el;
}

function walk(node, out) {
  for (const child of node.children || []) { out.push(child); walk(child, out); }
  return out;
}

function find(root, sel) {
  const name = sel.replace(/^\./, '');
  return walk(root, []).find(
    (el) => typeof el.className === 'string' && el.className.split(/\s+/).indexOf(name) !== -1,
  ) || null;
}

function findAll(root, sel) {
  const name = sel.replace(/^\./, '');
  return walk(root, []).filter(
    (el) => typeof el.className === 'string' && el.className.split(/\s+/).indexOf(name) !== -1,
  );
}

function load() {
  const document = {
    createElement: makeEl,
    createTextNode: (t) => ({ nodeType: 3, textContent: String(t) }),
  };
  const window = { document };
  const ctx = vm.createContext({ window, document, URL });
  vm.runInContext(source, ctx, { filename: modulePath });
  return { substack: ctx.window.NV.substack, document };
}

const ESSAY = {
  id: '42',
  t: 'Vì sao quy trình rườm rà làm chậm việc ship',
  c: 'Tác giả A',
  u: 'https://a.substack.com/p/bai',
  d: '2026-08-20',
  p: '2026-08-20T09:00:00+00:00',
  lead: 'Một đoạn dẫn nhập ngắn.',
  w: 900,
  m: 5,
  ns: 3,
};

// --------------------------------------------------------------------------- teaserCard / thumb

test('a cover image renders when the essay carries a valid https img', () => {
  const { substack } = load();
  const card = substack.teaserCard(Object.assign({}, ESSAY, { img: 'https://cdn.example/cover.jpg' }), '../');
  const thumb = card.querySelector('.scard__thumb');
  assert.notEqual(thumb, null);
  assert.equal(thumb.tagName, 'IMG');
  assert.equal(thumb.src, 'https://cdn.example/cover.jpg');
});

test('no cover image element when img is absent', () => {
  const { substack } = load();
  const card = substack.teaserCard(ESSAY, '../');
  assert.equal(card.querySelector('.scard__thumb'), null);
});

test('a non-https img is rejected, not rendered', () => {
  const { substack } = load();
  const card = substack.teaserCard(Object.assign({}, ESSAY, { img: 'http://cdn.example/cover.jpg' }), '../');
  assert.equal(card.querySelector('.scard__thumb'), null);
});

test('a malformed img url is rejected without throwing', () => {
  const { substack } = load();
  assert.doesNotThrow(() => substack.teaserCard(Object.assign({}, ESSAY, { img: 'not a url' }), '../'));
});

// --------------------------------------------------------------------------- renderIndex filters

function renderTwo(extra1, extra2) {
  const { substack, document } = load();
  const app = makeEl('div');
  const items = [
    Object.assign({}, ESSAY, { id: '1', t: 'Bài về kinh tế vĩ mô', c: 'Nguyễn Văn A' }, extra1 || {}),
    Object.assign({}, ESSAY, { id: '2', t: 'Bài về AI và mô hình lớn', c: 'Trần Thị B' }, extra2 || {}),
  ];
  substack.renderIndex(app, { items }, { base: '../' });
  return { app, document };
}

test('the search box filters by title, diacritic-insensitively', () => {
  const { app } = renderTwo();
  const input = app.querySelector('.sublist__search');
  input.value = 'kinh te'; // no diacritics, must still match "kinh tế"
  input.fire('input');
  const titles = app.querySelectorAll('.scard__title').map((el) => el.textContent);
  assert.deepEqual(titles, ['Bài về kinh tế vĩ mô']);
});

test('the author select filters to exactly that author', () => {
  const { app } = renderTwo();
  const select = app.querySelector('.sublist__select');
  select.value = 'Trần Thị B';
  select.fire('change');
  const titles = app.querySelectorAll('.scard__title').map((el) => el.textContent);
  assert.deepEqual(titles, ['Bài về AI và mô hình lớn']);
});

test('a query matching nothing shows the empty-results message', () => {
  const { app } = renderTwo();
  const input = app.querySelector('.sublist__search');
  input.value = 'khong-ton-tai-xyz';
  input.fire('input');
  assert.equal(app.querySelector('.sublist__noresults').hidden, false);
  assert.equal(app.querySelectorAll('.scard').length, 0);
});

test('clear resets the search box, author filter and results', () => {
  const { app } = renderTwo();
  const input = app.querySelector('.sublist__search');
  input.value = 'khong-ton-tai-xyz';
  input.fire('input');
  assert.equal(app.querySelectorAll('.scard').length, 0);

  app.querySelector('.sublist__clear').fire('click');

  assert.equal(input.value, '');
  assert.equal(app.querySelectorAll('.scard').length, 2);
  assert.equal(app.querySelector('.sublist__noresults').hidden, true);
});

test('an empty item list renders no filter bar, just the empty message', () => {
  const { substack } = load();
  const app = makeEl('div');
  substack.renderIndex(app, { items: [] }, { base: '../' });
  assert.equal(app.querySelector('.sublist__controls'), null);
  assert.notEqual(app.querySelector('.sublist__empty'), null);
});
