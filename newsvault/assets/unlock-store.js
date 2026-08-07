"use strict";
window.NV = window.NV || {};

(function () {
  const DB_NAME = "nv-unlock";
  const STORE_NAME = "keys";
  const RECORD_ID = "site";

  function isSupported() {
    try {
      return typeof indexedDB !== "undefined" && indexedDB !== null;
    } catch (error) {
      return false;
    }
  }

  function openDatabase() {
    return new Promise(function (resolve) {
      if (!isSupported()) {
        resolve(null);
        return;
      }

      let request;
      try {
        request = indexedDB.open(DB_NAME, 1);
      } catch (error) {
        resolve(null);
        return;
      }

      request.onupgradeneeded = function () {
        try {
          const db = request.result;
          if (!db.objectStoreNames.contains(STORE_NAME)) {
            db.createObjectStore(STORE_NAME, { keyPath: "id" });
          }
        } catch (error) {
          // Upgrade failures are reported through the request error path.
        }
      };

      request.onsuccess = function () {
        resolve(request.result);
      };

      request.onerror = function () {
        resolve(null);
      };

      request.onblocked = function () {
        resolve(null);
      };
    });
  }

  function closeDatabase(db) {
    try {
      db.close();
    } catch (error) {
      // A failed close must not change the storage operation's result.
    }
  }

  function save(key, fingerprintValue) {
    return new Promise(function (resolve) {
      openDatabase().then(function (db) {
        if (!db) {
          resolve(false);
          return;
        }

        let settled = false;
        let transaction;
        try {
          transaction = db.transaction(STORE_NAME, "readwrite");
          transaction.oncomplete = function () {
            if (!settled) {
              settled = true;
              closeDatabase(db);
              resolve(true);
            }
          };
          transaction.onabort = function () {
            if (!settled) {
              settled = true;
              closeDatabase(db);
              resolve(false);
            }
          };
          transaction.onerror = function () {
            if (!settled) {
              settled = true;
              closeDatabase(db);
              resolve(false);
            }
          };
          transaction.objectStore(STORE_NAME).put({
            id: RECORD_ID,
            key: key,
            fingerprint: fingerprintValue,
          });
        } catch (error) {
          if (!settled) {
            settled = true;
            closeDatabase(db);
            resolve(false);
          }
        }
      }).catch(function () {
        resolve(false);
      });
    });
  }

  function load(fingerprintValue) {
    return new Promise(function (resolve) {
      openDatabase().then(function (db) {
        if (!db) {
          resolve(null);
          return;
        }

        let settled = false;
        let transaction;
        try {
          transaction = db.transaction(STORE_NAME, "readwrite");
          transaction.oncomplete = function () {
            if (!settled) {
              settled = true;
              closeDatabase(db);
              resolve(transaction.record || null);
            }
          };
          transaction.onabort = function () {
            if (!settled) {
              settled = true;
              closeDatabase(db);
              resolve(null);
            }
          };
          transaction.onerror = function () {
            if (!settled) {
              settled = true;
              closeDatabase(db);
              resolve(null);
            }
          };

          const store = transaction.objectStore(STORE_NAME);
          const request = store.get(RECORD_ID);
          request.onsuccess = function () {
            const record = request.result;
            if (!record || !record.key) {
              transaction.record = null;
            } else if (record.fingerprint === fingerprintValue) {
              transaction.record = record.key;
            } else {
              transaction.record = null;
              store.delete(RECORD_ID);
            }
          };
          request.onerror = function () {
            transaction.record = null;
          };
        } catch (error) {
          if (!settled) {
            settled = true;
            closeDatabase(db);
            resolve(null);
          }
        }
      }).catch(function () {
        resolve(null);
      });
    });
  }

  function clear() {
    return new Promise(function (resolve) {
      openDatabase().then(function (db) {
        if (!db) {
          resolve(false);
          return;
        }

        let settled = false;
        let transaction;
        try {
          transaction = db.transaction(STORE_NAME, "readwrite");
          transaction.oncomplete = function () {
            if (!settled) {
              settled = true;
              closeDatabase(db);
              resolve(true);
            }
          };
          transaction.onabort = function () {
            if (!settled) {
              settled = true;
              closeDatabase(db);
              resolve(false);
            }
          };
          transaction.onerror = function () {
            if (!settled) {
              settled = true;
              closeDatabase(db);
              resolve(false);
            }
          };
          transaction.objectStore(STORE_NAME).delete(RECORD_ID);
        } catch (error) {
          if (!settled) {
            settled = true;
            closeDatabase(db);
            resolve(false);
          }
        }
      }).catch(function () {
        resolve(false);
      });
    });
  }

  window.NV.unlockStore = {
    DB_NAME: DB_NAME,
    STORE_NAME: STORE_NAME,
    RECORD_ID: RECORD_ID,
    isSupported: isSupported,
    save: save,
    load: function (fingerprintValue) {
      return load(fingerprintValue);
    },
    clear: clear,
    fingerprint: function (salt, iterations) {
      return salt + ":" + iterations;
    },
  };
})();
