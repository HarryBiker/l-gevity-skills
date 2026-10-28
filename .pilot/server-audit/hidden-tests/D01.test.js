'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { startApp } = require('./support');

test('D01 totalPages counts a partially filled last page', async (t) => {
  const { call, signUp } = await startApp(t);
  const token = await signUp('pager@example.com');
  for (let i = 0; i < 5; i += 1) {
    const res = await call('POST', '/orders', { token, body: { items: [{ sku: `SKU-${i}`, unitPrice: 1, quantity: 1 }] } });
    assert.equal(res.status, 201);
  }
  const first = await call('GET', '/orders?pageSize=2', { token });
  assert.equal(first.status, 200);
  assert.equal(first.body.total, 5);
  assert.equal(first.body.items.length, 2);
  assert.equal(first.body.totalPages, 3);
  const last = await call('GET', '/orders?pageSize=2&page=3', { token });
  assert.equal(last.body.items.length, 1);
  assert.equal(last.body.totalPages, 3);
});
