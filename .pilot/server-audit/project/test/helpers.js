'use strict';

const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { createApp } = require('../src/app');

const ADMIN = { email: 'admin@example.com', password: 'admin-password', name: 'Admin' };
const PASSWORD = 'correct-horse';

async function startApp(t, options = {}) {
  const reportDir = fs.mkdtempSync(path.join(os.tmpdir(), 'orders-reports-'));
  const app = createApp({ secret: 'test-secret', reportDir, admin: ADMIN, ...options });
  const port = await app.listen(0);
  t.after(async () => {
    await app.close();
    fs.rmSync(reportDir, { recursive: true, force: true });
  });

  function call(method, urlPath, { body, token } = {}) {
    return new Promise((resolve, reject) => {
      const payload = body === undefined ? undefined : JSON.stringify(body);
      const headers = {};
      if (payload !== undefined) headers['content-type'] = 'application/json';
      if (token) headers.authorization = `Bearer ${token}`;
      const req = http.request({ host: '127.0.0.1', port, method, path: urlPath, headers, agent: false }, (res) => {
        const chunks = [];
        res.on('data', (chunk) => chunks.push(chunk));
        res.on('end', () => {
          const text = Buffer.concat(chunks).toString('utf8');
          const isJson = (res.headers['content-type'] || '').startsWith('application/json');
          resolve({ status: res.statusCode, body: isJson && text ? JSON.parse(text) : undefined, text });
        });
      });
      req.on('error', reject);
      req.end(payload);
    });
  }

  async function login(email, password = PASSWORD) {
    const res = await call('POST', '/sessions', { body: { email, password } });
    return res.body.token;
  }

  async function signUp(email, name = 'Customer') {
    await call('POST', '/users', { body: { email, password: PASSWORD, name } });
    return login(email);
  }

  return { call, login, signUp, reportDir, adminToken: await login(ADMIN.email, ADMIN.password) };
}

module.exports = { startApp, PASSWORD };
