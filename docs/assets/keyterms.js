(function () {
  window.NV = window.NV || {};

  function isLetterOrDigit(character) {
    if (!character) {
      return false;
    }
    return /^[a-z0-9]$/i.test(foldCharacter(character));
  }

  function foldCharacter(character) {
    return character
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D")
      .toLowerCase();
  }

  // Folds one character at a time and records, for every folded character, the original
  // span it came from. NFD changes string length, so folded offsets cannot be used against
  // the original text directly - without this map every highlight on an accented word (i.e.
  // most Vietnamese words) would silently drift by a few characters.
  function buildFoldedText(text) {
    var folded = "";
    var starts = [];
    var ends = [];
    var index;
    var character;
    var value;
    var part;

    for (index = 0; index < text.length; index += 1) {
      character = text.charAt(index);
      value = foldCharacter(character);

      for (part = 0; part < value.length; part += 1) {
        folded += value.charAt(part);
        starts.push(index);
        ends.push(index + 1);
      }
    }

    return {
      text: folded,
      starts: starts,
      ends: ends
    };
  }

  function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function addNumberIntervals(text, intervals) {
    var pattern = /\$?[0-9]+(?:[.,][0-9]+)*/g;
    var match;
    var value;
    var start;
    var numberStart;
    var end;
    var digitCount;
    var suffix;
    var unitMatch;

    while ((match = pattern.exec(text)) !== null) {
      value = match[0];
      start = match.index;
      numberStart = value.charAt(0) === "$" ? start + 1 : start;

      if (numberStart > 0 && isLetterOrDigit(text.charAt(numberStart - 1))) {
        continue;
      }

      end = start + value.length;
      suffix = text.slice(end);
      unitMatch = null;

      if (suffix.charAt(0) === "%") {
        unitMatch = ["%"];
      } else {
        unitMatch = /^\s*(USD|tỷ|triệu|nghìn|đồng|điểm|tấn|km|MW|GW)/i.exec(suffix);

        if (
          unitMatch &&
          isLetterOrDigit(suffix.charAt(unitMatch[0].length))
        ) {
          unitMatch = null;
        }
      }

      if (unitMatch) {
        intervals.push([start, end + unitMatch[0].length]);
      } else if (value.charAt(0) === "$") {
        intervals.push([start, end]);
      } else {
        digitCount = value.replace(/[.,]/g, "").length;
        if (digitCount >= 4) {
          intervals.push([start, end]);
        }
      }
    }
  }

  function addCodeIntervals(text, intervals) {
    var pattern = /[A-Z0-9]{2,6}/g;
    var match;
    var value;
    var start;
    var end;

    while ((match = pattern.exec(text)) !== null) {
      value = match[0];
      start = match.index;
      end = start + value.length;

      if (
        /[A-Z]/.test(value) &&
        !isLetterOrDigit(text.charAt(start - 1)) &&
        !isLetterOrDigit(text.charAt(end))
      ) {
        intervals.push([start, end]);
      }
    }
  }

  function addExtraTermIntervals(text, extraTerms, intervals) {
    var foldedText;
    var term;
    var foldedTerm;
    var pattern;
    var match;
    var start;
    var end;
    var index;

    if (!Array.isArray(extraTerms)) {
      return;
    }

    foldedText = buildFoldedText(text);

    for (index = 0; index < extraTerms.length; index += 1) {
      if (typeof extraTerms[index] !== "string") {
        continue;
      }

      term = extraTerms[index].trim();
      if (!term) {
        continue;
      }

      foldedTerm = buildFoldedText(term).text;
      if (!foldedTerm) {
        continue;
      }

      pattern = new RegExp(escapeRegExp(foldedTerm), "g");

      while ((match = pattern.exec(foldedText.text)) !== null) {
        start = match.index;
        end = start + match[0].length;

        if (
          !isLetterOrDigit(foldedText.text.charAt(start - 1)) &&
          !isLetterOrDigit(foldedText.text.charAt(end))
        ) {
          intervals.push([
            foldedText.starts[start],
            foldedText.ends[end - 1]
          ]);
        }
      }
    }
  }

  function mergeIntervals(intervals) {
    var sorted;
    var merged;
    var interval;
    var previous;
    var index;

    if (!intervals.length) {
      return [];
    }

    sorted = intervals.slice().sort(function (left, right) {
      return left[0] - right[0] || right[1] - left[1];
    });
    merged = [sorted[0].slice()];

    for (index = 1; index < sorted.length; index += 1) {
      interval = sorted[index];
      previous = merged[merged.length - 1];

      if (interval[0] <= previous[1]) {
        previous[1] = Math.max(previous[1], interval[1]);
      } else {
        merged.push(interval.slice());
      }
    }

    return merged;
  }

  // Returns non-overlapping [start, end) spans into `text`, never HTML: the caller feeds
  // them through the existing escape-then-mark routine in search.js, which is what keeps
  // this XSS-safe. Building markup here would move that guarantee somewhere nobody checks.
  function findKeyTerms(text, extraTerms) {
    var intervals = [];

    if (typeof text !== "string" || !text) {
      return [];
    }

    addNumberIntervals(text, intervals);
    addCodeIntervals(text, intervals);
    addExtraTermIntervals(text, extraTerms, intervals);

    return mergeIntervals(intervals);
  }

  window.NV.keyterms = {
    findKeyTerms: findKeyTerms
  };
})();
