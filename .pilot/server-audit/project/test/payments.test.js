'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { startApp } = require('./helpers');

const ITEMS = [{ sku: 'LAMP-2', unitPrice: 24.5, quantity: 2 }];

async function placeOrder(call, token) {
  return (await call('POST', '/orders', { token, body: { items: ITEMS } })).body;
}

test('paying the exact total marks the order paid', async (t) => {
  const { call, signUp } = await startApp(t);
  const alice = await signUp('alice@example.com');
  const order = await placeOrder(call, alice);
  const payment = await call('POST', '/payments', { token: alice, body: { orderId: order.id, amount: 49 } });
  assert.equal(payment.status, 201);
  assert.equal(payment.body.status, 'captured');
  const updated = (await call('GET', `/orders/${order.id}`, { token: alice })).body;
  assert.equal(updated.status, 'paid');
  assert.equal(updated.paymentId, payment.body.id);
});

test('a wrong amount is rejected and the order stays pending', async (t) => {
  const { call, signUp } = await startApp(t);
  const alice = await signUp('alice@example.com');
  const order = await placeOrder(call, alice);
  const res = await call('POST', '/payments', { token: alice, body: { orderId: order.id, amount: 48.99 } });
  assert.equal(res.status, 400);
  assert.equal((await call('GET', `/orders/${order.id}`, { token: alice })).body.status, 'pending');
});

test('an order is paid only once and only by its owner', async (t) => {
  const { call, signUp } = await startApp(t);
  const alice = await signUp('alice@example.com');
  const bob = await signUp('bob@example.com');
  const order = await placeOrder(call, alice);
  assert.equal((await call('POST', '/payments', { token: bob, body: { orderId: order.id, amount: 49 } })).status, 404);
  assert.equal((await call('POST', '/payments', { token: alice, body: { orderId: order.id, amount: 49 } })).status, 201);
  assert.equal((await call('POST', '/payments', { token: alice, body: { orderId: order.id, amount: 49 } })).status, 409);
});

test('payments are visible to their owner only', async (t) => {
  const { call, signUp, adminToken } = await startApp(t);
  const alice = await signUp('alice@example.com');
  const bob = await signUp('bob@example.com');
  const order = await placeOrder(call, alice);
  const payment = (await call('POST', '/payments', { token: alice, body: { orderId: order.id, amount: 49 } })).body;
  assert.equal((await call('GET', `/payments/${payment.id}`, { token: alice })).status, 200);
  assert.equal((await call('GET', `/payments/${payment.id}`, { token: adminToken })).status, 200);
  assert.equal((await call('GET', `/payments/${payment.id}`, { token: bob })).status, 404);
});
