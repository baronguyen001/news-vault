import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const modulePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'topics.js');
const source = fs.readFileSync(modulePath, 'utf8');

const fallbackFold = (value) => String(value).toLowerCase().normalize("NFD")
  .replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "d")
  .replace(/\s+/g, " ").trim();

function makeSandbox(options = {}) {
  const sandbox = { window: { NV: {} } };
  if (options.withSearchFold) {
    sandbox.window.NV.search = { fold: fallbackFold };
  }
  const context = vm.createContext(sandbox);
  vm.runInContext(source, context);
  return context.window.NV.topics;
}

test("KEYS contains the documented slugs in order and is frozen", () => {
  const topics = makeSandbox();
  assert.deepEqual(Array.from(topics.KEYS), [
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
  assert.equal(Object.isFrozen(topics.KEYS), true);
});

test("each database topic maps to its own slug", () => {
  const topics = makeSandbox();
  assert.equal(topics.slug("Kinh tế/Tài chính"), "kinh-te");
  assert.equal(topics.slug("Chính trị/Chính sách"), "chinh-tri");
  assert.equal(topics.slug("Công nghệ/AI"), "cong-nghe");
  assert.equal(topics.slug("Xung đột/Chiến tranh"), "xung-dot");
  assert.equal(topics.slug("Pháp luật/Nghị định"), "phap-luat");
  assert.equal(topics.slug("Văn hóa/Xã hội"), "van-hoa");
  assert.equal(topics.slug("Khác"), "khac");
  // Added 2026-08-12 alongside the two new news-hunter topics.
  assert.equal(topics.slug("Chứng khoán"), "chung-khoan");
  assert.equal(topics.slug("Crypto"), "crypto");
});

test("the two new finance splits win over the generic money group", () => {
  const topics = makeSandbox();
  // "Chứng khoán" carries no "kinh te"/"tai chinh" substring, but a vertical label might,
  // and the narrow hue has to win when both could match.
  assert.equal(topics.slug("Tài chính - Chứng khoán"), "chung-khoan");
  assert.equal(topics.slug("Tài chính Crypto"), "crypto");
});

test("Blockchain does not leak into technology through the bare AI keyword", () => {
  const topics = makeSandbox();
  // "blockchain" contains the letters "ai" inside "chain". The AI keyword is whole-word
  // only for exactly this reason - this test keeps that guarantee nailed down.
  assert.equal(topics.slug("Crypto/Blockchain"), "crypto");
  assert.equal(topics.slug("Blockchain"), "crypto");
});

test("x-pulse vertical slugs already used by posts.py resolve to themselves", () => {
  const topics = makeSandbox();
  assert.equal(topics.slug("chung-khoan"), "chung-khoan");
  assert.equal(topics.slug("crypto"), "crypto");
});

test("Tài chính and Kinh doanh maps to finance rather than technology", () => {
  const topics = makeSandbox();
  assert.equal(topics.slug("Tài chính & Kinh doanh"), "kinh-te");
});

test("Công nghệ AI and bare AI map to technology", () => {
  const topics = makeSandbox();
  assert.equal(topics.slug("Công nghệ/AI"), "cong-nghe");
  assert.equal(topics.slug("AI"), "cong-nghe");
});

test("empty and absent topics return empty values", () => {
  const topics = makeSandbox();
  for (const value of ["", null, undefined, "   "]) {
    assert.equal(topics.slug(value), "");
    assert.equal(topics.className(value), "");
  }
});

test("a number does not throw and returns a known slug", () => {
  const topics = makeSandbox();
  assert.doesNotThrow(() => topics.slug(123));
  assert.ok(topics.KEYS.includes(topics.slug(123)));
});

test("an unknown topic is deterministic across calls and sandboxes", () => {
  const first = makeSandbox().slug("Thể thao");
  const second = makeSandbox().slug("Thể thao");
  assert.ok(makeSandbox().KEYS.includes(first));
  assert.equal(first, second);
});

test("different unknown topics return non-empty known slugs", () => {
  const topics = makeSandbox();
  const first = topics.slug("Thiên văn");
  const second = topics.slug("Ẩm thực");
  assert.ok(topics.KEYS.includes(first));
  assert.ok(topics.KEYS.includes(second));
  assert.notEqual(first, "");
  assert.notEqual(second, "");
});

test("className prefixes the topic slug", () => {
  const topics = makeSandbox();
  assert.equal(topics.className("Công nghệ/AI"), "topic-cong-nghe");
});

test("fallback and search fold produce the same answers", () => {
  const fallbackTopics = makeSandbox();
  const searchTopics = makeSandbox({ withSearchFold: true });
  const values = [
    "Kinh tế/Tài chính",
    "Chính trị/Chính sách",
    "Công nghệ/AI",
    "Thể thao",
    123
  ];
  for (const value of values) {
    assert.equal(searchTopics.slug(value), fallbackTopics.slug(value));
    assert.equal(searchTopics.className(value), fallbackTopics.className(value));
  }
});
