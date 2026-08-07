import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'user.js');
const source = fs.readFileSync(modulePath, 'utf8');

function makeSandbox(preload = {}) {
  const storage = new Map(Object.entries(preload));
  const localStorage = {
    getItem(key) {
      return storage.has(key) ? storage.get(key) : null;
    },
    setItem(key, value) {
      storage.set(key, String(value));
    },
    removeItem(key) {
      storage.delete(key);
    },
  };
  const sandbox = {
    localStorage,
    document: {
      documentElement: {
        dataset: {},
      },
    },
    NV: {},
    Date,
  };
  sandbox.window = sandbox;
  return { sandbox, storage };
}

function recorder(user) {
  const events = [];
  user.on('change', (...args) => {
    events.push({ event: 'change', args });
  });
  user.on('read', (...args) => {
    events.push({ event: 'read', args });
  });
  user.on('theme', (...args) => {
    events.push({ event: 'theme', args });
  });
  user.on('watchlist', (...args) => {
    events.push({ event: 'watchlist', args });
  });
  return events;
}

function loadUser(preload = {}) {
  const context = makeSandbox(preload);
  vm.runInNewContext(source, context.sandbox);
  return {
    user: context.sandbox.NV.user,
    storage: context.storage,
  };
}

test('markRead emits exactly one read event with the URL', () => {
  const { user } = loadUser();
  const events = recorder(user);

  user.markRead('/article/one');

  assert.deepEqual(events, [
    { event: 'read', args: ['/article/one'] },
  ]);
});

test('markRead never emits the generic change event', () => {
  const { user } = loadUser();
  const events = recorder(user);

  user.markRead('/article/one');

  assert.equal(events.filter((entry) => entry.event === 'change').length, 0);
});

test('markRead on an already-read URL emits nothing', () => {
  const { user } = loadUser();
  const events = recorder(user);

  user.markRead('/article/one');
  events.length = 0;
  user.markRead('/article/one');

  assert.deepEqual(events, []);
});

test('markRead persists the read URL without emitting change', () => {
  const { user, storage } = loadUser();
  const events = recorder(user);

  user.markRead('/article/one');

  assert.equal(storage.get('nv.read'), '["/article/one"]');
  assert.equal(events.some((entry) => entry.event === 'change'), false);
});

test('isRead changes from false to true after markRead', () => {
  const { user } = loadUser();

  assert.equal(user.isRead('/article/one'), false);
  user.markRead('/article/one');
  assert.equal(user.isRead('/article/one'), true);
});

test('toggleSave emits change when saving and unsaving, but never read', () => {
  const { user } = loadUser();
  const events = recorder(user);

  assert.equal(user.toggleSave('/article/one'), true);
  assert.equal(user.toggleSave('/article/one'), false);

  assert.deepEqual(events, [
    { event: 'change', args: [] },
    { event: 'change', args: [] },
  ]);
});

test('clearRead emits change and clears previously read URLs', () => {
  const { user } = loadUser();
  const events = recorder(user);

  user.markRead('/article/one');
  events.length = 0;
  user.clearRead();

  assert.equal(user.isRead('/article/one'), false);
  assert.deepEqual(events, [
    { event: 'change', args: [] },
  ]);
});

test('marking many articles emits ordered read events and no change events', () => {
  const { user } = loadUser();
  const events = recorder(user);
  const urls = Array.from({ length: 50 }, (_, index) => `/article/${index}`);

  urls.forEach((url) => user.markRead(url));

  assert.deepEqual(
    events.filter((entry) => entry.event === 'read').map((entry) => entry.args[0]),
    urls,
  );
  assert.equal(events.some((entry) => entry.event === 'change'), false);
});

test('the read set is capped at 5000 and drops the oldest URLs', () => {
  const { user, storage } = loadUser();
  const urls = Array.from({ length: 5001 }, (_, index) => `/article/${index}`);

  urls.forEach((url) => user.markRead(url));

  const persisted = JSON.parse(storage.get('nv.read'));
  assert.equal(persisted.length, 5000);
  assert.equal(persisted[0], '/article/1');
  assert.equal(persisted[persisted.length - 1], '/article/5000');
  assert.equal(persisted.includes('/article/0'), false);
  assert.equal(user.isRead('/article/0'), false);
  assert.equal(user.isRead('/article/1'), true);
  assert.equal(user.isRead('/article/5000'), true);
});

test('init restores a preloaded read history', () => {
  const { user } = loadUser({
    'nv.read': JSON.stringify(['/article/one', '/article/two']),
  });

  user.init();

  assert.equal(user.isRead('/article/one'), true);
  assert.equal(user.isRead('/article/two'), true);
  assert.equal(user.stats().read, 2);
});

test('init tolerates corrupt read storage and leaves an empty read set', () => {
  const { user } = loadUser({
    'nv.read': 'not valid JSON',
  });

  assert.doesNotThrow(() => user.init());
  assert.equal(user.stats().read, 0);
  assert.equal(user.isRead('/article/one'), false);
});

test('setTheme emits theme only and setWatchlist emits watchlist then change', () => {
  const { user } = loadUser();
  const events = recorder(user);

  user.setTheme('dark');
  user.setWatchlist(['technology', 'science']);

  assert.deepEqual(events, [
    { event: 'theme', args: ['dark'] },
    { event: 'watchlist', args: [] },
    { event: 'change', args: [] },
  ]);
});

test('a throwing handler does not stop other handlers for the same event', () => {
  const { user } = loadUser();
  const events = recorder(user);
  let secondHandlerCalled = false;

  user.on('read', () => {
    throw new Error('handler failure');
  });
  user.on('read', () => {
    secondHandlerCalled = true;
  });

  user.markRead('/article/one');

  assert.equal(secondHandlerCalled, true);
  assert.deepEqual(events, [
    { event: 'read', args: ['/article/one'] },
  ]);
});
