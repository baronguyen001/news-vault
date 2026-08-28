import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'videos.js');
const source = fs.readFileSync(modulePath, 'utf8');

function makeEl(tag) {
  const el = {
    tagName: String(tag).toUpperCase(),
    className: '',
    textContent: '',
    type: '',
    src: '',
    alt: '',
    hidden: false,
    loading: '',
    decoding: '',
    referrerPolicy: '',
    onerror: null,
    children: [],
    parentNode: null,
    attrs: {},
    listeners: {},
    appendChild(child) { child.parentNode = this; this.children.push(child); return child; },
    removeChild(child) {
      const i = this.children.indexOf(child);
      if (i !== -1) { this.children.splice(i, 1); child.parentNode = null; }
      return child;
    },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    click() { (this.listeners.click || []).forEach((fn) => fn({ preventDefault() {} })); },
    querySelector(sel) { return find(this, sel); },
    get firstChild() { return this.children[0] || null; },
    get classList() {
      const self = this;
      return {
        add(...names) { self.className = (self.className + ' ' + names.join(' ')).trim(); },
        contains(name) { return self.className.split(/\s+/).indexOf(name) !== -1; },
        toggle(name, on) {
          const has = self.className.split(/\s+/).indexOf(name) !== -1;
          const want = on === undefined ? !has : !!on;
          if (want && !has) { self.className = (self.className + ' ' + name).trim(); }
          if (!want && has) {
            self.className = self.className.split(/\s+/).filter((c) => c !== name).join(' ');
          }
        },
      };
    },
  };
  return el;
}

function walk(node, out) {
  // Text nodes have no children array - createTextNode returns a bare object.
  for (const child of node.children || []) { out.push(child); walk(child, out); }
  return out;
}

function find(root, sel) {
  const name = sel.replace(/^\./, '');
  // A summary's runs append real text nodes, which have no className to match on.
  return walk(root, []).find(
    (el) => typeof el.className === 'string' && el.className.split(/\s+/).indexOf(name) !== -1,
  ) || null;
}

function load() {
  const document = {
    createElement: makeEl,
    createElementNS: (_namespace, tag) => makeEl(tag),
    createTextNode: (t) => ({ nodeType: 3, textContent: String(t) }),
  };
  const window = { document };
  const ctx = vm.createContext({ window, document, URL });
  vm.runInContext(source, ctx, { filename: modulePath });
  return { videos: ctx.window.NV.videos, document };
}

const SHORT = {
  id: 'aaaaaaaaaaa', sh: 1, t: 'Muot 45 giay', c: 'Kenh A', u: 'https://youtube.com/shorts/aaaaaaaaaaa',
  th: 'https://i.ytimg.com/vi/aaaaaaaaaaa/oar2.jpg', thf: 'https://i.ytimg.com/vi/aaaaaaaaaaa/hqdefault.jpg',
  ty: 'tech', p: '2026-06-18T21:00:00', bl: [{ k: 'p', r: [['Noi dung', false]] }],
};
const LONG = {
  id: 'bbbbbbbbbbb', t: 'Phong van 40 phut', c: 'Kenh B', u: 'https://youtube.com/watch?v=bbbbbbbbbbb',
  th: 'https://i.ytimg.com/vi/bbbbbbbbbbb/hqdefault.jpg', thf: '',
  ty: 'finance', p: '2026-06-18T19:00:00', bl: [{ k: 'p', r: [['Noi dung', false]] }],
};

test('a Short card has the short class', () => {
  const { videos } = load();
  assert.equal(videos.card(SHORT).classList.contains('card--short'), true);
});

test('a long card does not have the short class', () => {
  const { videos } = load();
  assert.equal(videos.card(LONG).classList.contains('card--short'), false);
});

test('a Short card has the literal Short badge', () => {
  const { videos } = load();
  assert.equal(videos.card(SHORT).querySelector('.badge--short').textContent, 'Short');
});

test('the Short badge precedes the YouTube badge', () => {
  const { videos } = load();
  const header = videos.card(SHORT).children[0];
  assert.equal(header.children[1].className, 'badge badge--short');
  assert.equal(header.children[2].className, 'badge badge--video');
});

