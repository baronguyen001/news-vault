import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const enginePath = path.resolve(__dirname, '..', '..', 'newsvault', 'assets', 'search.js');
const context = vm.createContext({ window: {} });
vm.runInContext(fs.readFileSync(enginePath, 'utf8'), context, { filename: enginePath });
const { fold, parse, run, highlight } = context.window.NV.search;

const ITEMS = [
  { d: '2026-08-04', i: 1, t: 'Fed tăng lãi suất', f: 'fed tang lai suat ...', s: 'Reuters', sk: 'reuters', tr: 'paid', tp: 'Kinh tế/Tài chính', im: 'cao', sc: 74, r: 'international', tg: ['Fed', 'lãi suất'], u: 'u1', law: true, analyzed: true, saved: false, unread: true },
  { d: '2026-08-04', i: 2, t: 'Chứng khoán <b>VN</b> & bất động sản', f: 'chung khoan vn va bat dong san ...', s: 'VnExpress', sk: 'vnexpress', tr: 'free', tp: 'Kinh tế/Chứng khoán', im: 'trung bình', sc: 74, r: 'domestic', tg: ['VN-Index'], u: 'u2', law: false, analyzed: false, saved: true, unread: false },
  { d: '2026-08-05', i: 1, t: 'Tin tức pháp luật mới', f: 'tin tuc phap luat moi ...', s: 'Thanh Niên', sk: 'thanhnien', tr: 'free', tp: 'Pháp luật', im: 'thấp', sc: 55, r: 'domestic', tg: ['pháp luật'], u: 'u3', law: true, analyzed: true, saved: true, unread: false },
  { d: '2026-08-05', i: 2, t: 'AI và y tế', f: 'ai va y te ...', s: 'Reuters', sk: 'reuters', tr: 'paid', tp: '', im: 'cao', sc: 92, r: 'international', tg: ['AI', 'y tế'], u: 'u4', law: false, analyzed: false, saved: false, unread: true },
  { d: '2026-08-06', i: 1, t: 'Miền Trung mưa lũ', f: 'mien trung mua lu ...', s: 'Tuổi Trẻ', sk: 'tuoitre', tr: 'free', tp: 'Xã hội', im: 'trung bình', sc: 60, r: 'domestic', tg: [], u: 'u5', law: false, analyzed: true, saved: false, unread: true },
  { d: '2026-08-06', i: 2, t: 'OPEC giữ giá dầu', f: 'opec giu gia dau ...', s: 'Bloomberg', sk: 'bloomberg', tr: 'paid', tp: 'Kinh tế/Năng lượng', im: 'cao', sc: 88, r: 'international', tg: ['OPEC', 'dầu'], u: 'u6', law: true, analyzed: true, saved: true, unread: false },
  { d: '2026-08-07', i: 1, t: 'Công nghệ & AI', f: 'cong nghe va ai ...', s: 'TechCrunch', sk: 'techcrunch', tr: 'free', tp: 'Công nghệ', im: 'thấp', sc: 42, r: 'international', tg: ['AI'], u: 'u7', law: false, analyzed: false, saved: false, unread: true },
  { d: '2026-08-07', i: 2, t: 'Lạm phát toàn cầu', f: 'lam phat toan cau ...', s: 'Reuters', sk: 'reuters', tr: 'paid', tp: 'Kinh tế/Vĩ mô', im: 'cao', sc: 80, r: 'international', tg: ['lạm phát'], u: 'u8', law: false, analyzed: true, saved: true, unread: false },
  { d: '2026-08-08', i: 1, t: 'Thể thao Việt Nam', f: 'the thao viet nam ...', s: 'VnExpress', sk: 'vnexpress', tr: 'free', tp: 'Thể thao', im: 'trung bình', sc: 50, r: 'domestic', tg: ['thể thao'], u: 'u9', law: false, analyzed: false, saved: false, unread: true },
  { d: '2026-08-08', i: 2, t: 'Kinh tế & Tài chính', f: 'kinh te va tai chinh ...', s: 'CaféF', sk: 'cafef', tr: 'paid', tp: 'Kinh tế/Tài chính', im: 'cao', sc: 65, r: 'domestic', tg: ['tài chính'], u: 'u10', law: true, analyzed: true, saved: true, unread: false },
  { d: '2026-08-09', i: 1, t: 'Premium analysis', f: 'premium analysis ...', s: 'Alpha', sk: 'alpha', tr: 'paid', tp: 'Phân tích', im: 'cao', sc: 95, r: 'international', tg: ['analysis'], u: 'u11', law: true, analyzed: true, saved: true, unread: false },
  { d: '2026-08-09', i: 2, t: 'Free briefing', f: 'free briefing ...', s: 'Beta', sk: 'beta', tr: 'free', tp: 'Tổng hợp', im: '', sc: 30, r: 'domestic', tg: ['free'], u: 'u12', law: false, analyzed: false, saved: false, unread: true },
];

