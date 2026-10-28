'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { startApp } = require('./helpers');

test('admins export orders and download the export', async (t) => {
  const { call, signUp, adminToken } = await startApp(t);
  const alice = await signUp('alice@example.com');
  await call('POST', '/orders', { token: alice, body: { items: [{ sku: 'MUG-1', unitPrice: 8, quantity: 3 }] } });
  const exported = await call('POST', '/reports/orders', { token: adminToken });
  assert.equal(exported.status, 201);
  const download = await call('GET', `/reports/${exported.body.name}`, { token: adminToken });
  assert.equal(download.status, 200);
  const lines = download.text.trim().split('\n');
  assert.equal(lines[0], 'id,userId,status,total,createdAt');
  assert.equal(lines.length, 2);
  assert.match(lines[1], /,pending,24\.00,/);
});

test('customers cannot export or download reports', async (t) => {
  const { call, signUp, adminToken } = await startApp(t);
  const alice = await signUp('alice@example.com');
  assert.equal((await call('POST', '/reports/orders', { token: alice })).status, 403);
  const exported = await call('POST', '/reports/orders', { token: adminToken });
  assert.equal((await call('GET', `/reports/${exported.body.name}`, { token: alice })).status, 403);
});

test('an unknown export is not found', async (t) => {
  const { call, adminToken } = await startApp(t);
  assert.equal((await call('GET', '/reports/orders-0.csv', { token: adminToken })).status, 404);
});