test('a long card has no Short badge', () => {
  const { videos } = load();
  assert.equal(videos.card(LONG).querySelector('.badge--short'), null);
});

test('both cards retain their base classes', () => {
  const { videos } = load();
  for (const video of [SHORT, LONG]) {
    const classes = videos.card(video).className;
    assert.equal(classes.indexOf('card ') !== -1, true);
    assert.equal(classes.indexOf('card--video') !== -1, true);
    assert.equal(classes.indexOf('card--closed') !== -1, true);
  }
});

test('thumb sets image loading attributes', () => {
  const { videos, document } = load();
  const parent = document.createElement('div');
  const wrapper = videos.thumb(parent, SHORT.th, SHORT.t, '', SHORT.thf);
  const img = wrapper.children[0];
  assert.equal(img.loading, 'lazy');
  assert.equal(img.decoding, 'async');
  assert.equal(img.referrerPolicy, 'no-referrer');
});

test('a non-https primary URL renders a placeholder', () => {
  const { videos, document } = load();
  const parent = document.createElement('div');
  const wrapper = videos.thumb(parent, 'http://example.com/a.jpg', 'x', 'custom-thumb');
  assert.equal(wrapper.classList.contains('card__thumb--empty'), true);
  assert.equal(wrapper.classList.contains('custom-thumb'), true);
  assert.equal(parent.children.length, 1);
});

test('a non-https fallback is ignored', () => {
  const { videos, document } = load();
  const parent = document.createElement('div');
  const wrapper = videos.thumb(parent, SHORT.th, 'x', '', 'http://example.com/fallback.jpg');
  const img = wrapper.children[0];
  img.onerror();
  assert.equal(parent.children.length, 1);
  assert.equal(wrapper.classList.contains('card__thumb--empty'), true);
  assert.notEqual(img.src, 'http://example.com/fallback.jpg');
});

test('the first Short image error uses the fallback', () => {
  const { videos, document } = load();
  const parent = document.createElement('div');
  const wrapper = videos.thumb(parent, SHORT.th, 'x', '', SHORT.thf);
  const img = wrapper.children[0];
  img.onerror();
  assert.equal(img.src, SHORT.thf);
  assert.equal(parent.children.length, 1);
});

test('the second image error replaces the image with a placeholder', () => {
  const { videos, document } = load();
  const parent = document.createElement('div');
  const wrapper = videos.thumb(parent, SHORT.th, 'x', '', SHORT.thf);
  const img = wrapper.children[0];
  img.onerror();
  img.onerror();
  assert.equal(parent.children.length, 1);
  assert.equal(wrapper.parentNode, parent);
  assert.equal(wrapper.classList.contains('card__thumb--empty'), true);
  assert.equal(wrapper.children[0].tagName, 'SVG');
});

test('a missing fallback uses a placeholder on its first error', () => {
  const { videos, document } = load();
  const parent = document.createElement('div');
  const wrapper = videos.thumb(parent, LONG.th, 'x', '', LONG.thf);
  wrapper.children[0].onerror();
  assert.equal(parent.children.length, 1);
  assert.equal(wrapper.classList.contains('card__thumb--empty'), true);
});

test('the fallback is tried at most once', () => {
  const { videos, document } = load();
  const parent = document.createElement('div');
  const wrapper = videos.thumb(parent, SHORT.th, 'x', '', SHORT.thf);
  const img = wrapper.children[0];
  img.onerror();
  const fallback = img.src;
  img.onerror();
  assert.equal(img.src, fallback);
  assert.equal(parent.children.length, 1);
  assert.equal(wrapper.classList.contains('card__thumb--empty'), true);
});

test('a missing bl array does not throw', () => {
  const { videos } = load();
  assert.doesNotThrow(() => videos.card({ ...LONG, bl: undefined }));
});

test('a non-array bl value does not throw', () => {
  const { videos } = load();
  assert.doesNotThrow(() => videos.card({ ...LONG, bl: 'invalid' }));
});

test('section creates two video list items', () => {
  const { videos } = load();
  const sec = videos.section([SHORT, LONG]);
  const ul = sec.children[1];
  assert.equal(sec.tagName, 'SECTION');
  assert.equal(ul.tagName, 'UL');
  assert.equal(ul.children.length, 2);
});
