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
    // setOpen guards on nodeType, so a stub without it silently skips the inline fold.
    nodeType: 1,
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

const VIDEO = {
  id: 'bbbbbbbbbbb', t: 'Phong van 40 phut', c: 'Kenh B', u: 'https://youtube.com/watch?v=bbbbbbbbbbb',
  th: 'https://i.ytimg.com/vi/bbbbbbbbbbb/hqdefault.jpg', thf: '',
  ty: 'finance', p: '2026-06-18T19:00:00', bl: [{ k: 'p', r: [['Noi dung', false]] }],
};

function load(options = {}) {
  const document = {
    createElement: makeEl,
    createTextNode: (t) => ({ nodeType: 3, textContent: String(t) }),
  };
  const window = { document };
  const ctx = vm.createContext({ window, document, URL });
  vm.runInContext(source, ctx, { filename: modulePath });

  const opens = [];
  const nv = ctx.window.NV;

  if (options.pointerFine !== undefined) {
    nv.read = {
      pointerFine: options.pointerFine === 'throws'
        ? () => { throw new Error('pointerFine failed'); }
        : () => options.pointerFine,
    };
  }

  if (options.modal !== undefined) {
    nv.modal = options.modal === 'throws'
      ? { open() { throw new Error('modal failed'); } }
      : {
        open(config) {
          opens.push(config);
        },
      };
  }

  // The dialog's onClose is read off the recorded call rather than handed back here: a
  // destructured getter would capture null before the first click ever happens.
  return {
    videos: ctx.window.NV.videos,
    opens,
    document,
  };
}

test('useModal is false when neither NV.modal nor NV.read exists', () => {
  const { videos } = load();
  assert.equal(videos.useModal(), false);
});

test('useModal is false when NV.modal exists but NV.read does not', () => {
  const { videos } = load({ modal: true });
  assert.equal(videos.useModal(), false);
});

test('useModal is false when pointerFine returns false', () => {
  const { videos } = load({ modal: true, pointerFine: false });
  assert.equal(videos.useModal(), false);
});

test('useModal is true when NV.modal exists and pointerFine returns true', () => {
  const { videos } = load({ modal: true, pointerFine: true });
  assert.equal(videos.useModal(), true);
});

test('useModal is false and does not throw when pointerFine throws', () => {
  const { videos } = load({ modal: true, pointerFine: 'throws' });
  assert.doesNotThrow(() => videos.useModal());
  assert.equal(videos.useModal(), false);
});

test('fine pointer clicking card more calls NV.modal.open exactly once', () => {
  const { videos, opens } = load({ modal: true, pointerFine: true });
  const card = videos.card(VIDEO);
  card.querySelector('.card__more').click();
  assert.equal(opens.length, 1);
});

test('fine pointer passes the video title and body node to NV.modal.open', () => {
  const { videos, opens } = load({ modal: true, pointerFine: true });
  const card = videos.card(VIDEO);
  const body = card.querySelector('.card__body');
  card.querySelector('.card__more').click();
  assert.equal(opens[0].title, 'Phong van 40 phut');
  assert.equal(opens[0].node, body);
});

test('fine pointer keeps the card closed while the dialog is open', () => {
  const { videos, opens } = load({ modal: true, pointerFine: true });
  const card = videos.card(VIDEO);
  const button = card.querySelector('.card__more');
  const body = card.querySelector('.card__body');
  button.click();
  assert.equal(opens.length, 1);
  assert.equal(card.classList.contains('card--closed'), true);
  assert.equal(button.textContent, 'Xem thêm');
  assert.equal(button.getAttribute('aria-expanded'), 'true');
  assert.equal(body.hidden, false);
});

test('fine pointer onClose folds the card back', () => {
  const { videos, opens } = load({ modal: true, pointerFine: true });
  const card = videos.card(VIDEO);
  const button = card.querySelector('.card__more');
  const body = card.querySelector('.card__body');
  button.click();
  opens[0].onClose();
  assert.equal(card.classList.contains('card--closed'), true);
  assert.equal(body.hidden, true);
  assert.equal(button.textContent, 'Xem thêm');
  assert.equal(button.getAttribute('aria-expanded'), 'false');
});

test('fine pointer opens the dialog again after onClose', () => {
  const { videos, opens } = load({ modal: true, pointerFine: true });
  const card = videos.card(VIDEO);
  const button = card.querySelector('.card__more');
  button.click();
  opens[0].onClose();
  button.click();
  assert.equal(opens.length, 2);
});

test('coarse pointer unfolds the card inline', () => {
  const { videos, opens } = load({ modal: true, pointerFine: false });
  const card = videos.card(VIDEO);
  const button = card.querySelector('.card__more');
  const body = card.querySelector('.card__body');
  button.click();
  assert.equal(opens.length, 0);
  assert.equal(card.classList.contains('card--closed'), false);
  assert.equal(button.textContent, 'Thu gọn');
  assert.equal(body.hidden, false);
});

test('clicking without a modal unfolds the card inline', () => {
  const { videos, opens } = load();
  const card = videos.card(VIDEO);
  const button = card.querySelector('.card__more');
  button.click();
  assert.equal(opens.length, 0);
  assert.equal(card.classList.contains('card--closed'), false);
  assert.equal(button.textContent, 'Thu gọn');
});

test('an already open inline card collapses without opening the dialog', () => {
  const { videos, opens } = load({ modal: true, pointerFine: true });
  const card = videos.card(VIDEO);
  const button = card.querySelector('.card__more');
  videos.setOpen(card, true);
  button.click();
  assert.equal(opens.length, 0);
  assert.equal(card.classList.contains('card--closed'), true);
  assert.equal(button.textContent, 'Xem thêm');
  assert.equal(card.querySelector('.card__body').hidden, true);
});

test('a throwing modal unfolds the card inline', () => {
  const { videos, opens } = load({ modal: 'throws', pointerFine: true });
  const card = videos.card(VIDEO);
  const button = card.querySelector('.card__more');
  const body = card.querySelector('.card__body');
  assert.doesNotThrow(() => button.click());
  assert.equal(opens.length, 0);
  assert.equal(card.classList.contains('card--closed'), false);
  assert.equal(button.textContent, 'Thu gọn');
  assert.equal(body.hidden, false);
});

test('openModal returns false without a card body', () => {
  const { videos, document, opens } = load({ modal: true, pointerFine: true });
  const bare = document.createElement('li');
  assert.equal(videos.openModal(bare), false);
  assert.equal(opens.length, 0);
});

test('openModal passes an empty title when the card has no link', () => {
  const { videos, opens } = load({ modal: true, pointerFine: true });
  const card = videos.card(VIDEO);
  const title = card.querySelector('.card__title');
  title.parentNode.removeChild(title);
  assert.equal(videos.openModal(card), true);
  assert.equal(opens[0].title, '');
});
