'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { startApp, PASSWORD } = require('./helpers');

test('registering returns the public profile only', async (t) => {
  const { call } = await startApp(t);
  const res = await call('POST', '/users', { body: { email: ' Alice@Example.com ', password: PASSWORD, name: 'Alice' } });
  assert.equal(res.status, 201);
  assert.equal(res.body.email, 'alice@example.com');
  assert.equal(res.body.role, 'customer');
  assert.equal(res.body.passwordHash, undefined);
  assert.equal(res.body.salt, undefined);
});

test('registration rejects duplicates and weak input', async (t) => {
  const { call, signUp } = await startApp(t);
  await signUp('alice@example.com');
  const duplicate = await call('POST', '/users', { body: { email: 'alice@example.com', password: PASSWORD, name: 'A' } });
  assert.equal(duplicate.status, 409);
  const short = await call('POST', '/users', { body: { email: 'bob@example.com', password: 'short', name: 'Bob' } });
  assert.equal(short.status, 400);
  const badEmail = await call('POST', '/users', { body: { email: 'not-an-email', password: PASSWORD, name: 'Bob' } });
  assert.equal(badEmail.status, 400);
});

test('sessions reject wrong credentials', async (t) => {
  const { call, signUp } = await startApp(t);
  await signUp('alice@example.com');
  const res = await call('POST', '/sessions', { body: { email: 'alice@example.com', password: 'wrong-password' } });
  assert.equal(res.status, 401);
  const unknown = await call('POST', '/sessions', { body: { email: 'nobody@example.com', password: PASSWORD } });
  assert.equal(unknown.status, 401);
});

test('a valid token identifies the caller', async (t) => {
  const { call, signUp } = await startApp(t);
  const token = await signUp('alice@example.com', 'Alice');
  const me = await call('GET', '/users/me', { token });
  assert.equal(me.status, 200);
  assert.equal(me.body.name, 'Alice');
});

test('missing, tampered, and expired tokens are rejected', async (t) => {
  const { call, signUp } = await startApp(t);
  const token = await signUp('alice@example.com');
  assert.equal((await call('GET', '/users/me')).status, 401);
  const [payload, signature] = token.split('.');
  const tampered = `${payload}.${signature[0] === 'A' ? 'B' : 'A'}${signature.slice(1)}`;
  assert.equal((await call('GET', '/users/me', { token: tampered })).status, 401);

  const expiring = await startApp(t, { tokenTtlSeconds: 0 });
  const expired = await expiring.signUp('bob@example.com');
  assert.equal((await expiring.call('GET', '/users/me', { token: expired })).status, 401);
});

test('only admins list users', async (t) => {
  const { call, signUp, adminToken } = await startApp(t);
  const token = await signUp('alice@example.com');
  assert.equal((await call('GET', '/users', { token })).status, 403);
  const res = await call('GET', '/users', { token: adminToken });
  assert.equal(res.status, 200);
  assert.equal(res.body.total, 2);
  assert.ok(res.body.items.every((user) => user.passwordHash === undefined));
});
