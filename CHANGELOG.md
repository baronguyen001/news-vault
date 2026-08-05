# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.0] - 2026-08-05

### Fixed
- **Shorts no longer render as black rectangles.** The upstream summariser used to skip YouTube
  Shorts and now keeps them: **344 of the 802 videos in the archive are Shorts**. Their thumbnail was
  being requested from `hqdefault.jpg`, which is always 480x360, so a 9:16 clip came back pillarboxed
  — measured on real ids, the left edge pixel is `(0, 0, 0)` — and the fixed 16:9 crop then showed
  almost nothing but the black. A Short's picture now comes from `oar2.jpg`, the original-aspect
  frame, verified to exist for 20 of 20 sampled Shorts and for all 18 on the test day. The crop is
  biased to `center 32%` because the subject of a vertical video is never in the bottom third.
- **A day whose videos changed is rebuilt.** `scripts/run_daily.ps1` ran a bare `build`, which
  resolves to the newest day alone. But a video is filed under the day it was *uploaded*, so a clip
  summarised tonight can belong to last Tuesday — and that page was never rewritten, leaving the
  video invisible forever. The nightly job now passes `--backfill`; the build already hashes each
  day and skips what has not changed, so the full pass over 119 days costs about ten seconds.

### Added
- Shorts carry a **`Short` badge**, so a 45-second clip is no longer indistinguishable from a
  40-minute interview until you open it.
- A **toggle above the video list** hides them — `Ẩn 18 Short` — and remembers the choice. At 42% of
  the archive, someone here for long-form needed a way to put them aside.
- `newsvault/videos.py` reads `is_short` **only when the column exists**, so an older copy of the
  upstream database still loads, and every thumbnail now travels with a fallback url the front end
  tries once before giving up on the picture.
- `tests/js/videos.test.mjs` — 16 tests over the real `videos.js` against a stub DOM, no browser.

## [0.6.0] - 2026-08-05

### Added
- **A layout switch for desktop reading.** One, two or three columns, or a card grid, chosen from the
  top bar and remembered across days ([`newsvault/assets/layout.js`](newsvault/assets/layout.js)). The
  choice is an attribute on `<html>`; the stylesheet does the rest, so nothing re-renders when it
  changes. The control is hidden below 1024px — a phone has one column and no decision to make.
  Three columns need 1280px; below that the mode falls back to two rather than producing 300px columns.
- In the grid mode a card turns vertical, picture above the headline, four across a 1440px screen.
- Opening a card in any multi-column mode gives it the full width of the row, because a summary plus
  four analysis sections is unreadable in a third of a screen.

### Changed
- **The day's videos start open.** They are things to read, not a chart to consult; folding them made
  them invisible. The analysis panels still start folded. Either way the reader's own choice is
  remembered, and only a panel nobody has touched uses the default.
- **The page fills a desktop screen.** Above 1280px the 1200px cap is replaced by a gutter of
  1.5–2rem, with content capped at 2000px so a 4K monitor does not produce unreadable line lengths.
- The video section no longer prints its own heading inside the fold that already names it.

### Fixed
- **Every thumbnail is now the same size.** `.card__lead > div` also matched `.card__thumb` — the
  wrapper *is* a div — and its `flex: 1 1 auto` outranked `.card__thumb { flex: none }` by one element
  selector. Each picture therefore grew into whatever space its headline left over: measured on one
  page at 1440px, six thumbnails came out 197, 200, 320, 331, 349 and 405 px wide. They are now a
  fixed 208px (144px at three columns, full width in the grid).

## [0.5.0] - 2026-08-05

### Added
- **A second source: YouTube.** The archive now reads `youtube_summarizer.db` alongside the news
  database and lists each day's AI-summarised videos in their own folded section. That takes the
  archive from 16 days to **114** (2026-03-30 onward) and adds **793 summaries**, because a day now
  exists when it has articles *or* videos. Point `NEWSVAULT_VIDEO_DB` at the file; leave it unset and
  the archive builds exactly as before.
- **Pictures, taken rather than generated.** Videos show their YouTube thumbnail, articles show the
  image the publisher put in their own `og:image`. Both urls travel inside the encrypted payload, so a
  visitor who has not typed the password never learns one exists, and both are loaded with
  `referrerpolicy="no-referrer"` so the publisher's CDN is not told which page linked to it. A
  thumbnail that fails removes itself rather than leaving a broken-image glyph.