const urls = (results) => results.map((item) => item.u).sort();
const ALL_URLS = urls(ITEMS);

test('Folding lowercases, strips Vietnamese diacritics, maps đ to d and collapses whitespace', () => {
  assert.equal(fold('Lãi suất'), 'lai suat');
  assert.equal(fold('Đà Nẵng'), 'da nang');
  assert.equal(fold('  Lãi   SUẤT  '), 'lai suat');
});

test('ANDed terms only return items containing every term', () => {
  assert.deepEqual(urls(run(ITEMS, 'lai suat')), ['u1']);
  assert.deepEqual(urls(run(ITEMS, 'lai viet')), []);
});

test('Quoted phrases match as a contiguous folded substring', () => {
  assert.deepEqual(urls(run(ITEMS, '"lai suat"')), ['u1']);
  assert.deepEqual(urls(run(ITEMS, '"cong nghe"')), ['u7']);
});

test('A leading minus excludes items containing the term, phrase or operator', () => {
  assert.deepEqual(urls(run(ITEMS, '-lai')), ALL_URLS.filter((u) => u !== 'u1'));
  assert.deepEqual(urls(run(ITEMS, '-"lai suat"')), ALL_URLS.filter((u) => u !== 'u1'));
  assert.deepEqual(urls(run(ITEMS, '-source:reuters')), ['u10', 'u11', 'u12', 'u2', 'u3', 'u5', 'u6', 'u7', 'u9']);
});

test('source: and sk: match either the source key or the folded display source', () => {
  assert.deepEqual(urls(run(ITEMS, 'source:reuters')), ['u1', 'u4', 'u8']);
  assert.deepEqual(urls(run(ITEMS, 'sk:vnexpress')), ['u2', 'u9']);
});

test('topic: and tp: match the folded topic prefix', () => {
  assert.deepEqual(urls(run(ITEMS, 'topic:"kinh"')), ['u1', 'u10', 'u2', 'u6', 'u8']);
  assert.deepEqual(urls(run(ITEMS, 'tp:"the"')), ['u9']);
  // The quoted multi-word form is what every filter chip emits, so it carries the
  // most weight of any query shape in the application. Topic matching is a prefix
  // match, so this selects the whole "Kinh tế/..." family.
  assert.deepEqual(urls(run(ITEMS, 'topic:"kinh te"')), ['u1', 'u10', 'u2', 'u6', 'u8']);
  assert.deepEqual(urls(run(ITEMS, 'topic:"kinh te/tai chinh"')), ['u1', 'u10']);
  assert.deepEqual(urls(run(ITEMS, 'tp:"the thao"')), ['u9']);
});

test('impact: matches the exact folded impact level', () => {
  assert.deepEqual(urls(run(ITEMS, 'impact:"cao"')), ['u1', 'u10', 'u11', 'u4', 'u6', 'u8']);
  assert.deepEqual(urls(run(ITEMS, 'impact:"thap"')), ['u3', 'u7']);
  // "trung bình" is a real impact level in the database and the only one whose value
  // contains a space, so it has to survive quoting.
  assert.deepEqual(urls(run(ITEMS, 'impact:"trung binh"')), ['u2', 'u5', 'u9']);
});

test('region: maps vn and vietnam to domestic and intl or world to international', () => {
  assert.deepEqual(urls(run(ITEMS, 'region:vn')), ['u10', 'u12', 'u2', 'u3', 'u5', 'u9']);
  assert.deepEqual(urls(run(ITEMS, 'region:vietnam')), ['u10', 'u12', 'u2', 'u3', 'u5', 'u9']);
  assert.deepEqual(urls(run(ITEMS, 'region:intl')), ['u1', 'u11', 'u4', 'u6', 'u7', 'u8']);
  assert.deepEqual(urls(run(ITEMS, 'region:world')), ['u1', 'u11', 'u4', 'u6', 'u7', 'u8']);
});

test('tag: matches any folded tag exactly', () => {
  assert.deepEqual(urls(run(ITEMS, 'tag:fed')), ['u1']);
  assert.deepEqual(urls(run(ITEMS, 'tag:ai')), ['u4', 'u7']);
});

