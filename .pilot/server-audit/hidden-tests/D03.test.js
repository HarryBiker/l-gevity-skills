'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { startApp } = require('./support');

test('D03 a shipped order cannot be cancelled', async (t) => {
  const { call, signUp, adminToken } = await startApp(t);
  const token = await signUp('shipper@example.com');
  const order = (await call('POST', '/orders', { token, body: { items: [{ sku: 'A', unitPrice: 5, quantity: 2 }] } })).body;
  assert.equal((await call('POST', '/payments', { token, body: { orderId: order.id, amount: 10 } })).status, 201);
  assert.equal((await call('POST', `/orders/${order.id}/ship`, { token: adminToken })).status, 200);

  const cancel = await call('POST', `/orders/${order.id}/cancel`, { token });
  assert.ok(cancel.status >= 400 && cancel.status < 500, `expected a 4xx, got ${cancel.status}`);
  assert.equal((await call('GET', `/orders/${order.id}`, { token })).body.status, 'shipped');

  const paid = (await call('POST', '/orders', { token, body: { items: [{ sku: 'B', unitPrice: 3, quantity: 1 }] } })).body;
  assert.equal((await call('POST', '/payments', { token, body: { orderId: paid.id, amount: 3 } })).status, 201);
  assert.equal((await call('POST', `/orders/${paid.id}/cancel`, { token })).status, 200);
});
