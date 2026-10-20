import assert from 'node:assert/strict';

const listeners = new Map();
const message = {textContent: ''};
const enroll = {
  dataset: {user: 'approved-user'},
  disabled: false,
  textContent: 'Enroll this device passkey',
  addEventListener(type, callback) { listeners.set(type, callback); },
};

globalThis.document = {
  cookie: 'baiamonte_csrf=test-csrf',
  querySelector(selector) {
    if (selector === '#message') return message;
    if (selector === '#enroll-passkey') return enroll;
    return null;
  },
};
globalThis.location = {search: '?enroll=1', pathname: '/erp/app'};
globalThis.history = {replaceState() {}};
globalThis.sessionStorage = {getItem() { return null; }, setItem() {}};
const local = new Map();
globalThis.localStorage = {
  getItem(key) { return local.get(key) ?? null; },
  setItem(key, value) { local.set(key, value); },
};
globalThis.window = {PublicKeyCredential: function PublicKeyCredential() {}};

let createCalls = 0;
Object.defineProperty(globalThis, 'navigator', {configurable: true, value: {credentials: {async create() {
  createCalls += 1;
  return {
    rawId: Uint8Array.of(1).buffer,
    response: {
      clientDataJSON: Uint8Array.of(2).buffer,
      attestationObject: Uint8Array.of(3).buffer,
      getTransports() { return ['internal']; },
    },
  };
}}}});

let fetchCalls = 0;
globalThis.fetch = async (url) => {
  fetchCalls += 1;
  if (url.endsWith('/options')) {
    return {ok: true, async json() { return {ok: true, options: {publicKey: {challenge: 'AQ', user: {id: 'Ag'}}}}; }};
  }
  return {ok: true, async json() { return {ok: true}; }};
};

await import('../public/app.js');
await new Promise(resolve => setTimeout(resolve, 0));

assert.equal(createCalls, 1, 'HA return starts passkey enrollment on an unrecognized browser');
assert.equal(fetchCalls, 2, 'automatic enrollment gets options and verifies the credential');
assert.equal(local.get('baiamonte_passkey_enrolled:approved-user'), '1', 'successful enrollment is remembered per browser and user');
assert.equal(message.textContent, 'This device is enrolled for offline sign-in.');
assert.equal(enroll.disabled, true);
console.log('ok - HA return automatically starts per-device passkey enrollment');
