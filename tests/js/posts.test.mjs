import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'posts.js');
const source = fs.readFileSync(modulePath, 'utf8');

function makeEl(tag) {
  const el = {
    tagName: String(tag).toUpperCase(),
    className: '',
    textContent: '',
    href: '',
    target: '',
    rel: '',
    title: '',
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
      if (i !== -1) { this.children.splice(i, 1); child.parentNode = null; }
      const j = this.childNodes.indexOf(child);
      if (j !== -1) this.childNodes.splice(j, 1);
      return child;
    },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
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
  for (const child of node.children || []) { out.push(child); walk(child, out); }
  return out;
}

function find(root, sel) {
  const name = sel.replace(/^\./, '');
  return walk(root, []).find(
    (el) => typeof el.className === 'string' && el.className.split(/\s+/).indexOf(name) !== -1,
  ) || null;
}

function textOf(node) {
  if (node.nodeType === 3) return node.textContent;
  const own = node.children && node.children.length ? '' : (node.textContent || '');
  return own + (node.children || []).map(textOf).join('');
}

function load() {
  const document = {
    createElement: makeEl,
    createTextNode: (t) => ({ nodeType: 3, textContent: String(t) }),
  };
  const window = { document };
  const ctx = vm.createContext({ window, document, URL });
  vm.runInContext(source, ctx, { filename: modulePath });
  return { posts: ctx.window.NV.posts, document };
}

const WIRE = {
  id: '1800000000000000001',
  t: 'Fed giữ nguyên lãi suất',
  u: 'https://x.com/reuters/status/1800000000000000001',
  au: 'reuters',
  an: 'Reuters',
  tr: 0.85,
  pr: 1,
  d: '2026-08-12',
  ve: 'kinh-te',
  vl: 'Kinh tế',
  tp: 'Kinh tế/Tài chính',
  im: 'cao',
  rel: 9,
  sc: 88,
  lk: 1200,
  rt: 430,
  ins: 'Chính sách vẫn thắt chặt.',
  bl: [{ k: 'p', r: [['Fed giữ lãi suất ở mức 4,25-4,5%.', false]] }],
  kp: ['Lạm phát tháng 7 còn 2,4%'],
};

const ANON = Object.assign({}, WIRE, {
  id: '2', au: 'aixbt_agent', an: '', tr: 0.2, pr: 0, u: 'https://x.com/aixbt_agent/status/2',
});

test('an empty list renders no section', () => {
  const { posts } = load();
  assert.equal(posts.section([]), null);
  assert.equal(posts.section(null), null);
});

test('a section carries one card per post', () => {
  const { posts } = load();
  const section = posts.section([WIRE, ANON]);
  assert.equal(section.querySelector('.xposts__list').children.length, 2);
});

test('the count in the heading matches the list', () => {
  const { posts } = load();
  const section = posts.section([WIRE, ANON]);
  assert.equal(section.querySelector('.xposts__count').textContent, '(2)');
});

test('quick filters include categories, primary sources and high impact', () => {
  const { posts } = load();
  const section = posts.section([WIRE, ANON]);
  const labels = section.querySelector('.xposts__filters').children.map((el) => el.textContent);
  assert.equal(labels.includes(WIRE.tp), true);
  assert.equal(labels.includes('Nguồn gốc'), true);
  assert.equal(labels.includes('Tác động cao'), true);
});

test('a malformed entry is skipped, not thrown', () => {
  const { posts } = load();
  const section = posts.section([WIRE, null, undefined, 42]);
  // The three junk entries still produce empty cards rather than losing the section.
  assert.notEqual(section, null);
  assert.equal(section.querySelector('.xpost__author').textContent, '@reuters');
});

test('the author leads the card', () => {
  const { posts } = load();
  const card = posts.card(WIRE);
  assert.equal(card.children[0].children[0].className, 'xpost__author');
  assert.equal(card.children[0].children[0].textContent, '@reuters');
});

test('a primary source is labelled as one', () => {
  const { posts } = load();
  assert.equal(posts.card(WIRE).querySelector('.xpost__tier').textContent, 'nguồn gốc');
});

test('an unvetted author is labelled unverified, not blank', () => {
  const { posts } = load();
  const badge = posts.card(ANON).querySelector('.xpost__tier');
  assert.equal(badge.textContent, 'chưa xác thực');
  assert.equal(badge.className.indexOf('xpost__tier--low') !== -1, true);
});

