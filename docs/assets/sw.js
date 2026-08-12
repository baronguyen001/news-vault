"use strict";

// Service Worker for news-vault
// Conservative offline cache. Encrypted .enc files are cached – they are useless without the password.
// Never cache cross-origin or non-200 responses.

const CACHE_NAME = "nv-cache-v1";
// Bumped whenever the shell asset list or its contents change: the activate handler
// deletes every "nv-" cache that is not one of the current names, so a returning
// reader gets the new stylesheet instead of last week's from cache.
const SHELL_CACHE = "nv-shell-v9";
const RUNTIME_CACHE = "nv-runtime-v1";
const MAX_RUNTIME = 400;

// Shell assets to pre-cache
const SHELL_URLS = [
  "/",
  "/manifest.json",
  "/assets/styles.css",
  "/assets/crypto.js",
  "/assets/unlock-store.js",
  "/assets/icons.js",
  "/assets/videos.js",
  "/assets/video-library.js",
  // curated.js was missing from this list until posts.js was added: the page loaded it
  // over the network every visit while every sibling came from cache.
  "/assets/curated.js",
  "/assets/posts.js",
  "/assets/search.js",
  "/assets/keyterms.js",
  "/assets/user.js",
  "/assets/share.js",
  "/assets/palette.js",
  "/assets/layout.js",
  "/assets/topics.js",
  "/assets/read.js",
  "/assets/modal.js",
  "/assets/app.js",
];

// Install: pre-cache shell, skip waiting
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => {
      return cache.addAll(SHELL_URLS);
    }).then(() => {
      return self.skipWaiting();
    })
  );
});

// Activate: delete old caches, claim clients
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key.startsWith("nv-") && key !== SHELL_CACHE && key !== RUNTIME_CACHE) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => {
      return self.clients.claim();
    })
  );
});

// Helper: evict oldest entries from runtime cache if over limit
async function evictIfNeeded(cache) {
  const requests = await cache.keys();
  if (requests.length > MAX_RUNTIME) {
    const toDelete = requests.slice(0, requests.length - MAX_RUNTIME);
    await Promise.all(toDelete.map((req) => cache.delete(req)));
  }
}

// Fetch strategy
self.addEventListener("fetch", (event) => {
  const request = event.request;

  // Only handle GET requests, same-origin
  if (request.method !== "GET") return;
  if (!request.url.startsWith(self.location.origin)) return;

  const url = new URL(request.url);
  const path = url.pathname;

  // Assets and manifest.webmanifest: stale-while-revalidate
  if (path.startsWith("/assets/") || path.endsWith("/manifest.webmanifest")) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const fetchPromise = fetch(request).then((response) => {
          if (response.status === 200 && response.type !== "opaque") {
            const cacheClone = response.clone();
            caches.open(SHELL_CACHE).then((cache) => {
              cache.put(request, cacheClone);
            });
          }
          return response;
        }).catch(() => cached);
        return cached || fetchPromise;
      })
    );
    return;
  }

  // .enc payloads and .webp images: cache-first with runtime cap
  if (path.endsWith(".enc") || path.endsWith(".webp")) {
    event.respondWith(
      caches.open(RUNTIME_CACHE).then((cache) => {
        return cache.match(request).then((cached) => {
          if (cached) {
            return cached;
          }
          return fetch(request).then((response) => {
            if (response.status === 200 && response.type !== "opaque") {
              const cacheClone = response.clone();
              cache.put(request, cacheClone).then(() => evictIfNeeded(cache));
            }
            return response;
          });
        });
      })
    );
    return;
  }

  // Navigations: network-first with shell fallback
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).then((response) => {
        if (response.status === 200 && response.type !== "opaque") {
          const cacheClone = response.clone();
          caches.open(SHELL_CACHE).then((cache) => {
            cache.put(request, cacheClone);
          });
        }
        return response;
      }).catch(() => {
        return caches.match(request).then((cached) => {
          if (cached) return cached;
          // Fallback to shell (root)
          return caches.match("/");
        });
      })
    );
    return;
  }

  // manifest.json: network-first (changes every build)
  if (path.endsWith("/manifest.json")) {
    event.respondWith(
      fetch(request).then((response) => {
        if (response.status === 200 && response.type !== "opaque") {
          const cacheClone = response.clone();
          caches.open(SHELL_CACHE).then((cache) => {
            cache.put(request, cacheClone);
          });
        }
        return response;
      }).catch(() => {
        return caches.match(request);
      })
    );
    return;
  }

  // Default: network-only (pass through)
  return;
});

// Message handler: clear all nv- caches
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "nv-clear-cache") {
    event.waitUntil(
      caches.keys().then((keys) => {
        return Promise.all(
          keys.map((key) => {
            if (key.startsWith("nv-")) {
              return caches.delete(key);
            }
          })
        );
      }).then(() => {
        if (event.ports && event.ports[0]) {
          event.ports[0].postMessage({ success: true });
        }
      })
    );
  }
});
