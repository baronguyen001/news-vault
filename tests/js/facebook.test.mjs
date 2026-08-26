import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'facebook.js');
const source = fs.readFileSync(modulePath, 'utf8');

function makeEl(tag) {
  let value = '';
  const el = {
    tagName: String(tag).toUpperCase(), className: '', children: [], childNodes: [], attrs: {},
    parentNode: null, hidden: false, listeners: {},
    get textContent() { return value; },
    set textContent(next) { value = next == null ? '' : String(next); this.children.length = 0; this.childNodes.length = 0; },
    appendChild(child) { child.parentNode = this; this.children.push(child); this.childNodes.push(child); return child; },
    setAttribute(key, next) { this.attrs[key] = String(next); },
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    querySelector(selector) { return find(this, selector); },
    get classList() { const self = this; return { contains(name) { return self.className.split(/\s+/).includes(name); } }; },
  };
  return el;
}

function walk(node, out) {
  for (const child of node.children || []) { out.push(child); walk(child, out); }
  return out;
}

function find(root, selector) {
  const name = selector.replace(/^\./, '');
  return walk(root, []).find((el) => el.className.split(/\s+/).includes(name)) || null;
}

function load() {
  const document = {
    createElement: makeEl,
    createTextNode(value) { return { textContent: String(value), children: [], childNodes: [] }; },
  };
  const thumbs = [];
  const window = {
    document,
    NV: { videos: { thumb(parent, url, alt) {
      if (typeof url !== 'string' || !url.startsWith('https:')) return null;
      thumbs.push({ url, alt });
      const wrapper = makeEl('div');
      wrapper.className = 'card__thumb';
      parent.appendChild(wrapper);
      return wrapper;
    } } },
  };
  const ctx = vm.createContext({ window, document, URL });
  vm.runInContext(source, ctx, { filename: modulePath });
  return { facebook: ctx.window.NV.facebook, thumbs };
}

test('Facebook cards use the shared card grid and thumbnail builder', () => {
  const { facebook, thumbs } = load();
  const section = facebook.section([{
    an: 'Author', c: 'AI', img: 'https://cdn.example.test/post.jpg',
    u: 'https://facebook.example.test/post', bl: [],
  }]);
  const list = section.querySelector('.fposts__list');
  const card = section.querySelector('.fpost');
  assert.equal(section.classList.contains('cards-wrap'), true);
  assert.equal(list.classList.contains('cards'), true);
  assert.equal(card.classList.contains('card'), true);
  assert.notEqual(card.querySelector('.card__thumb'), null);
  assert.equal(thumbs.length, 1);
  assert.equal(thumbs[0].url, 'https://cdn.example.test/post.jpg');
});
