import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'indie.js');
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

function load(videos) {
  const document = {
    createElement: makeEl,
    createTextNode: (t) => ({ nodeType: 3, textContent: String(t) }),
  };
  const window = {
    document,
    NV: {
      app: {
        blocksInto(parent, blocks, options) {
          const list = Array.isArray(blocks) ? blocks : [];
          for (const block of list) {
            const kind = block && (block.k || block.kind) === 'h' ? 'h4' : 'p';
            const cls = kind === 'h4' ? options.headingClass : options.paragraphClass;
            const el = makeEl(kind);
            el.className = cls || '';
            el.textContent = ((block && block.r) || [])
              .map((run) => Array.isArray(run) ? run[0] : '').join('');
            parent.appendChild(el);
          }
        },
      },
    },
  };
  if (videos) window.NV.videos = videos;
  const ctx = vm.createContext({ window, document, URL });
  vm.runInContext(source, ctx, { filename: modulePath });
  return { indie: ctx.window.NV.indie };
}

function renderTwo() {
  const { indie } = load();
  const app = makeEl('div');
  const items = [
    { au: 'nguoia', an: 'Người A', vi: 'Ra mắt SaaS mới cho freelancer', u: 'https://x.com/nguoia/status/1', p: '2026-08-10T00:00:00+00:00', lk: 10, rt: 2 },
    { au: 'nguoib', an: 'Người B', vi: 'Chạm mốc MRR 5k USD', u: 'https://x.com/nguoib/status/2', p: '2026-08-20T00:00:00+00:00', lk: 20, rt: 4 },
  ];
  indie.renderIndex(app, { items }, { base: '../' });
  return { app };
}

test('an empty item list renders no filter bar, just the empty message', () => {
  const { indie } = load();
  const app = makeEl('div');
  indie.renderIndex(app, { items: [] }, { base: '../' });
  assert.equal(app.querySelector('.ilist__controls'), null);
  assert.notEqual(app.querySelector('.ilist__empty'), null);
});

test('the search box filters by post text', () => {
  const { app } = renderTwo();
  const input = app.querySelector('.ilist__search');
  input.value = 'MRR';
  input.fire('input');
  const bodies = app.querySelectorAll('.ipost__paragraph').map((el) => el.textContent);
  assert.deepEqual(bodies, ['Chạm mốc MRR 5k USD']);
});

test('the author select filters to exactly that author', () => {
  const { app } = renderTwo();
  const select = app.querySelector('.ilist__select');
  select.value = 'nguoia';
  select.fire('change');
  const bodies = app.querySelectorAll('.ipost__paragraph').map((el) => el.textContent);
  assert.deepEqual(bodies, ['Ra mắt SaaS mới cho freelancer']);
});

test('a query matching nothing shows the empty-results message', () => {
  const { app } = renderTwo();
  const input = app.querySelector('.ilist__search');
  input.value = 'khong-ton-tai-xyz';
  input.fire('input');
  assert.equal(app.querySelector('.ilist__noresults').hidden, false);
  assert.equal(app.querySelectorAll('.ipost').length, 0);
});

test('clear resets the search box, author filter and results', () => {
  const { app } = renderTwo();
  const input = app.querySelector('.ilist__search');
  input.value = 'khong-ton-tai-xyz';
  input.fire('input');
  assert.equal(app.querySelectorAll('.ipost').length, 0);

  app.querySelector('.ilist__clear').fire('click');

  assert.equal(input.value, '');
  assert.equal(app.querySelectorAll('.ipost').length, 2);
  assert.equal(app.querySelector('.ilist__noresults').hidden, true);
});

test('Indie cards use the shared card grid and thumbnail builder', () => {
  const thumbs = [];
  const { indie } = load({
    thumb(parent, url, alt) {
      if (typeof url !== 'string' || !url.startsWith('https:')) return null;
      thumbs.push({ url, alt });
      const wrapper = makeEl('div');
      wrapper.className = 'card__thumb';
      parent.appendChild(wrapper);
      return wrapper;
    },
  });
  const section = indie.section([
    { au: 'nguoia', an: 'Người A', vi: 'Ra mắt SaaS mới', u: 'https://x.com/1', img: 'https://pbs.twimg.com/x.jpg' },
  ]);
  const list = section.querySelector('.iposts__list');
  const card = section.querySelector('.ipost');
  assert.equal(section.classList.contains('cards-wrap'), true);
  assert.equal(list.classList.contains('cards'), true);
  assert.equal(card.classList.contains('card'), true);
  assert.notEqual(card.querySelector('.card__thumb'), null);
  assert.equal(thumbs.length, 1);
  assert.equal(thumbs[0].url, 'https://pbs.twimg.com/x.jpg');
});

test('legacy Indie text splits into real paragraphs', () => {
  const { indie } = load();
  const card = indie.card({ au: 'maker', vi: 'Đoạn một.\n\nĐoạn hai.' }, 0);
  assert.deepEqual(
    card.querySelectorAll('.ipost__paragraph').map((el) => el.textContent),
    ['Đoạn một.', 'Đoạn hai.'],
  );
});

test('sorting oldest-first puts the earlier post first', () => {
  const { app } = renderTwo();
  const selects = app.querySelectorAll('.ilist__select');
  const sortSelect = selects[1]; // author select is created first, sort select second
  sortSelect.value = 'oldest';
  sortSelect.fire('change');
  const bodies = app.querySelectorAll('.ipost__paragraph').map((el) => el.textContent);
  assert.deepEqual(bodies, ['Ra mắt SaaS mới cho freelancer', 'Chạm mốc MRR 5k USD']);
});