- Video summaries are stored as **pre-parsed blocks**, not text with markup in it. `newsvault/videos.py`
  turns the model's output into headings, paragraphs, bullets and bold runs, and the front end builds
  text nodes from them. Nothing a language model wrote can be interpreted as markup by the browser.
- Videos are in the whole-archive search index, so `!` search reaches them.

### Fixed
- **The article list rendered into the folded video panel.** `NV.videos` puts the shared `cards` class
  on its own list, and `app.js` looked up `#app .cards` unscoped, so `querySelector` returned whichever
  list came first in the DOM — the video one. Every article card was written into a collapsed
  `<details>` and the day page came up empty. All article-list lookups are scoped to `.cards-wrap` now,
  and entity and week pages carry that container too so the selector means the same thing everywhere.

### Operations
- The nightly publish task existed but had **never run**: it was registered at 18:38 for an 18:30
  trigger. It is proven working now, and moved to **21:15** so it lands after news-hunter (13:00) and
  the YouTube summariser (20:00) instead of a day behind them.

## [0.4.0] - 2026-08-05

### Removed
- **The AI illustration pipeline is gone.** `newsvault/images.py`, the image prompts, the
  `--images` / `--image-days` / `--max-image-calls` / `--dry-run-images` flags and the
  `NEWSVAULT_IMAGE_PROVIDER` / `AI_HUB_*` settings all go with it, along with 35 generated WebP files.
  Every category now carries a fixed line icon from `newsvault/assets/icons.js`. Generating a picture
  per category per day cost an API call and about a minute per day, sent this archive's headlines to a
  third-party endpoint to decorate a page, and gave the same category a different look on every date.
  The whole icon set is about a kilobyte.

### Added
- **Source tier.** Thirteen of the sixty-two sources cost a subscription; `newsvault/sources.py` mirrors
  the flag news-hunter keeps on each source, and `Article.tier` derives from the source key rather than
  being stored, so the two can never drift. Paid coverage is badged on the card, sorted first by
  default (a new `Trả phí trước` sort mode), filterable with `tier:paid` / `tier:free` and their two
  Vietnamese chips, counted per category, and coloured in the source chart.
- **Headline-first reading.** A card shows its badges, headline and source line only; the summary, key
  points, tags and the four analysis sections are behind one `Xem thêm` toggle (`x` or Enter on the
  keyboard cursor, `Mở tất cả` in the search bar). Saving stays outside the fold — it is the one action
  worth taking off a bare headline. A text query auto-expands its matches so highlights stay visible.
- **Folded analysis panels.** Categories, the three charts, trends and blind spots start collapsed
  inside one `Chuyên mục · Biểu đồ · Xu hướng` row and remember whether you opened them, so a phone
  opens on the brief and the headline list instead of three screens of charts.
- `tests/js/search.test.mjs` — 33 tests over the real query engine, run by `node --test` in CI with no
  browser and no dependencies. It exists because a filter that matches nothing fails silently.

### Changed
- **The source chart shows every source collected, not the top six.** It was a donut, which folds its
  tail into a `Khác` slice; the question the panel answers is which sources ran that day. It is now a
  full bar chart with paid sources coloured and a legend. Week pages and the entity timeline get the
  same treatment — a timeline truncated to ten bars turns dates into a meaningless bucket.
- The brief cache moved from `.image-cache/brief` to `.cache/brief` now that nothing else lives there.

### Fixed
- **A quoted operator value containing a space matched nothing.** `tokenize()` only recognised a quote
  at the *start* of a token, so `topic:"Kinh tế/Tài chính"` — exactly what every category chip and
  topic chip emits — split into `topic:"Kinh` plus a stray `tế/Tài chính"`, and the unbalanced quote
  was never stripped. Clicking a category returned an empty list.
- **Four filter chips could never match.** `law:`, `analysis:`, `saved:` and `unread:` were missing
  from the operator key set, so each fell through to a full-text search for the literal string
  `law:true` and returned nothing. They are operators now, `analysis` aliases `analyzed`, and
  `law:false` means the same as `-law:true`.
- **Unstyled buttons were invisible in the dark theme.** The reset gave every button `color: inherit`
  while its background stayed the OS ButtonFace — near-white text on near-white. Buttons now default to
  a transparent background, and `.card__action` has a real frame of its own.
- Card badges were laid out `space-between`, flinging score, tier and impact to opposite edges of a
  phone. They read as one strip now.
- The headline is the primary tap target in a headline-first list, and a one-line Vietnamese title
  renders at 21px. It gets 44px on touch.

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