test('day: matches the exact day string without folding', () => {
  assert.deepEqual(urls(run(ITEMS, 'day:2026-08-04')), ['u1', 'u2']);
  assert.deepEqual(urls(run(ITEMS, 'day:2026-08-09')), ['u11', 'u12']);
});

test('tier: accepts paid, free, the Vietnamese hyphen aliases and premium', () => {
  assert.deepEqual(urls(run(ITEMS, 'tier:paid')), ['u1', 'u10', 'u11', 'u4', 'u6', 'u8']);
  assert.deepEqual(urls(run(ITEMS, 'tier:tra-phi')), ['u1', 'u10', 'u11', 'u4', 'u6', 'u8']);
  assert.deepEqual(urls(run(ITEMS, 'tier:free')), ['u12', 'u2', 'u3', 'u5', 'u7', 'u9']);
  assert.deepEqual(urls(run(ITEMS, 'tier:mien-phi')), ['u12', 'u2', 'u3', 'u5', 'u7', 'u9']);
  assert.deepEqual(urls(run(ITEMS, 'tier:premium')), ['u1', 'u10', 'u11', 'u4', 'u6', 'u8']);
});

test('score: supports greater-than, less-than, range and exact comparisons', () => {
  assert.deepEqual(urls(run(ITEMS, 'score:>70')), ['u1', 'u11', 'u2', 'u4', 'u6', 'u8']);
  assert.deepEqual(urls(run(ITEMS, 'score:<50')), ['u12', 'u7']);
  assert.deepEqual(urls(run(ITEMS, 'score:40..60')), ['u3', 'u5', 'u7', 'u9']);
  assert.deepEqual(urls(run(ITEMS, 'score:55')), ['u3']);
});

test('is: matches a boolean flag by name', () => {
  assert.deepEqual(urls(run(ITEMS, 'is:law')), ['u1', 'u10', 'u11', 'u3', 'u6']);
  assert.deepEqual(urls(run(ITEMS, 'is:unread')), ['u1', 'u12', 'u4', 'u5', 'u7', 'u9']);
});

test('law:true is parsed as a boolean facet and matches only law items', () => {
  assert.deepEqual(urls(run(ITEMS, 'law:true')), ['u1', 'u10', 'u11', 'u3', 'u6']);
});

test('law:false and -law:true both require the absence of the law flag', () => {
  const expected = ['u12', 'u2', 'u4', 'u5', 'u7', 'u8', 'u9'];
  assert.deepEqual(urls(run(ITEMS, 'law:false')), expected);
  assert.deepEqual(urls(run(ITEMS, '-law:true')), expected);
});

test('analysis:true is parsed as a boolean facet and matches only analyzed items', () => {
  assert.deepEqual(urls(run(ITEMS, 'analysis:true')), ['u1', 'u10', 'u11', 'u3', 'u5', 'u6', 'u8']);
});

test('saved:true is parsed as a boolean facet and matches only saved items', () => {
  assert.deepEqual(urls(run(ITEMS, 'saved:true')), ['u10', 'u11', 'u2', 'u3', 'u6', 'u8']);
});

test('unread:true is parsed as a boolean facet and matches only unread items', () => {
  assert.deepEqual(urls(run(ITEMS, 'unread:true')), ['u1', 'u12', 'u4', 'u5', 'u7', 'u9']);
});

test('analysis is an alias for analyzed', () => {
  assert.deepEqual(urls(run(ITEMS, 'analyzed:true')), urls(run(ITEMS, 'analysis:true')));
});

test('Multiple values for the same key are OR-ed while different keys are AND-ed', () => {
  assert.deepEqual(urls(run(ITEMS, 'source:reuters source:bloomberg')), ['u1', 'u4', 'u6', 'u8']);
  assert.deepEqual(urls(run(ITEMS, 'topic:"kinh" tier:paid')), ['u1', 'u10', 'u6', 'u8']);
});

test('Negated operators exclude matching items', () => {
  assert.deepEqual(urls(run(ITEMS, '-topic:"kinh"')), ['u11', 'u12', 'u3', 'u4', 'u5', 'u7', 'u9']);
  assert.deepEqual(urls(run(ITEMS, '-tag:ai')), ['u1', 'u10', 'u11', 'u12', 'u2', 'u3', 'u5', 'u6', 'u8', 'u9']);
});

