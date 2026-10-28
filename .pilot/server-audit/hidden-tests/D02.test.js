'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { startApp } = require('./support');

test('D02 order totals are exact to the cent', async (t) => {
  const { call, signUp } = await startApp(t);
  const token = await signUp('cents@example.com');
  const cases = [
    { items: [{ sku: 'A', unitPrice: 0.1, quantity: 1 }, { sku: 'B', unitPrice: 0.2, quantity: 1 }], total: 0.3 },
    { items: [{ sku: 'C', unitPrice: 1.15, quantity: 3 }], total: 3.45 },
    { items: [{ sku: 'D', unitPrice: 10.1, quantity: 1 }, { sku: 'E', unitPrice: 20.2, quantity: 1 }], total: 30.3 },
  ];
  for (const { items, total } of cases) {
    const res = await call('POST', '/orders', { token, body: { items } });
    assert.equal(res.status, 201);
    assert.equal(res.body.total, total, JSON.stringify(items));
  }
});
