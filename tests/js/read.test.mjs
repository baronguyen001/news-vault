import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'read.js');
const source = fs.readFileSync(modulePath, 'utf8');

function makeSandbox(options = {}) {
  let now = 0;
  let nextTimer = 1;
  const timers = new Map();
  const observerRecords = [];
  const window = { NV: {} };

  function setTimeoutFake(callback, delay) {
    const id = nextTimer++;
    timers.set(id, { callback, time: now + delay });
    return id;
  }

  function clearTimeoutFake(id) {
    timers.delete(id);
  }

  function advance(ms) {
    now += ms;
    let found = true;
    while (found) {
      found = false;
      for (const [id, timer] of timers) {
        if (timer.time <= now) {
          timers.delete(id);
          timer.callback();
          found = true;
          break;
        }
      }
    }
  }

  function makeCard(href) {
    const listeners = {};
    const card = {
      className: "card",
      listeners,
      addEventListener(type, callback) {
        listeners[type] = listeners[type] || [];
        listeners[type].push(callback);
      },
      removeEventListener(type, callback) {
        listeners[type] = (listeners[type] || []).filter((item) => item !== callback);
      },
      querySelector(selector) {
        if (selector === ".card__link" && href) {
          return { href };
        }
        return null;
      },
      emit(type) {
        for (const callback of listeners[type] || []) {
          callback();
        }
      }
    };
    return card;
  }

  if (options.includeMatchMedia !== false) {
    window.matchMedia = () => ({ matches: options.pointerFine === true });
  }

  if (options.includeIntersectionObserver !== false) {
    window.IntersectionObserver = class {
      constructor(callback, observerOptions) {
        this.callback = callback;
        this.options = observerOptions;
        this.observed = [];
        this.unobserved = [];
        this.disconnected = false;
        observerRecords.push(this);
      }

      observe(card) {
        this.observed.push(card);
      }

      unobserve(card) {
        this.unobserved.push(card);
      }

      disconnect() {
        this.disconnected = true;
      }

      push(entries) {
        this.callback(entries);
      }
    };
  }

  const ctx = {
    window,
    NV: window.NV,
    setTimeout: setTimeoutFake,
    clearTimeout: clearTimeoutFake
  };
  vm.createContext(ctx);
  vm.runInContext(source, ctx, { filename: modulePath });

  return {
    read: ctx.window.NV.read,
    makeCard,
    advance,
    observerRecords
  };
}

test("mode uses the fine pointer and falls back to scroll", () => {
  assert.equal(makeSandbox({ pointerFine: true }).read.mode(), "hover");
  assert.equal(makeSandbox({ pointerFine: false }).read.mode(), "scroll");
  assert.equal(
    makeSandbox({ pointerFine: true, includeMatchMedia: false }).read.mode(),
    "scroll"
  );
});

test("hover reads a card after its dwell delay", () => {
  const sandbox = makeSandbox({ pointerFine: true });
  const card = sandbox.makeCard("https://example.test/a");
  const calls = [];
  sandbox.read.observe([card], { onRead: (url, item) => calls.push([url, item]) });
  card.emit("mouseenter");
  sandbox.advance(2001);
  assert.deepEqual(calls, [["https://example.test/a", card]]);
});

test("hover cancellation prevents a read", () => {
  const sandbox = makeSandbox({ pointerFine: true });
  const card = sandbox.makeCard("https://example.test/a");
  const calls = [];
  sandbox.read.observe([card], { onRead: (url) => calls.push(url) });
  card.emit("mouseenter");
  card.emit("mouseleave");
  sandbox.advance(3000);
  assert.deepEqual(calls, []);
});

test("hover cancellation does not shorten the next dwell", () => {
  const sandbox = makeSandbox({ pointerFine: true });
  const card = sandbox.makeCard("https://example.test/a");
  const calls = [];
  sandbox.read.observe([card], { onRead: (url) => calls.push(url) });
  card.emit("mouseenter");
  sandbox.advance(1000);
  card.emit("mouseleave");
  card.emit("mouseenter");
  sandbox.advance(1000);
  assert.deepEqual(calls, []);
  sandbox.advance(1000);
  assert.deepEqual(calls, ["https://example.test/a"]);
});

test("hover reads a completed dwell only once", () => {
  const sandbox = makeSandbox({ pointerFine: true });
  const card = sandbox.makeCard("https://example.test/a");
  const calls = [];
  sandbox.read.observe([card], { onRead: (url) => calls.push(url) });
  card.emit("mouseenter");
  sandbox.advance(2000);
  card.emit("mouseleave");
  card.emit("mouseenter");
  sandbox.advance(2000);
  assert.equal(calls.length, 1);
});

test("hover does not read a card without a link", () => {
  const sandbox = makeSandbox({ pointerFine: true });
  const card = sandbox.makeCard();
  const calls = [];
  sandbox.read.observe([card], { onRead: (url) => calls.push(url) });
  card.emit("mouseenter");
  sandbox.advance(2000);
  assert.deepEqual(calls, []);
});

