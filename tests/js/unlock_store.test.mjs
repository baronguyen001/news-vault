import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'unlock-store.js');
const source = fs.readFileSync(modulePath, 'utf8');

function createFakeIndexedDB(options = {}) {
  const records = new Map();
  let database;

  class Request {
    constructor() {
      this.result = undefined;
      this.onerror = null;
      this.onsuccess = null;
    }
  }

  class Transaction {
    constructor(mode) {
      this.mode = mode;
      this.oncomplete = null;
      this.onerror = null;
      this.onabort = null;
      this.settled = false;
      // A real transaction does not complete until every request made against it has
      // settled - and a request's onsuccess may enqueue another one, as the mismatch path
      // does when it deletes the stale record. Completing on a timer set at construction
      // would fire before the very callbacks that fill in the result.
      this.pending = 0;
      this.store = {
        put: (record) => this.request(() => {
          records.set(record.id, record);
        }),
        get: (id) => this.request(() => records.get(id)),
        delete: (id) => this.request(() => {
          records.delete(id);
        }),
      };
      this.scheduleCompletion();
    }

    scheduleCompletion() {
      setTimeout(() => {
        if (this.settled) return;
        if (this.pending > 0) {
          this.scheduleCompletion();
          return;
        }
        this.settled = true;
        if (options.abortTransactions) {
          if (this.onabort) this.onabort();
          return;
        }
        if (this.oncomplete) this.oncomplete();
      }, options.transactionDelay || 0);
    }

    request(action) {
      const request = new Request();
      this.pending += 1;
      setTimeout(() => {
        this.pending -= 1;
        if (options.abortTransactions) {
          if (!this.settled) {
            this.settled = true;
            if (this.onabort) this.onabort();
          }
          return;
        }
        request.result = action();
        if (request.onsuccess) request.onsuccess();
      }, options.requestDelay || 0);
      return request;
    }

    objectStore() {
      return this.store;
    }
  }

  database = {
    objectStoreNames: {
      contains: (name) => name === "keys" && database.hasStore,
    },
    hasStore: true,
    createObjectStore: () => {
      database.hasStore = true;
      return {};
    },
    transaction: (name, mode) => {
      if (!database.hasStore) {
        throw new Error("missing store");
      }
      return new Transaction(mode);
    },
    close: () => {
      database.closed = true;
    },
  };

  return {
    backingStore: records,
    open: () => {
      const request = new Request();
      setTimeout(() => {
        if (options.failOpen) {
          if (request.onerror) request.onerror();
          return;
        }
        request.result = database;
        if (!database.hasStore && request.onupgradeneeded) request.onupgradeneeded();
        if (request.onsuccess) request.onsuccess();
      }, 0);
      return request;
    },
  };
}

function loadStore(fake) {
  const sandbox = {
    window: { NV: {} },
    indexedDB: fake,
    setTimeout,
    queueMicrotask,
  };
  vm.runInNewContext(source, sandbox);
  return sandbox.window.NV.unlockStore;
}

test('fingerprint formats salt and iterations', () => {
  const store = loadStore(createFakeIndexedDB());
  assert.equal(store.fingerprint("abc", 250000), "abc:250000");
});

test('isSupported detects IndexedDB', () => {
  const fake = createFakeIndexedDB();
  assert.equal(loadStore(fake).isSupported(), true);
  const sandbox = { window: { NV: {} } };
  vm.runInNewContext(source, sandbox);
  assert.equal(sandbox.window.NV.unlockStore.isSupported(), false);
});

test('save and load return the identical key object', async () => {
  const store = loadStore(createFakeIndexedDB());
  const key = { opaque: true };
  assert.equal(await store.save(key, "fp"), true);
  assert.equal(await store.load("fp"), key);
});

test('mismatched fingerprint returns null', async () => {
  const fake = createFakeIndexedDB();
  const store = loadStore(fake);
  await store.save({ opaque: true }, "old");
  assert.equal(await store.load("new"), null);
});

test('mismatch removes the stale record', async () => {
  const fake = createFakeIndexedDB();
  const store = loadStore(fake);
  await store.save({ opaque: true }, "old");
  assert.equal(await store.load("new"), null);
  assert.equal(fake.backingStore.has("site"), false);
  assert.equal(await store.load("old"), null);
});

test('empty database loads null', async () => {
  const store = loadStore(createFakeIndexedDB());
  assert.equal(await store.load("fp"), null);
});

test('clear removes the record', async () => {
  const store = loadStore(createFakeIndexedDB());
  await store.save({ opaque: true }, "fp");
  assert.equal(await store.clear(), true);
  assert.equal(await store.load("fp"), null);
});

test('open failures never reject', async () => {
  const store = loadStore(createFakeIndexedDB({ failOpen: true }));
  assert.equal(await store.save({}, "fp"), false);
  assert.equal(await store.load("fp"), null);
  assert.equal(await store.clear(), false);
});

test('aborting transactions makes save fail', async () => {
  const store = loadStore(createFakeIndexedDB({ abortTransactions: true }));
  assert.equal(await store.save({}, "fp"), false);
});

test('save waits for transaction completion', async () => {
  const fake = createFakeIndexedDB({ transactionDelay: 30 });
  const store = loadStore(fake);
  const started = Date.now();
  const result = await store.save({}, "fp");
  assert.equal(result, true);
  assert.ok(Date.now() - started >= 20);
});
