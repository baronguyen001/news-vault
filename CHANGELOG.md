# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-08-04

### Changed
- **AI Hub is now the default illustration provider**, with Gemini as the automatic fallback
  (`NEWSVAULT_IMAGE_PROVIDER`). Already-generated images are cached on prompt and size, so the
  existing archive keeps its current artwork and only new days are drawn by the hub. The trade-off is
  documented rather than hidden: `orchestration` rewrites the prompt before drawing, so house-style
  adherence varies run to run — its ceiling is higher than Gemini's and its floor is lower.
- Entity and week pages now carry a header with links home and to the latest day. They were
  navigational dead ends.

### Fixed
- **The image prompt was sending real article headlines to the image API.** The 0.2.0 rewrite of
  `images.py` stopped calling `newsvault.prompts` and built its own prompt with the day's Vietnamese
  headlines embedded as "Story cues". That both destroyed the locked house style — the model drew the
  headlines into the picture as misspelled text — and shipped the content of a deliberately private
  archive to a third-party endpoint. `plan_images` uses `newsvault.prompts` again, and a test now
  asserts that no generated prompt contains a headline or any Vietnamese character at all.
- **77 of the 126 CSS classes the application emits had no rule at all.** Whole components rendered as
  browser defaults: the command palette opened as a blank white overlay, the watchlist dialog had no
  box, archive search results were bare text, and value/label pairs ran together as `193Tổng số bài`
  and `Chính trị/Chính sáchhôm nay 18%`. All of them are styled now, mobile-first.
- The overlay scrim was mixed from `--bg`, which in the light theme is the same white as the page it
  was meant to dim — the palette and dialog were invisible. Added a dedicated `--scrim` token per theme.
- The home calendar placed every date one weekday column off: the header starts on Sunday while the
  leading pad was computed Monday-first. It also skipped days with no articles entirely, which shifted
  every following date. Every date of the month is now rendered, quiet days included but inert.
- The sort select and the archive-search button kept the browser's default chrome, rendering white on
  white in dark mode.
- The month grid collapsed into a single column on a phone, and short wide charts were letterboxed
  into tall empty boxes with ~6px labels — both regressions from the previous release's touch-target
  and chart-sizing rules.

## [0.2.0] - 2026-08-04

### Added
- Illustrations can be drawn by the **MK1 AI Hub** (`POST /v1/images/generations`, model
  `orchestration`) as well as Gemini, selected with `NEWSVAULT_IMAGE_PROVIDER`. Gemini stays the
  default: the hub's `orchestration` model rewrites the prompt before drawing, and on the same locked
  house-style brief it produced a clean editorial vector on one run and a tourism poster with rendered
  text and a national flag on the next — unusable variance for an archive built on visual coherence.
- Automatic cross-provider fallback: when the configured back-end fails — a rate limit, a text-only
  model, a missing key — the other one is tried once, so a dead provider costs a picture, not a build.
  The image cache stays keyed on prompt and size only, so switching providers never orphans an
  existing archive.
- Measured mobile layout: a Playwright pass across iPhone SE / iPhone 14 / Android / tablet asserting
  no horizontal page scroll and a 44px minimum for every interactive control.

### Changed
- The header no longer stacks its six action buttons vertically on a phone, where it consumed an
  entire screen before the first headline. It is now two compact rows with a horizontally scrolling
  action strip.
- Category cards show the label and count on separate lines and no longer repeat the label as a
  caption.

### Fixed
- The search input collapsed to 4px wide on a 360px screen: `flex: 1; min-width: 0` let the sort
  select and the archive button squeeze it out. It now takes a row of its own below 720px.
- Tags rendered as bare 15px-wide anchors; they are chips now.
- Server-rendered charts stretched to fill their container because an SVG with only a `viewBox` has no
  intrinsic width. Their height is pinned instead.
- The section heading inside the category grid occupied a grid cell and pushed the first card sideways.

## [0.1.0] - 2026-08-04

First release.

### Added
- Read-only reader over a news-hunter SQLite database, with normalisation of the free-text
  `published_at`, `impact_level`, `key_points`, `tags` and `analysis` columns.
- Composite 0–100 article score from relevance, impact level and source tier.
- Deterministic same-story clustering (title-token Jaccard within a topic, union-find).
- Entity index built from the tag column, with a generated page per recurring entity.
- Trending terms (z-score against a 7-day baseline) and blind spots (topic share against a 30-day
  baseline).
- Server-rendered SVG charts that carry no JavaScript and follow the visitor's theme.
- AES-256-GCM payload container with PBKDF2-HMAC-SHA256 key derivation, decrypted in the browser via
  WebCrypto; payloads are zlib-compressed before encryption.
- Static site generator: landing page with a calendar heat map, one folder per day, entity pages,
  weekly roll-ups and monthly search-index shards.
- Browser application: password gate, diacritic-insensitive Vietnamese search across the archive,
  search operators, quick filters, cluster disclosure, `⌘K` command palette, saved articles, keyword
  watchlist, read tracking, theme toggle, offline service worker, Markdown export, print-to-PDF and
  canvas share cards — vanilla JavaScript with no external dependency.
- Gemini-backed daily brief with a deterministic fallback, and Gemini-backed category illustrations
  under a fixed house style; both cached by content hash and both fail soft.
- Metadata-only Atom and JSON feeds, with an explicit opt-in flag for full-content feeds.
- Optional spoken digest behind the `audio` extra, disabled by default.
- Incremental rebuilds via per-page content hashes and a stable site salt, keeping daily commits small.
- `newsvault` CLI: `build`, `rekey`, `export`, `days`, `verify`.

### Security
- The generated HTML contains no article text; everything readable is inside the encrypted payloads.
- `robots.txt` disallows all crawlers and every page is marked `noindex`.
- The publish script aborts when the site password appears anywhere under the output directory.
