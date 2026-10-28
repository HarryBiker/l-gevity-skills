'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { startApp } = require('./helpers');

const ITEMS = [
  { sku: 'BOOK-1', unitPrice: 12.5, quantity: 2 },
  { sku: 'PEN-3', unitPrice: 5, quantity: 1 },
];

test('creating an order computes its total', async (t) => {
  const { call, signUp } = await startApp(t);
  const token = await signUp('alice@example.com');
  const res = await call('POST', '/orders', { token, body: { items: ITEMS } });
  assert.equal(res.status, 201);
  assert.equal(res.body.total, 30);
  assert.equal(res.body.status, 'pending');
  assert.equal(res.body.items.length, 2);
});

test('invalid orders are rejected', async (t) => {
  const { call, signUp } = await startApp(t);
  const token = await signUp('alice@example.com');
  const cases = [
    { items: [] },
    { items: [{ sku: 'A', unitPrice: 1, quantity: 0 }] },
    { items: [{ sku: 'A', unitPrice: 1.234, quantity: 1 }] },
    { items: [{ sku: '', unitPrice: 1, quantity: 1 }] },
  ];
  for (const body of cases) {
    assert.equal((await call('POST', '/orders', { token, body })).status, 400, JSON.stringify(body));
  }
  assert.equal((await call('POST', '/orders', { body: { items: ITEMS } })).status, 401);
});

test('customers list their own orders and admins list all', async (t) => {
  const { call, signUp, adminToken } = await startApp(t);
  const alice = await signUp('alice@example.com');
  const bob = await signUp('bob@example.com');
  await call('POST', '/orders', { token: alice, body: { items: ITEMS } });
  await call('POST', '/orders', { token: alice, body: { items: ITEMS } });
  await call('POST', '/orders', { token: bob, body: { items: ITEMS } });

  const own = await call('GET', '/orders', { token: alice });
  assert.equal(own.status, 200);
  assert.equal(own.body.total, 2);
  assert.equal(own.body.page, 1);
  assert.equal(own.body.totalPages, 1);

  const all = await call('GET', '/orders', { token: adminToken });
  assert.equal(all.body.total, 3);
});

test('owners and admins read an order', async (t) => {
  const { call, signUp, adminToken } = await startApp(t);
  const alice = await signUp('alice@example.com');
  const order = (await call('POST', '/orders', { token: alice, body: { items: ITEMS } })).body;
  assert.equal((await call('GET', `/orders/${order.id}`, { token: alice })).body.id, order.id);
  assert.equal((await call('GET', `/orders/${order.id}`, { token: adminToken })).status, 200);
  assert.equal((await call('GET', '/orders/missing', { token: alice })).status, 404);
});

test('a pending order can be cancelled once', async (t) => {
  const { call, signUp } = await startApp(t);
  const alice = await signUp('alice@example.com');
  const order = (await call('POST', '/orders', { token: alice, body: { items: ITEMS } })).body;
  const cancelled = await call('POST', `/orders/${order.id}/cancel`, { token: alice });
  assert.equal(cancelled.status, 200);
  assert.equal(cancelled.body.status, 'cancelled');
  assert.equal((await call('POST', `/orders/${order.id}/cancel`, { token: alice })).status, 409);
});

test('admins ship paid orders and deliver shipped ones', async (t) => {
  const { call, signUp, adminToken } = await startApp(t);
  const alice = await signUp('alice@example.com');
  const order = (await call('POST', '/orders', { token: alice, body: { items: ITEMS } })).body;
  assert.equal((await call('POST', `/orders/${order.id}/ship`, { token: adminToken })).status, 409);
  await call('POST', '/payments', { token: alice, body: { orderId: order.id, amount: 30 } });
  assert.equal((await call('POST', `/orders/${order.id}/ship`, { token: alice })).status, 403);
  const shipped = await call('POST', `/orders/${order.id}/ship`, { token: adminToken });
  assert.equal(shipped.body.status, 'shipped');
  const delivered = await call('POST', `/orders/${order.id}/deliver`, { token: adminToken });
  assert.equal(delivered.body.status, 'delivered');
});
