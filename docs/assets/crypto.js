(function () {
  "use strict";

  window.NV = window.NV || {};

  const MAGIC = "NVLT";
  const PW_KEY = "nv.pw";

  class BadPasswordError extends Error {
    constructor(message = "Sai mật khẩu") {
      super(message);
      this.name = "BadPasswordError";
    }
  }

  class BadFormatError extends Error {
    constructor(message = "Định dạng không hợp lệ") {
      super(message);
      this.name = "BadFormatError";
    }
  }

  const keyCache = new Map();
  const inFlight = new Map();

  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  async function deriveKey(password, salt, iterations) {
    const cacheKey = arrayBufferToBase64(salt) + ":" + iterations + ":" + password;
    const cached = keyCache.get(cacheKey);
    if (cached) {
      return cached;
    }

    const encoder = new TextEncoder();
    const passwordKey = await crypto.subtle.importKey(
      "raw",
      encoder.encode(password),
      { name: "PBKDF2" },
      false,
      ["deriveKey"]
    );

    const key = await crypto.subtle.deriveKey(
      {
        name: "PBKDF2",
        hash: "SHA-256",
        salt: salt,
        iterations: iterations,
      },
      passwordKey,
      { name: "AES-GCM", length: 256 },
      false,
      ["decrypt"]
    );

    keyCache.set(cacheKey, key);
    return key;
  }

  function base64ToBytes(value) {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }

  /* A "secret" is either the password the reader typed or an already-derived AES key.
   * A remembered device stores the derived key and never the password: the key comes back
   * from IndexedDB non-extractable, so it can decrypt this site and yield nothing else. */
  function isCryptoKey(value) {
    return !!value &&
      typeof value === "object" &&
      typeof value.type === "string" &&
      typeof value.algorithm === "object";
  }

  async function resolveKey(secret, salt, iterations) {
    if (isCryptoKey(secret)) {
      return secret;
    }
    return deriveKey(secret, salt, iterations);
  }

  /** The key for this site, given the salt and iteration count the manifest publishes. */
  async function keyFor(password, saltBase64, iterations) {
    return deriveKey(password, base64ToBytes(saltBase64), iterations);
  }

  async function decryptBuffer(buffer, password) {
    if (!(buffer instanceof ArrayBuffer)) {
      throw new BadFormatError("Dữ liệu đầu vào không hợp lệ.");
    }

    const view = new DataView(buffer);
    const magicBytes = new Uint8Array(buffer, 0, 4);
    const magic = new TextDecoder().decode(magicBytes);

    if (magic !== MAGIC) {
      throw new BadFormatError("Tệp tin không đúng định dạng news-vault.");
    }

    const version = view.getUint8(4);
    if (version !== 1) {
      throw new BadFormatError("Phiên bản mã hóa không được hỗ trợ.");
    }

    const iterations = view.getUint32(5, false);
    const salt = new Uint8Array(buffer, 9, 16);
    const iv = new Uint8Array(buffer, 25, 12);
    const ciphertext = new Uint8Array(buffer, 37);

    const key = await resolveKey(password, salt, iterations);

    let plaintext;
    try {
      plaintext = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: iv },
        key,
        ciphertext
      );
    } catch (err) {
      throw new BadPasswordError("Sai mật khẩu");
    }

    if (typeof DecompressionStream === "undefined") {
      throw new BadFormatError(
        "Trình duyệt của bạn quá cũ. Vui lòng sử dụng Chrome, Edge, Firefox hoặc Safari phiên bản mới hơn."
      );
    }

    const ds = new DecompressionStream("deflate");
    const stream = new Response(new Blob([plaintext])).body.pipeThrough(ds);
    const inflated = await new Response(stream).arrayBuffer();
    const text = new TextDecoder().decode(inflated);

    return JSON.parse(text);
  }

  async function fetchJson(url, password) {
    const isIndexEnc = url.includes("/idx/") && url.endsWith(".enc");
    const fetchOptions = isIndexEnc ? { cache: "no-store" } : {};
    const existing = inFlight.get(url);

    if (existing) {
      return existing;
    }

    const promise = (async () => {
      try {
        const response = await fetch(url, fetchOptions);
        if (!response.ok) {
          throw new BadFormatError("Không thể tải dữ liệu: " + response.status);
        }
        const buffer = await response.arrayBuffer();
        return await decryptBuffer(buffer, password);
      } finally {
        inFlight.delete(url);
      }
    })();

    inFlight.set(url, promise);
    return promise;
  }

  function savePassword(password) {
    try {
      sessionStorage.setItem(PW_KEY, password);
    } catch (err) {
      // Intentional swallow: Safari private mode may throw on sessionStorage access.
    }
  }

  function loadPassword() {
    try {
      return sessionStorage.getItem(PW_KEY);
    } catch (err) {
      // Intentional swallow: Safari private mode may throw on sessionStorage access.
      return null;
    }
  }

  function clearPassword() {
    try {
      sessionStorage.removeItem(PW_KEY);
    } catch (err) {
      // Intentional swallow: Safari private mode may throw on sessionStorage access.
    }
  }

  window.NV.crypto = {
    MAGIC,
    decryptBuffer,
    fetchJson,
    keyFor,
    isCryptoKey,
    savePassword,
    loadPassword,
    clearPassword,
    BadPasswordError,
    BadFormatError,
  };
})();