test("hover observe is idempotent for the same card", () => {
  const sandbox = makeSandbox({ pointerFine: true });
  const card = sandbox.makeCard("https://example.test/a");
  const calls = [];
  sandbox.read.observe([card], { onRead: (url) => calls.push(url) });
  sandbox.read.observe([card], { onRead: (url) => calls.push(url) });
  card.emit("mouseenter");
  sandbox.advance(2000);
  assert.deepEqual(calls, ["https://example.test/a"]);
});

test("hover disconnect cancels pending work", () => {
  const sandbox = makeSandbox({ pointerFine: true });
  const card = sandbox.makeCard("https://example.test/a");
  const calls = [];
  const handle = sandbox.read.observe([card], { onRead: (url) => calls.push(url) });
  card.emit("mouseenter");
  handle.disconnect();
  sandbox.advance(3000);
  assert.deepEqual(calls, []);
});

test("hover delay can override the default", () => {
  const sandbox = makeSandbox({ pointerFine: true });
  const card = sandbox.makeCard("https://example.test/a");
  const calls = [];
  const handle = sandbox.read.observe([card], {
    delayMs: 500,
    onRead: (url) => calls.push(url)
  });
  assert.equal(handle.mode, "hover");
  assert.equal(sandbox.read.DEFAULT_DELAY_MS, 2000);
  card.emit("mouseenter");
  sandbox.advance(499);
  assert.deepEqual(calls, []);
  sandbox.advance(1);
  assert.deepEqual(calls, ["https://example.test/a"]);
});

test("scroll reads a seen card leaving through the top", () => {
  const sandbox = makeSandbox();
  const card = sandbox.makeCard("https://example.test/a");
  const calls = [];
  sandbox.read.observe([card], { mode: "scroll", onRead: (url) => calls.push(url) });
  const observer = sandbox.observerRecords[0];
  observer.push([{
    target: card,
    isIntersecting: true,
    intersectionRatio: 0.6
  }]);
  observer.push([{
    target: card,
    isIntersecting: false,
    boundingClientRect: { bottom: 0 },
    rootBounds: { top: 1, bottom: 700 }
  }]);
  assert.deepEqual(calls, ["https://example.test/a"]);
  assert.deepEqual(observer.unobserved, [card]);
});

test("scroll ignores an exit through the bottom", () => {
  const sandbox = makeSandbox();
  const card = sandbox.makeCard("https://example.test/a");
  const calls = [];
  sandbox.read.observe([card], { mode: "scroll", onRead: (url) => calls.push(url) });
  const observer = sandbox.observerRecords[0];
  observer.push([{ target: card, isIntersecting: true, intersectionRatio: 0.6 }]);
  observer.push([{
    target: card,
    isIntersecting: false,
    boundingClientRect: { top: 700, bottom: 900 },
    rootBounds: { top: 0, bottom: 600 }
  }]);
  assert.deepEqual(calls, []);
});

test("scroll ignores a never-seen card leaving through the top", () => {
  const sandbox = makeSandbox();
  const card = sandbox.makeCard("https://example.test/a");
  const calls = [];
  sandbox.read.observe([card], { mode: "scroll", onRead: (url) => calls.push(url) });
  sandbox.observerRecords[0].push([{
    target: card,
    isIntersecting: false,
    boundingClientRect: { bottom: -1 },
    rootBounds: { top: 0, bottom: 600 }
  }]);
  assert.deepEqual(calls, []);
});

test("scroll uses zero as the missing root top", () => {
  const sandbox = makeSandbox();
  const card = sandbox.makeCard("https://example.test/a");
  const calls = [];
  sandbox.read.observe([card], { mode: "scroll", onRead: (url) => calls.push(url) });
  const observer = sandbox.observerRecords[0];
  observer.push([{ target: card, isIntersecting: true, intersectionRatio: 0.5 }]);
  observer.push([{
    target: card,
    isIntersecting: false,
    boundingClientRect: { bottom: 0 },
    rootBounds: null
  }]);
  assert.deepEqual(calls, ["https://example.test/a"]);
});

test("scroll without IntersectionObserver is harmless", () => {
  const sandbox = makeSandbox({ includeIntersectionObserver: false });
  const card = sandbox.makeCard("https://example.test/a");
  const calls = [];
  const handle = sandbox.read.observe([card], {
    mode: "scroll",
    onRead: (url) => calls.push(url)
  });
  assert.doesNotThrow(() => handle.disconnect());
  assert.deepEqual(calls, []);
});

test("observe accepts missing and empty cards", () => {
  const sandbox = makeSandbox({ pointerFine: true });
  assert.doesNotThrow(() => sandbox.read.observe(undefined));
  assert.doesNotThrow(() => sandbox.read.observe([]));
});
