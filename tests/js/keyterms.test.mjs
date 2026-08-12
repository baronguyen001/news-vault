import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const src = readFileSync(
  new URL("../../newsvault/assets/keyterms.js", import.meta.url),
  "utf8"
);
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const KT = sandbox.window.NV.keyterms;

function intervals(value) {
  return Array.from(value, (pair) => Array.from(pair));
}

function covered(text, result) {
  return result.map(([start, end]) => text.slice(start, end));
}

test("matches the golden samples", () => {
  const samples = [
    ["", [], []],
    ["Không có gì đáng chú ý ở đây.", [], []],
    ["VN-Index tăng 12,5% trong quý 2.", [], ["VN", "12,5%"]],
    [
      "Máy DUV ngâm có giá khoảng 90 triệu USD mỗi chiếc.",
      [],
      ["DUV", "90 triệu", "USD"]
    ],
    ["Nhà máy công suất 120.000 thùng mỗi ngày.", [], ["120.000"]],
    ["Thương vụ trị giá $9 tỷ với Anthropic.", [], ["$9 tỷ"]],
    ["Chỉ có 3 người bị thương.", [], []],
    ["Hà Nội xây tuyến mới.", ["hà nội"], ["Hà Nội"]],
    ["Ha Noi xay tuyen moi.", ["Hà Nội"], ["Ha Noi"]],
    ["Việt Nam và Trung Quốc.", [], []]
  ];

  for (const [text, extraTerms, expected] of samples) {
    const result = intervals(KT.findKeyTerms(text, extraTerms));
    assert.deepEqual(covered(text, result), expected, `sample: ${text}`);
  }
});

test("maps folded accented and unaccented terms to original bounds", () => {
  const accented = intervals(KT.findKeyTerms("Hà Nội.", ["ha noi"]));
  const unaccented = intervals(KT.findKeyTerms("Ha Noi.", ["hà nội"]));

  assert.deepEqual(accented, [[0, 6]]);
  assert.deepEqual(unaccented, [[0, 6]]);
});

test("merges overlapping category intervals", () => {
  const text = "Giá 90 USD tăng.";
  const result = intervals(KT.findKeyTerms(text, []));

  assert.deepEqual(covered(text, result), ["90 USD"]);
});

test("guards invalid inputs and ignores invalid extra terms", () => {
  assert.deepEqual(intervals(KT.findKeyTerms(null)), []);
  assert.deepEqual(intervals(KT.findKeyTerms(undefined)), []);
  assert.deepEqual(intervals(KT.findKeyTerms(123)), []);
  assert.deepEqual(intervals(KT.findKeyTerms("abc", ["", null, 42])), []);
});

test("handles regex-special supplied terms safely", () => {
  const text = "Foo (Bar) announced results.";
  const result = intervals(KT.findKeyTerms(text, ["Foo (Bar)"]));

  assert.deepEqual(covered(text, result), ["Foo (Bar)"]);
});

test("does not retain regex state between calls", () => {
  const text = "GDP đạt 12,5%.";
  const first = intervals(KT.findKeyTerms(text, []));
  const second = intervals(KT.findKeyTerms(text, []));

  assert.deepEqual(second, first);
});

test("returns spans that are sorted and never overlap", () => {
  const text = "GDP tăng 12,5%, VN30 đạt 1.234 điểm, Hà Nội dẫn đầu với $9 tỷ.";
  const result = intervals(KT.findKeyTerms(text, ["Hà Nội", "GDP"]));

  for (let i = 1; i < result.length; i += 1) {
    assert.ok(result[i][0] >= result[i - 1][1], `span ${i} overlaps its predecessor`);
  }
  for (const [start, end] of result) {
    assert.ok(start >= 0 && end <= text.length && start < end, "span out of bounds");
  }
});
