"use strict";
window.NV = window.NV || {};

/* Topic -> colour slug. A day page is ninety identical grey boxes; giving each topic a
 * hue is what lets a reader tell finance from war without reading a word.
 *
 * The seven slugs are a closed set, but the classifier is free to invent a topic and video
 * cards reuse the field for a video type - so an unrecognised topic still gets a colour,
 * picked by a hash so the same topic always lands on the same one. Nothing renders grey. */
(function () {
  const NV = window.NV;

  const KEYS = Object.freeze([
    "kinh-te",
    "chung-khoan",
    "crypto",
    "chinh-tri",
    "cong-nghe",
    "xung-dot",
    "phap-luat",
    "van-hoa",
    "khac"
  ]);

  function fallbackFold(value) {
    return String(value).toLowerCase().normalize("NFD")
      .replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "d")
      .replace(/\s+/g, " ").trim();
  }

  function fold(value) {
    if (NV.search && typeof NV.search.fold === "function") {
      return NV.search.fold(value);
    }
    return fallbackFold(value);
  }

  // Order is also the tie-break order: "Tài chính & Kinh doanh" must land on money, and it
  // would land on technology if the tech group were tested first.
  const keywordGroups = [
    // These two are tested BEFORE "kinh-te" on purpose. "Chứng khoán" and "Crypto" are
    // narrower splits of finance, and a headline vertical like "Tài chính & Chứng khoán"
    // must land on the narrow hue, not on the generic money one.
    //
    // The hyphenated spellings are not redundant: fold() collapses whitespace but leaves
    // "-" alone, so the already-slugged form that posts.py stores in `vertical`
    // ("chung-khoan") misses the spaced keyword and falls through to the hash, which put
    // it on the money hue purely by accident. Cheaper to accept both spellings than to
    // rely on nobody ever passing a slug in here.
    {
      slug: "chung-khoan",
      keywords: ["chung khoan", "chung-khoan", "co phieu", "co-phieu", "stock", "equit"]
    },
    {
      slug: "crypto",
      keywords: ["crypto", "tien ma hoa", "tien so", "blockchain", "bitcoin", "defi", "web3"]
    },
    {
      slug: "kinh-te",
      keywords: ["kinh te", "tai chinh", "business", "finance", "market"]
    },
    {
      slug: "chinh-tri",
      keywords: ["chinh tri", "chinh sach", "politic", "government"]
    },
    {
      slug: "cong-nghe",
      keywords: ["cong nghe", "ai", "tech", "khoa hoc", "science"]
    },
    {
      slug: "xung-dot",
      keywords: ["xung dot", "chien tranh", "war", "conflict", "quan su"]
    },
    {
      slug: "phap-luat",
      keywords: ["phap luat", "nghi dinh", "luat", "law", "legal"]
    },
    {
      slug: "van-hoa",
      keywords: ["van hoa", "xa hoi", "giao duc", "culture", "social", "health"]
    },
    {
      slug: "khac",
      keywords: ["khac", "other"]
    }
  ];

  function slug(topic) {
    if (topic === null || topic === undefined) {
      return "";
    }

    const text = String(topic).trim();
    if (!text) {
      return "";
    }

    const folded = fold(text);

    for (const group of keywordGroups) {
      for (const keyword of group.keywords) {
        if (keyword === "ai") {
          // Whole word only. As a substring it fires on "tai chinh", "khai thac",
          // "hai quan" - most of the Vietnamese vocabulary, in other words.
          if (/(^|[^a-z])ai([^a-z]|$)/.test(folded)) {
            return group.slug;
          }
        } else if (folded.indexOf(keyword) !== -1) {
          return group.slug;
        }
      }
    }

    let total = 0;
    for (const character of folded) {
      total += character.charCodeAt(0);
    }
    return KEYS[total % KEYS.length];
  }

  function className(topic) {
    const topicSlug = slug(topic);
    return topicSlug ? "topic-" + topicSlug : "";
  }

  NV.topics = {
    KEYS: KEYS,
    slug: slug,
    className: className
  };
})();
