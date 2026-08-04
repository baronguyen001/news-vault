# news-vault

Turn a daily news database into a **password-protected static archive** — one HTML folder per day,
searchable across the whole history, hosted for free on GitHub Pages.

The site is public infrastructure holding private reading. Every headline, summary and link lives
inside an AES-256-GCM blob; the HTML shell is empty until the visitor types the password. Cloning the
repository, reading the page source or scraping the host reveals nothing but dates and counts.

```
docs/
├── index.html              landing page + calendar heat map of article volume
├── manifest.json           plain: dates, counts, entity names — never a headline
├── d/2026-08-04/
│   ├── index.html          empty shell
│   └── data.enc            the day, encrypted
├── e/<entity>/             per-entity page, aggregated across every day
├── w/2026-W32/             weekly roll-up
├── idx/2026-08.enc         monthly search-index shard
└── feed.xml, feed.json     metadata-only feeds (no headlines by default)
```

## What it does

**Reads** a [news-hunter](https://github.com/baronguyen001) SQLite database read-only — it never
writes to your source of truth. Articles already carry a relevance score, an impact level, a topic, a
region, tags, key points and a deep-analysis block; news-vault turns those into navigation.

**Scores** every article `0.5·relevance + 0.3·impact + 0.2·source tier`, normalised to 0–100. The
weights live in one dict in [`newsvault/score.py`](newsvault/score.py).

**Clusters** stories: articles from the same day and topic whose title tokens overlap past a Jaccard
threshold collapse into one card labelled *“9 nguồn đưa tin”*. No LLM call, fully deterministic.
The threshold is deliberately strict (0.45). On a feed that news-hunter has already de-duplicated
upstream it fires rarely — measured on real data, the closest unrelated pair scores 0.35, so loosening
it would merge distinct stories rather than surface real multi-source coverage.

**Builds entity pages** from the tag column — any name mentioned three times or more gets its own page
tracking coverage across the archive.

**Surfaces trends and blind spots**: terms whose frequency today exceeds their 7-day baseline by a
z-score, and topics whose share of coverage has fallen unusually far below their 30-day norm.

**Writes a daily brief** — five Vietnamese bullets from Gemini, or a deterministic top-five fallback
when there is no API key, no quota, or no network.

**Marks paid coverage.** Thirteen of the sixty-two sources cost a subscription. news-vault derives
that tier from the source key ([`newsvault/sources.py`](newsvault/sources.py)), badges it on the card,
sorts paid coverage first by default, and gives it its own filter chip — the point of paying for
Reuters and the FT is reading them before everything else.

**Shows every source it collected.** The source panel is a full bar chart, not a donut: a donut folds
its tail into "Khác", and the question the panel answers is which sources ran today, paid ones marked.

**Reads headline-first.** A card is a headline, a source and a score until you open it; the summary,
key points and the four analysis sections are one tap away. Ninety expanded articles is a wall nobody
scrolls. The category, chart and trend panels start folded for the same reason, and remember whether
you opened them.

**Illustrates categories with fixed icons** — a line icon per topic, drawn from a table in
[`newsvault/assets/icons.js`](newsvault/assets/icons.js). Earlier releases generated an AI picture per
category per day. That cost an API call and about a minute per day, sent this archive's headlines to a
third-party endpoint to decorate a page, and gave the same category a different look on every date.

**In the browser**: diacritic-insensitive Vietnamese search across the whole archive, search operators
(`source:reuters topic:AI impact:cao tier:paid score:>70`), a `⌘K` command palette, saved articles, a keyword
watchlist, read tracking, “new since your last visit”, dark mode, offline PWA caching, Markdown/PDF
export and share cards — all vanilla JavaScript, no framework, no CDN, no tracking.

**On a phone**: the layout is verified by measurement, not by eye. `tests/` aside, a Playwright pass
across iPhone SE / iPhone 14 / Android / tablet asserts the page never scrolls horizontally and that
every interactive control clears the 44px touch minimum. The header collapses to two compact rows with
a horizontally scrolling action strip instead of stacking six buttons down the screen.

## Security model

| | |
|---|---|
| Encryption | AES-256-GCM, key from PBKDF2-HMAC-SHA256, 250 000 iterations |
| What is encrypted | day payloads, entity pages, weekly pages, search index shards |
| What is not | dates, article counts, entity names |
| Where the password lives | `NEWSVAULT_PASSWORD` in `.env`, git-ignored, never in the output |
| Session | the password is held in `sessionStorage`; closing the tab clears it |
| Crawlers | `robots.txt` disallows everything, every page is `noindex` |

Two features can undo this and are therefore **off by default**:

* `--feed-full` puts headlines into `feed.xml` and `feed.json`, which are plaintext and public.
* `newsvault.audio` renders the brief to an mp3, which is likewise public.

A published archive is only as private as its password. `Bao@1992`-class passwords resist casual
snooping, not an attacker willing to spend GPU time on 250 000-round PBKDF2. Treat this as a lock on a
filing cabinet, not a safe.

## Install

```bash
git clone git@github.com:baronguyen001/news-vault.git
cd news-vault
python -m venv .venv && . .venv/Scripts/activate     # Windows
pip install -e ".[dev]"
cp .env.example .env                                  # then fill it in
```

Optional spoken digest: `pip install -e ".[audio]"`.

## Use

```bash
newsvault days                                  # what the database holds
newsvault build                                 # today only
newsvault build --backfill                      # whole history
newsvault export --date 2026-08-04 --to day.md  # server-side Markdown
newsvault verify --date 2026-08-04              # decrypt a built day and describe it
newsvault rekey                                 # re-encrypt everything after a password change
```

Rebuilds are incremental: each page's payload is hashed into `docs/.build-state.json`, and an unchanged
day is neither re-encrypted nor re-committed. The PBKDF2 salt is stored there too and deliberately
reused, so a daily commit stays a small diff instead of rewriting every byte in the archive.

Briefs are cached on disk per day, so a rebuild — including a `rekey` — costs nothing and calls no API.

### Publishing

GitHub Pages, source `main` / `/docs`. [`scripts/run_daily.ps1`](scripts/run_daily.ps1) builds, refuses
to publish if the password appears anywhere under `docs/`, then commits and pushes.

## Testing

```bash
ruff check . && ruff format --check . && pytest
```

Tests never touch the network or a real database: `tests/make_fixture.py` generates a synthetic
news-hunter database with the real schema.

## License

MIT
