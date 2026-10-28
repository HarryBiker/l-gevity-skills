'use strict';

const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');
const { startApp } = require('./support');

test('D06 report downloads cannot escape the report directory', async (t) => {
  const { call, adminToken, base } = await startApp(t);
  const secret = 'PILOT-SECRET-6f1d0c';
  fs.writeFileSync(path.join(base, 'secret.txt'), secret);

  for (const probe of ['..%2Fsecret.txt', '..%5Csecret.txt', '%2E%2E%2Fsecret.txt']) {
    const res = await call('GET', `/reports/${probe}`, { token: adminToken });
    assert.notEqual(res.status, 200, `${probe} was served`);
    assert.ok(!res.text.includes(secret), `${probe} leaked the file`);
  }

  const exported = await call('POST', '/reports/orders', { token: adminToken });
  assert.equal(exported.status, 201);
  const download = await call('GET', `/reports/${exported.body.name}`, { token: adminToken });
  assert.equal(download.status, 200);
  assert.match(download.text, /^id,userId,status,total,createdAt/);
});
