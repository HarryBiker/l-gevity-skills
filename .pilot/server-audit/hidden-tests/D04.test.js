'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { startApp } = require('./support');

test('D04 a customer cannot read another customer\'s order', async (t) => {
  const { call, signUp } = await startApp(t);
  const alice = await signUp('alice@example.com');
  const mallory = await signUp('mallory@example.com');
  const order = (await call('POST', '/orders', { token: alice, body: { items: [{ sku: 'A', unitPrice: 9, quantity: 1 }] } })).body;

  const stolen = await call('GET', `/orders/${order.id}`, { token: mallory });
  assert.ok([403, 404].includes(stolen.status), `expected 403 or 404, got ${stolen.status}`);
  assert.ok(!stolen.text.includes(order.userId), 'the response leaks the owner');

  assert.equal((await call('GET', `/orders/${order.id}`, { token: alice })).status, 200);
});
