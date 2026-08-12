import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'curated.js');
const source = fs.readFileSync(modulePath, 'utf8');

function makeEl(tag) {
  const el = {
    tagName: String(tag).toUpperCase(),
    className: '',
    textContent: '',
    href: '',
    children: [],
    childNodes: [],
    parentNode: null,
    attrs: {},
    appendChild(child) {
      child.parentNode = this;
      this.children.push(child);
      this.childNodes.push(child);
      return child;
    },
    removeChild(child) {
      const i = this.children.indexOf(child);
      if (i !== -1) {
        this.children.splice(i, 1);
        child.parentNode = null;
      }
      const j = this.childNodes.indexOf(child);
      if (j !== -1) this.childNodes.splice(j, 1);
      return child;
    },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) {
      return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null;
    },
    querySelector(sel) { return find(this, sel); },
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
  for (const child of node.children || []) {
    out.push(child);
    walk(child, out);
  }
  return out;
}

function findAll(root, sel) {
  const name = sel.replace(/^\./, '');
  return walk(root, []).filter(
    (el) => typeof el.className === 'string' && el.className.split(/\s+/).indexOf(name) !== -1,
  );
}

function find(root, sel) {
  return findAll(root, sel)[0] || null;
}

function load() {
  const document = {
    createElement: makeEl,
    createTextNode: (t) => ({ nodeType: 3, textContent: String(t), parentNode: null }),
  };
  const window = { document };
  const ctx = vm.createContext({ window, document, URL, encodeURIComponent });
  vm.runInContext(source, ctx, { filename: modulePath });
  return { curated: ctx.window.NV.curated, document };
}

const ITEM = {
  id: 'abc-1',
  t: 'Bài phân tích đầu tiên',
  c: 'Kinh tế',
  p: '2026-08-12',
  m: 12,
  lead: 'Phân tích các diễn biến quan trọng trong ngày.',
};

const SECOND_ITEM = Object.assign({}, ITEM, {
  id: 'abc-2',
  t: 'Bài phân tích thứ hai',
});

test('an empty list renders no section', () => {
  const { curated } = load();
  assert.equal(curated.daySection([]), null);
  assert.equal(curated.daySection(null), null);
});

test('a section carries one deep-dive card per item', () => {
  const { curated } = load();
  const section = curated.daySection([ITEM, SECOND_ITEM]);
  const list = section.querySelector('.deepteaser__list');
  assert.equal(list.classList.contains('dcards'), true);
  assert.equal(findAll(section, '.dcard').length, 2);
});

test('the heading and count retain the selector used by the day-page fold', () => {
  const { curated } = load();
  const section = curated.daySection([ITEM, SECOND_ITEM]);
  const heading = section.querySelector('.deepteaser__title');
  assert.notEqual(heading, null);
  assert.equal(heading.querySelector('.deepteaser__count').textContent, '(2)');
});

test('removing the section heading leaves the card list in place', () => {
  const { curated } = load();
  const section = curated.daySection([ITEM, SECOND_ITEM]);
  const heading = section.querySelector('.deepteaser__title');
  section.removeChild(heading);
  assert.equal(section.querySelector('.deepteaser__title'), null);
  assert.notEqual(section.querySelector('.deepteaser__list'), null);
});

test('card links use the supplied relative base and encoded id', () => {
  const { curated } = load();
  const section = curated.daySection([ITEM], '../../');
  assert.equal(section.querySelector('.dcard__link').href, '../../c/abc-1/');
});

test('malformed entries are tolerated without losing the section', () => {
  const { curated } = load();
  const section = curated.daySection([ITEM, null, 42]);
  assert.notEqual(section, null);
  assert.notEqual(section.querySelector('.dcard__title'), null);
});

test('model-written text lands as text, never markup', () => {
  const { curated } = load();
  const hostile = '</script><img src=x onerror=alert(1)>';
  const card = curated.teaserCard(Object.assign({}, ITEM, {
    t: hostile,
    lead: hostile,
  }), '../../');
  const title = card.querySelector('.dcard__title');
  const lead = card.querySelector('.dcard__lead');
  assert.equal(title.textContent, hostile);
  assert.equal(lead.textContent, hostile);
  assert.equal(Object.prototype.hasOwnProperty.call(title, 'innerHTML'), false);
  assert.equal(Object.prototype.hasOwnProperty.call(lead, 'innerHTML'), false);
});
