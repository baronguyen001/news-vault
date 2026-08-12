import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const modulePath = path.resolve(path.dirname(__filename), '..', '..', 'newsvault', 'assets', 'video-library.js');
const source = fs.readFileSync(modulePath, 'utf8');

function load() {
  const window = {};
  vm.runInContext(source, vm.createContext({ window }), { filename: modulePath });
  return window.NV.videoLibrary;
}

test('channel search folding ignores Vietnamese diacritics, including đ', () => {
  assert.equal(load().folded('Đầu Tư & Công Nghệ'), 'dau tu & cong nghe');
});
