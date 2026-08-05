"use strict";
window.NV = window.NV || {};

/* Deciding when an article counts as "read".
 *
 * The rule used to be one IntersectionObserver: 50% visible for two seconds and the card
 * was read. On a desktop that marks the whole first screen read while the reader is still
 * looking at the top of it. Pointer type is what separates the two honest signals:
 *
 *   fine pointer  - the reader rests the mouse on a card for two seconds;
 *   coarse pointer - the reader scrolls the card up and off the top of the viewport.
 *
 * Leaving through the bottom never counts: that is the reader scrolling back up. */
(function () {
  const DEFAULT_DELAY_MS = 2000;
  const DESKTOP_QUERY = "(hover: hover) and (pointer: fine)";

  // Page-lifetime state. Keyed by element so a re-render's discarded cards are collected.
  const readCards = new WeakSet();
  const hoverCards = new WeakSet();
  const hoverTimers = new WeakMap();
  const scrollStates = new WeakMap();

  function pointerFine() {
    if (typeof window.matchMedia !== "function") {
      return false;
    }

    try {
      return window.matchMedia(DESKTOP_QUERY).matches === true;
    } catch (error) {
      return false;
    }
  }

  function mode() {
    return pointerFine() ? "hover" : "scroll";
  }

  function defaultUrlOf(card) {
    const link = card.querySelector(".card__link");
    return link ? link.href : "";
  }

  function observe(cards, opts) {
    const options = opts || {};
    const actualMode = options.mode === "hover" || options.mode === "scroll"
      ? options.mode
      : mode();
    const delayMs = options.delayMs === undefined
      ? DEFAULT_DELAY_MS
      : options.delayMs;
    const onRead = typeof options.onRead === "function" ? options.onRead : null;
    const urlOf = typeof options.urlOf === "function" ? options.urlOf : defaultUrlOf;
    const addedCards = [];
    let observer = null;
    let disconnected = false;

    if (actualMode === "hover") {
      if (cards && typeof cards.length === "number") {
        for (let index = 0; index < cards.length; index += 1) {
          const card = cards[index];

          if (!card || typeof card.addEventListener !== "function" ||
              hoverCards.has(card)) {
            continue;
          }

          const enter = function () {
            if (readCards.has(card)) {
              return;
            }

            const oldTimer = hoverTimers.get(card);
            if (oldTimer !== undefined) {
              clearTimeout(oldTimer);
            }

            const timer = setTimeout(function () {
              hoverTimers.delete(card);

              if (readCards.has(card)) {
                return;
              }

              const url = urlOf(card);
              if (!url) {
                return;
              }

              readCards.add(card);
              if (onRead) {
                onRead(url, card);
              }
            }, delayMs);

            hoverTimers.set(card, timer);
          };
          const leave = function () {
            const timer = hoverTimers.get(card);
            if (timer !== undefined) {
              clearTimeout(timer);
              hoverTimers.delete(card);
            }
          };

          card.addEventListener("mouseenter", enter);
          card.addEventListener("mouseleave", leave);
          hoverCards.add(card);
          addedCards.push({ card: card, enter: enter, leave: leave });
        }
      }
    } else if (typeof window.IntersectionObserver === "function") {
      observer = new window.IntersectionObserver(function (entries) {
        for (let index = 0; index < entries.length; index += 1) {
          const entry = entries[index];
          const card = entry.target;
          const state = scrollStates.get(card);

          if (!state || state.observer !== observer || state.done) {
            continue;
          }

          if (entry.isIntersecting === true && entry.intersectionRatio >= 0.5) {
            state.seen = true;
            continue;
          }

          if (entry.isIntersecting === false && state.seen) {
            // rootBounds is null in some browsers when the root is the viewport, hence
            // the fallback to the viewport's own top edge.
            const topLine = entry.rootBounds ? entry.rootBounds.top : 0;
            if (entry.boundingClientRect.bottom <= topLine) {
              const url = urlOf(card);
              state.done = true;
              observer.unobserve(card);

              if (url && !readCards.has(card)) {
                readCards.add(card);
                if (onRead) {
                  onRead(url, card);
                }
              }
            }
          }
        }
      }, { threshold: [0, 0.5] });

      if (cards && typeof cards.length === "number") {
        for (let index = 0; index < cards.length; index += 1) {
          const card = cards[index];

          if (!card || scrollStates.has(card)) {
            continue;
          }

          scrollStates.set(card, {
            seen: false,
            done: readCards.has(card),
            observer: observer
          });
          observer.observe(card);
          addedCards.push(card);
        }
      }
    }

    return {
      mode: actualMode,
      disconnect: function () {
        if (disconnected) {
          return;
        }
        disconnected = true;

        for (let index = 0; index < addedCards.length; index += 1) {
          const item = addedCards[index];

          if (actualMode === "hover") {
            const timer = hoverTimers.get(item.card);
            if (timer !== undefined) {
              clearTimeout(timer);
              hoverTimers.delete(item.card);
            }
            item.card.removeEventListener("mouseenter", item.enter);
            item.card.removeEventListener("mouseleave", item.leave);
            hoverCards.delete(item.card);
          } else {
            const state = scrollStates.get(item);
            if (state && state.observer === observer) {
              observer.unobserve(item);
              scrollStates.delete(item);
            }
          }
        }

        if (observer) {
          observer.disconnect();
        }
      }
    };
  }

  NV.read = {
    MODE_HOVER: "hover",
    MODE_SCROLL: "scroll",
    DEFAULT_DELAY_MS: DEFAULT_DELAY_MS,
    pointerFine: pointerFine,
    mode: mode,
    observe: observe
  };
})();
