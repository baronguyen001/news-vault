(function () {
  "use strict";

  window.NV = window.NV || {};

  const FILTER_KEYS = new Set([
    "source", "sk", "topic", "tp", "impact", "region", "tag", "day", "is", "score",
    "tier",
    // Boolean facets. They read as `law:true` in the query bar and used to be missing
    // from this set, so every one of them fell through to a full-text search for the
    // literal string "law:true" and silently matched nothing.
    "law", "analysis", "analyzed", "saved", "unread",
  ]);

  // `law:true` means the flag `law`; `law:false` means its negation.
  const BOOLEAN_KEYS = new Set(["law", "analysis", "analyzed", "saved", "unread"]);

  const FLAG_ALIASES = { analysis: "analyzed" };

  function fold(value) {
    return String(value ?? "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/\s+/g, " ")
      .trim();
  }

  function tokenize(query) {
    const tokens = [];
    let i = 0;

    while (i < query.length) {
      while (i < query.length && /\s/.test(query[i])) {
        i++;
      }
      if (i >= query.length) {
        break;
      }

      let negative = false;
      if (query[i] === "-") {
        negative = true;
        i++;
        while (i < query.length && /\s/.test(query[i])) {
          i++;
        }
      }

      if (i < query.length && query[i] === '"') {
        i++;
        let value = "";
        while (i < query.length && query[i] !== '"') {
          value += query[i];
          i++;
        }
        if (i < query.length) {
          i++;
        }
        tokens.push({
          type: "quoted",
          value: value,
          negative: negative,
          raw: (negative ? "-" : "") + '"' + value + '"',
        });
      } else {
        let value = "";
        while (i < query.length && !/\s/.test(query[i])) {
          // A quote *inside* a token opens a quoted operator value: `topic:"kinh te"`.
          // Without this the scan stopped at the space and produced `topic:"kinh` plus a
          // stray `te"`, so the unbalanced quote never got stripped and the filter
          // matched nothing at all - which is what every category chip emitted, since
          // most topic names contain a space.
          if (query[i] === '"') {
            value += '"';
            i++;
            while (i < query.length && query[i] !== '"') {
              value += query[i];
              i++;
            }
            if (i < query.length) {
              value += '"';
              i++;
            }
            continue;
          }
          value += query[i];
          i++;
        }
        tokens.push({
          type: "plain",
          value: value,
          negative: negative,
          raw: (negative ? "-" : "") + value,
        });
      }
    }

    return tokens;
  }

  function parseOperator(token) {
    const colonIdx = token.value.indexOf(":");
    if (colonIdx <= 0) {
      return null;
    }

    const key = token.value.slice(0, colonIdx).toLowerCase();
    if (!FILTER_KEYS.has(key)) {
      return null;
    }

    let rawVal = token.value.slice(colonIdx + 1);
    if (
      rawVal.length >= 2 &&
      rawVal.charAt(0) === '"' &&
      rawVal.charAt(rawVal.length - 1) === '"'
    ) {
      rawVal = rawVal.slice(1, -1);
    }

    return { key, rawVal, foldedVal: fold(rawVal) };
  }

  function applyScore(parsed, rawVal) {
    if (rawVal.startsWith(">")) {
      const n = parseInt(rawVal.slice(1), 10);
      if (!Number.isNaN(n)) {
        parsed.scoreMin = Math.max(parsed.scoreMin ?? -Infinity, n + 1);
      }
    } else if (rawVal.startsWith("<")) {
      const n = parseInt(rawVal.slice(1), 10);
      if (!Number.isNaN(n)) {
        parsed.scoreMax = Math.min(parsed.scoreMax ?? Infinity, n - 1);
      }
    } else if (rawVal.includes("..")) {
      const [a, b] = rawVal.split("..");
      const min = parseInt(a, 10);
      const max = parseInt(b, 10);
      if (!Number.isNaN(min)) {
        parsed.scoreMin = Math.max(parsed.scoreMin ?? -Infinity, min);
      }
      if (!Number.isNaN(max)) {
        parsed.scoreMax = Math.min(parsed.scoreMax ?? Infinity, max);
      }
    } else {
      const n = parseInt(rawVal, 10);
      if (!Number.isNaN(n)) {
        parsed.scoreMin = Math.max(parsed.scoreMin ?? -Infinity, n);
        parsed.scoreMax = Math.min(parsed.scoreMax ?? Infinity, n);
      }
    }
  }

  function parse(query) {
    const tokens = tokenize(query);

    const parsed = {
      terms: [],
      phrases: [],
      negatives: [],
      filters: {
        source: [], topic: [], impact: [], region: [], tag: [], day: [], tier: [], flags: [],
      },
      filterNegatives: {
        source: [], topic: [], impact: [], region: [], tag: [], day: [], tier: [], flags: [],
      },
      scoreMin: null,
      scoreMax: null,
      raw: query,
      isEmpty: false,
    };

    for (const token of tokens) {
      if (token.type === "quoted") {
        const folded = fold(token.value);
        if (token.negative) {
          parsed.negatives.push(folded);
        } else {
          parsed.phrases.push(folded);
        }
        continue;
      }

      const op = parseOperator(token);
      if (op) {
        let target = token.negative ? parsed.filterNegatives : parsed.filters;
        const { key, rawVal, foldedVal } = op;

        if (BOOLEAN_KEYS.has(key)) {
          // `law:false` is the same request as `-law:true`.
          if (foldedVal === "false" || foldedVal === "0" || foldedVal === "no") {
            target = target === parsed.filters ? parsed.filterNegatives : parsed.filters;
          }
          target.flags.push(FLAG_ALIASES[key] || key);
          continue;
        }

        switch (key) {
          case "source":
          case "sk":
            target.source.push(foldedVal);
            break;
          case "topic":
          case "tp":
            target.topic.push(foldedVal);
            break;
          case "impact":
            target.impact.push(foldedVal);
            break;
          case "region": {
            let mapped = foldedVal;
            if (mapped === "vn" || mapped === "vietnam") {
              mapped = "domestic";
            } else if (mapped === "intl" || mapped === "world") {
              mapped = "international";
            }
            target.region.push(mapped);
            break;
          }
          case "tag":
            target.tag.push(foldedVal);
            break;
          case "tier": {
            // Accept the Vietnamese words as well; the chips read "Trả phí"/"Miễn phí".
            // Spaces and hyphens are stripped so the hyphenated form works unquoted.
            const compact = foldedVal.replace(/[\s-]+/g, "");
            let mapped = foldedVal;
            if (compact === "traphi" || compact === "premium" || compact === "paid") {
              mapped = "paid";
            } else if (compact === "mienphi" || compact === "free") {
              mapped = "free";
            }
            target.tier.push(mapped);
            break;
          }
          case "day":
            target.day.push(rawVal);
            break;
          case "is":
            target.flags.push(foldedVal);
            break;
          case "score":
            applyScore(parsed, rawVal);
            break;
        }
      } else {
        const folded = fold(token.value);
        if (token.negative) {
          parsed.negatives.push(folded);
        } else {
          parsed.terms.push(folded);
        }
      }
    }

    parsed.isEmpty =
      parsed.terms.length === 0 &&
      parsed.phrases.length === 0 &&
      parsed.negatives.length === 0 &&
      parsed.scoreMin === null &&
      parsed.scoreMax === null &&
      Object.values(parsed.filters).every((arr) => arr.length === 0) &&
      Object.values(parsed.filterNegatives).every((arr) => arr.length === 0);

    return parsed;
  }

  function checkFlag(item, flag) {
    if (flag === "law") {
      return !!item.law;
    }
    if (flag === "analyzed" || flag === "analysis") {
      return !!(item.analyzed || item.analysis);
    }
    if (flag === "saved") {
      return !!item.saved;
    }
    if (flag === "unread") {
      return !!item.unread;
    }
    return false;
  }

  function matchFilters(item, filters, isNegative) {
    for (const key of Object.keys(filters)) {
      const vals = filters[key];
      if (vals.length === 0) {
        continue;
      }

      let matched = false;

      switch (key) {
        case "source": {
          const sourceFolded = fold(item.s || "");
          for (const v of vals) {
            if (item.sk === v || sourceFolded === v) {
              matched = true;
              break;
            }
          }
          break;
        }
        case "topic": {
          const topicFolded = fold(item.tp || "");
          for (const v of vals) {
            if (topicFolded.startsWith(v)) {
              matched = true;
              break;
            }
          }
          break;
        }
        case "impact": {
          const impactFolded = fold(item.im || "");
          for (const v of vals) {
            if (impactFolded === v) {
              matched = true;
              break;
            }
          }
          break;
        }
        case "region": {
          for (const v of vals) {
            if (item.r === v) {
              matched = true;
              break;
            }
          }
          break;
        }
        case "tag": {
          const tags = item.tg || [];
          for (const v of vals) {
            for (const t of tags) {
              if (fold(t) === v) {
                matched = true;
                break;
              }
            }
            if (matched) {
              break;
            }
          }
          break;
        }
        case "day": {
          for (const v of vals) {
            if (item.d === v) {
              matched = true;
              break;
            }
          }
          break;
        }
        case "tier": {
          for (const v of vals) {
            if ((item.tr || "free") === v) {
              matched = true;
              break;
            }
          }
          break;
        }
        case "flags": {
          for (const v of vals) {
            if (checkFlag(item, v)) {
              matched = true;
              break;
            }
          }
          break;
        }
      }

      if (isNegative ? matched : !matched) {
        return false;
      }
    }

    return true;
  }

  function matches(item, parsed) {
    if (parsed.scoreMin !== null && (item.sc ?? 0) < parsed.scoreMin) {
      return false;
    }
    if (parsed.scoreMax !== null && (item.sc ?? 0) > parsed.scoreMax) {
      return false;
    }

    if (!matchFilters(item, parsed.filters, false)) {
      return false;
    }
    if (!matchFilters(item, parsed.filterNegatives, true)) {
      return false;
    }

    const foldedText = item.f || "";

    for (const term of parsed.terms) {
      if (foldedText.indexOf(term) === -1) {
        return false;
      }
    }

    for (const phrase of parsed.phrases) {
      if (foldedText.indexOf(phrase) === -1) {
        return false;
      }
    }

    for (const neg of parsed.negatives) {
      if (foldedText.indexOf(neg) !== -1) {
        return false;
      }
    }

    return true;
  }

  function run(items, query, options) {
    const parsed = typeof query === "string" ? parse(query) : query;
    const sortMode = options?.sort || "paid";
    const limit = options?.limit;

    const result = items.filter((item) => matches(item, parsed));

    const paidRank = (item) => ((item.tr || "free") === "paid" ? 0 : 1);

    result.sort((a, b) => {
      // Default order. A paid subscription is only worth having if its reporting is
      // read first, so tier outranks score and score breaks the tie inside each tier.
      if (sortMode === "paid") {
        if (paidRank(a) !== paidRank(b)) {
          return paidRank(a) - paidRank(b);
        }
        if (b.sc !== a.sc) {
          return b.sc - a.sc;
        }
        return (b.d || "").localeCompare(a.d || "");
      }

      if (sortMode === "score") {
        if (b.sc !== a.sc) {
          return b.sc - a.sc;
        }
        return (b.d || "").localeCompare(a.d || "");
      }

      if (sortMode === "time") {
        if (b.d !== a.d) {
          return (b.d || "").localeCompare(a.d || "");
        }
        return b.sc - a.sc;
      }

      if (sortMode === "source") {
        const sa = (a.s || "").toLowerCase();
        const sb = (b.s || "").toLowerCase();
        if (sa !== sb) {
          return sa.localeCompare(sb);
        }
        return b.sc - a.sc;
      }

      return 0;
    });

    if (limit !== undefined && limit >= 0) {
      return result.slice(0, limit);
    }

    return result;
  }

  function escapeHtmlWithMap(text) {
    const codePoints = Array.from(text);
    const out = [];
    const origToEsc = new Array(codePoints.length + 1);
    origToEsc[0] = 0;

    for (let i = 0; i < codePoints.length; i++) {
      const cp = codePoints[i];
      let escaped;
      switch (cp) {
        case "&":
          escaped = "&amp;";
          break;
        case "<":
          escaped = "&lt;";
          break;
        case ">":
          escaped = "&gt;";
          break;
        case '"':
          escaped = "&quot;";
          break;
        case "'":
          escaped = "&#39;";
          break;
        default:
          escaped = cp;
      }
      out.push(escaped);
      origToEsc[i + 1] = origToEsc[i] + escaped.length;
    }

    return { escaped: out.join(""), origToEsc };
  }

  function foldWithMap(text) {
    const codePoints = Array.from(text);
    const chars = [];
    const map = [];
    let prevWasSpace = true;

    for (let i = 0; i < codePoints.length; i++) {
      const cp = codePoints[i];
      const segment = cp.toLowerCase().normalize("NFD");
      const parts = Array.from(segment);

      for (const p of parts) {
        const code = p.codePointAt(0);
        if (code >= 0x0300 && code <= 0x036f) {
          continue;
        }

        const out = p === "đ" ? "d" : p;

        if (/\s/.test(out)) {
          if (!prevWasSpace && chars.length > 0) {
            chars.push(" ");
            map.push(i);
            prevWasSpace = true;
          }
        } else {
          chars.push(out);
          map.push(i);
          prevWasSpace = false;
        }
      }
    }

    while (chars.length > 0 && chars[chars.length - 1] === " ") {
      chars.pop();
      map.pop();
    }

    const folded = chars.join("");
    map.push(codePoints.length);

    return { folded, map };
  }

  function findAll(haystack, needle) {
    const intervals = [];
    if (!needle) {
      return intervals;
    }
    let pos = 0;
    while ((pos = haystack.indexOf(needle, pos)) !== -1) {
      intervals.push([pos, pos + needle.length]);
      pos += 1;
    }
    return intervals;
  }

  function mergeIntervals(intervals) {
    if (intervals.length === 0) {
      return [];
    }
    intervals.sort((a, b) => a[0] - b[0] || a[1] - b[1]);

    const merged = [intervals[0].slice()];
    for (let i = 1; i < intervals.length; i++) {
      const [s, e] = intervals[i];
      const last = merged[merged.length - 1];
      if (s <= last[1]) {
        if (e > last[1]) {
          last[1] = e;
        }
      } else {
        merged.push([s, e]);
      }
    }
    return merged;
  }

  // `cls` distinguishes query highlighting (no class) from keyword highlighting
  // (class="kw"), so the two can be styled apart - and so keyword marks can be shown only
  // inside the modal while the card list stays calm.
  function insertMarks(escaped, intervals, cls) {
    const open = cls ? '<mark class="' + cls + '">' : "<mark>";
    const parts = [];
    let last = 0;
    for (const [s, e] of intervals) {
      if (s > last) {
        parts.push(escaped.slice(last, s));
      }
      parts.push(open);
      parts.push(escaped.slice(s, e));
      parts.push("</mark>");
      last = e;
    }
    if (last < escaped.length) {
      parts.push(escaped.slice(last));
    }
    return parts.join("");
  }

  // Marks arbitrary spans of `text`, reusing the same escape-first machinery as
  // `highlight`. Spans index into the ORIGINAL text; they are mapped onto the escaped
  // string here, which is why callers must never pre-escape or hand-build markup.
  function markSpans(text, spans, cls) {
    const { escaped, origToEsc } = escapeHtmlWithMap(text);
    if (!spans || !spans.length) return escaped;
    const escSpans = [];
    for (const [s, e] of spans) {
      if (s == null || e == null || s >= e) continue;
      if (s < 0 || e > text.length) continue;
      escSpans.push([origToEsc[s], origToEsc[e]]);
    }
    return insertMarks(escaped, mergeIntervals(escSpans), cls);
  }

  function highlight(text, parsed) {
    const p = typeof parsed === "string" ? parse(parsed) : parsed;
    const { escaped, origToEsc } = escapeHtmlWithMap(text);
    const { folded, map } = foldWithMap(text);

    const intervals = [];
    for (const term of p.terms) {
      intervals.push(...findAll(folded, term));
    }
    for (const phrase of p.phrases) {
      intervals.push(...findAll(folded, phrase));
    }

    const escIntervals = intervals.map(([fs, fe]) => [
      origToEsc[map[fs]],
      origToEsc[map[fe]],
    ]);

    const merged = mergeIntervals(escIntervals);
    return insertMarks(escaped, merged);
  }

  window.NV.search = {
    fold,
    parse,
    matches,
    run,
    highlight,
    markSpans,
  };
})();
