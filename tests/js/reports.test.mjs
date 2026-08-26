import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'reports.js');
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
    hidden: false,
    children: [],
    childNodes: [],
    parentNode: null,
    attrs: {},
    listeners: {},
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
  const document = { createElement: makeEl };
  const thumbs = [];
  const window = {
    document,
    NV: {
      videos: {
        thumb(parent, url, alt) {
          if (typeof url !== 'string' || !url.startsWith('https:')) return null;
          thumbs.push({ url, alt });
          const wrapper = makeEl('div');
          wrapper.className = 'card__thumb';
          parent.appendChild(wrapper);
          return wrapper;
        },
      },
    },
  };
  const ctx = vm.createContext({ window, document });
  vm.runInContext(source, ctx, { filename: modulePath });
  return { reports: ctx.window.NV.reports, thumbs };
}

function renderTwo() {
  const { reports } = load();
  const app = makeEl('div');
  const items = [
    { t: 'Kinh tế Việt Nam quý 3', s: 'McKinsey Insights', p: '2026-08-10', pi: '2026-08-10T00:00:00+00:00', sum: 'Tóm tắt A' },
    { t: 'Chip AI và chuỗi cung ứng', s: 'SemiAnalysis', p: '2026-08-20', pi: '2026-08-20T00:00:00+00:00', sum: 'Tóm tắt B' },
  ];
  reports.renderIndex(app, { items }, { base: '../' });
  return { app };
}

test('an empty item list renders no filter bar, just the empty message', () => {
  const { reports } = load();
  const app = makeEl('div');
  reports.renderIndex(app, { items: [] }, { base: '../' });
  assert.equal(app.querySelector('.reports-index__controls'), null);
  assert.notEqual(app.querySelector('.reports-index__empty'), null);
});

test('the search box filters by title, diacritic-insensitively', () => {
  const { app } = renderTwo();
  const input = app.querySelector('.reports-index__search');
  input.value = 'kinh te';
  input.fire('input');
  const titles = app.querySelectorAll('.report-teaser__link').map((el) => el.textContent);
  assert.deepEqual(titles, ['Kinh tế Việt Nam quý 3']);
});

test('the source select filters to exactly that source', () => {
  const { app } = renderTwo();
  const select = app.querySelector('.reports-index__select');
  select.value = 'SemiAnalysis';
  select.fire('change');
  const titles = app.querySelectorAll('.report-teaser__link').map((el) => el.textContent);
  assert.deepEqual(titles, ['Chip AI và chuỗi cung ứng']);
});

test('a query matching nothing shows the empty-results message', () => {
  const { app } = renderTwo();
  const input = app.querySelector('.reports-index__search');
  input.value = 'khong-ton-tai-xyz';
  input.fire('input');
  assert.equal(app.querySelector('.reports-index__noresults').hidden, false);
  assert.equal(app.querySelectorAll('.report-teaser').length, 0);
});

test('clear resets the search box, source filter and results', () => {
  const { app } = renderTwo();
  const input = app.querySelector('.reports-index__search');
  input.value = 'khong-ton-tai-xyz';
  input.fire('input');
  assert.equal(app.querySelectorAll('.report-teaser').length, 0);

  app.querySelector('.reports-index__clear').fire('click');

  assert.equal(input.value, '');
  assert.equal(app.querySelectorAll('.report-teaser').length, 2);
  assert.equal(app.querySelector('.reports-index__noresults').hidden, true);
});

test('sorting oldest-first puts the earlier report first', () => {
  const { app } = renderTwo();
  const sortSelects = app.querySelectorAll('.reports-index__select');
  const sortSelect = sortSelects[1]; // source select is created first, sort select second
  sortSelect.value = 'oldest';
  sortSelect.fire('change');
  const titles = app.querySelectorAll('.report-teaser__link').map((el) => el.textContent);
  assert.deepEqual(titles, ['Kinh tế Việt Nam quý 3', 'Chip AI và chuỗi cung ứng']);
});

test('RSS teasers delegate available images to the shared thumbnail builder', () => {
  const { reports, thumbs } = load();
  const card = reports.teaserCard({
    t: 'Report with an image',
    img: 'https://cdn.example.test/report.jpg',
  });
  assert.equal(card.classList.contains('card'), true);
  assert.notEqual(card.querySelector('.card__thumb'), null);
  assert.deepEqual(thumbs, [{ url: 'https://cdn.example.test/report.jpg', alt: 'Report with an image' }]);
});
