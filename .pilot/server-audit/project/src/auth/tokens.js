'use strict';

const crypto = require('node:crypto');

function createTokenService({ secret, ttlSeconds }) {
  if (!secret) throw new Error('a token secret is required');

  function sign(payload) {
    return crypto.createHmac('sha256', secret).update(payload).digest('base64url');
  }

  function issue(claims) {
    const exp = Math.floor(Date.now() / 1000) + ttlSeconds;
    const payload = Buffer.from(JSON.stringify({ ...claims, exp })).toString('base64url');
    return `${payload}.${sign(payload)}`;
  }

  function verify(token) {
    const [payload, signature, extra] = String(token).split('.');
    if (!payload || !signature || extra !== undefined) return null;
    if (signature !== sign(payload)) return null;
    let claims;
    try {
      claims = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    } catch {
      return null;
    }
    if (!claims || typeof claims.exp !== 'number' || claims.exp * 1000 <= Date.now()) return null;
    return claims;
  }

  return { issue, verify };
}

module.exports = { createTokenService };