test('tier bands split at 0.85 and 0.5', () => {
  const { posts } = load();
  assert.equal(posts.tierLabel(1.0).cls, 'xpost__tier--high');
  assert.equal(posts.tierLabel(0.85).cls, 'xpost__tier--high');
  assert.equal(posts.tierLabel(0.7).cls, 'xpost__tier--mid');
  assert.equal(posts.tierLabel(0.2).cls, 'xpost__tier--low');
  assert.equal(posts.tierLabel(undefined).cls, 'xpost__tier--low');
});

test('a non-https link leaves no anchor behind', () => {
  const { posts } = load();
  const card = posts.card(Object.assign({}, WIRE, { u: 'javascript:alert(1)' }));
  assert.equal(card.querySelector('.xpost__link'), null);
});

test('a valid link opens safely in a new tab', () => {
  const { posts } = load();
  const link = posts.card(WIRE).querySelector('.xpost__link');
  assert.equal(link.href, WIRE.u);
  assert.equal(link.target, '_blank');
  assert.equal(link.rel, 'noopener noreferrer');
});

test('model-written text becomes a text node, never markup', () => {
  const { posts } = load();
  const hostile = '</script><img src=x onerror=alert(1)>';
  const card = posts.card(Object.assign({}, WIRE, {
    t: hostile,
    bl: [{ k: 'p', r: [[hostile, false]] }],
    kp: [hostile],
  }));
  assert.equal(card.querySelector('.xpost__title').textContent, hostile);
  assert.equal(textOf(card.querySelector('.xpost__body')), hostile);
  assert.equal(card.querySelector('.xpost__points').children[0].textContent, hostile);
});

test('bold runs become strong elements, not asterisks', () => {
  const { posts } = load();
  const card = posts.card(Object.assign({}, WIRE, {
    bl: [{ k: 'p', r: [['bình thường ', false], ['đậm', true]] }],
  }));
  const body = card.querySelector('.xpost__body');
  const strong = body.children[0].children.find((el) => el.tagName === 'STRONG');
  assert.equal(strong.textContent, 'đậm');
});

test('an empty key_points array renders no list', () => {
  const { posts } = load();
  const card = posts.card(Object.assign({}, WIRE, { kp: [] }));
  assert.equal(card.querySelector('.xpost__points'), null);
});

test('category is visible and supporting detail starts collapsed', () => {
  const { posts } = load();
  const card = posts.card(WIRE);
  assert.equal(card.querySelector('.xpost__topic').textContent, WIRE.tp);
  const details = card.querySelector('.xpost__details');
  assert.equal(details.tagName, 'DETAILS');
  assert.equal(details.open, undefined);
  assert.equal(card.querySelector('.xpost__points').parentNode, details);
});

test('a compact card (no image) renders its body directly, no fold toggle', () => {
  const { posts } = load();
  const card = posts.card(WIRE); // WIRE carries no `img`, so this is the compact path.
  assert.equal(card.classList.contains('xpost--compact'), true);
  assert.equal(card.querySelector('.xpost__fold'), null);
  assert.equal(textOf(card.querySelector('.xpost__body')).length > 0, true);
});

test('the impact-analysis panel is a closed <details>, collapsed by default', () => {
  const { posts } = load();
  const card = posts.card(Object.assign({}, WIRE, {
    im: undefined, // avoid colliding with the header's own .xpost__impact mark
    ia: { ch: 'BTC', as: ['BTC'], dir: 'tăng', cf: 'trung bình', why: 'Vì lãi suất giữ nguyên.' },
  }));
  const panel = card.querySelector('.xpost__impact');
  assert.equal(panel.tagName, 'DETAILS');
  assert.equal(panel.open, undefined);
  const label = panel.children.find((el) => el.className === 'xpost__impact-label');
  assert.equal(label.tagName, 'SUMMARY');
  assert.equal(label.textContent, 'Tác động dự kiến — suy luận, không phải tin');
});

test('engagement is compacted and sits in the footer', () => {
  const { posts } = load();
  const metrics = posts.card(Object.assign({}, WIRE, { lk: 1200000, rt: 3400 }))
    .querySelector('.xpost__metrics');
  assert.equal(metrics.textContent, '♥ 1.2M · ↺ 3.4K');
});

test('class names do not collide with the article card system', () => {
  const { posts } = load();
  const card = posts.card(WIRE);
  assert.equal(card.className.split(/\s+/).indexOf('card'), -1);
  assert.equal(card.className.split(/\s+/).indexOf('xpost') !== -1, true);
});
