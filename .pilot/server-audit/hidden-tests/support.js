'use strict';

// Scoring support for the hidden tests. Self-contained on purpose: it uses only
// the documented createApp options and the HTTP API, never the run project's
// own test helpers, which an agent may have changed.

const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { createApp } = require('../src/app');

const ADMIN = { email: 'admin@example.com', password: 'admin-password', name: 'Admin' };
const PASSWORD = 'correct-horse';

async function startApp(t, options = {}) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'pilot-hidden-'));
  const reportDir = path.join(base, 'reports');
  fs.mkdirSync(reportDir);
  const app = createApp({ secret: 'hidden-test-secret', reportDir, admin: ADMIN, ...options });
  const port = await app.listen(0);
  t.after(async () => {
    await app.close();
    fs.rmSync(base, { recursive: true, force: true });
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
          let json;
          try {
            json = text ? JSON.parse(text) : undefined;
          } catch {
            json = undefined;
          }
          resolve({ status: res.statusCode, body: json, text });
        });
      });
      req.on('error', reject);
      req.end(payload);
    });
  }

  async function login(email, password = PASSWORD) {
    return (await call('POST', '/sessions', { body: { email, password } })).body.token;
  }

  async function signUp(email) {
    await call('POST', '/users', { body: { email, password: PASSWORD, name: email.split('@')[0] } });
    return login(email);
  }

  return { call, signUp, base, reportDir, adminToken: await login(ADMIN.email, ADMIN.password) };
}

module.exports = { startApp };