test('Default paid sort orders paid first, then score descending, then day descending', () => {
  assert.deepEqual(run(ITEMS, '').map((item) => item.u), ['u11', 'u4', 'u6', 'u8', 'u1', 'u10', 'u2', 'u5', 'u3', 'u9', 'u7', 'u12']);
});

test('Score sort orders by score descending then day descending', () => {
  assert.deepEqual(run(ITEMS, '', { sort: 'score' }).map((item) => item.u), ['u11', 'u4', 'u6', 'u8', 'u1', 'u2', 'u10', 'u5', 'u3', 'u9', 'u7', 'u12']);
});

test('Time sort orders by day descending then score descending', () => {
  assert.deepEqual(run(ITEMS, '', { sort: 'time' }).map((item) => item.u), ['u11', 'u12', 'u10', 'u9', 'u8', 'u7', 'u6', 'u5', 'u4', 'u3', 'u1', 'u2']);
});

test('Source sort orders source name case-insensitive A to Z then score descending', () => {
  assert.deepEqual(run(ITEMS, '', { sort: 'source' }).map((item) => item.u), ['u11', 'u12', 'u6', 'u10', 'u4', 'u8', 'u1', 'u7', 'u3', 'u5', 'u2', 'u9']);
});

test('Repeated runs over the same input produce identical order', () => {
  const a = run(ITEMS, '', { sort: 'paid' }).map((item) => item.u);
  const b = run(ITEMS, '', { sort: 'paid' }).map((item) => item.u);
  assert.deepEqual(a, b);
});

test('An empty query returns every item and parse reports isEmpty', () => {
  assert.deepEqual(urls(run(ITEMS, '')), ALL_URLS);
  assert.equal(parse('').isEmpty, true);
});

test('highlight escapes HTML before marking and never emits raw input angle or ampersand', () => {
  assert.equal(highlight('<b>VN</b> & AI', 'vn'), '&lt;b&gt;<mark>VN</mark>&lt;/b&gt; &amp; AI');
});

test('highlight offsets survive diacritics so matching lai wraps exactly Lãi', () => {
  assert.equal(highlight('Lãi suất Fed', 'lai'), '<mark>Lãi</mark> suất Fed');
});

test('highlight marks every occurrence of a term', () => {
  assert.equal(highlight('AI và AI', 'ai'), '<mark>AI</mark> và <mark>AI</mark>');
});

test('highlight marks a quoted phrase as one contiguous span', () => {
  assert.equal(highlight('Lãi suất Fed', '"lai suat"'), '<mark>Lãi suất</mark> Fed');
});

test('An unquoted multi-word operator value is split into an operator plus a free text term', () => {
  assert.deepEqual(urls(run(ITEMS, 'topic:kinh te')), ['u10']);
});

test('Every advertised operator key is parsed as an operator and changes the result set', () => {
  const cases = [
    ['source:reuters', ['u1', 'u4', 'u8']],
    ['sk:vnexpress', ['u2', 'u9']],
    ['topic:"kinh"', ['u1', 'u10', 'u2', 'u6', 'u8']],
    ['tp:"the"', ['u9']],
    ['impact:"cao"', ['u1', 'u10', 'u11', 'u4', 'u6', 'u8']],
    ['region:vn', ['u10', 'u12', 'u2', 'u3', 'u5', 'u9']],
    ['tag:ai', ['u4', 'u7']],
    ['day:2026-08-04', ['u1', 'u2']],
    ['tier:paid', ['u1', 'u10', 'u11', 'u4', 'u6', 'u8']],
    ['score:>70', ['u1', 'u11', 'u2', 'u4', 'u6', 'u8']],
    ['is:law', ['u1', 'u10', 'u11', 'u3', 'u6']],
    ['law:true', ['u1', 'u10', 'u11', 'u3', 'u6']],
    ['analysis:true', ['u1', 'u10', 'u11', 'u3', 'u5', 'u6', 'u8']],
    ['analyzed:true', ['u1', 'u10', 'u11', 'u3', 'u5', 'u6', 'u8']],
    ['saved:true', ['u10', 'u11', 'u2', 'u3', 'u6', 'u8']],
    ['unread:true', ['u1', 'u12', 'u4', 'u5', 'u7', 'u9']],
  ];
  for (const [query, expected] of cases) {
    const got = urls(run(ITEMS, query));
    assert.deepEqual(got, expected, `query ${query} should filter by operator`);
    assert.notDeepEqual(got, ALL_URLS, `query ${query} must not be swallowed as free text`);
  }
});
