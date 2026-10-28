'use strict';

const { unauthorized, forbidden } = require('../lib/errors');

function createGuard({ tokens, users }) {
  function authenticate(req) {
    const [scheme, token] = (req.headers.authorization || '').split(' ');
    if (scheme !== 'Bearer' || !token) return null;
    const claims = tokens.verify(token);
    return claims ? users.find(claims.sub) : null;
  }

  function requireUser(handler) {
    return async (ctx) => {
      const user = authenticate(ctx.req);
      if (!user) throw unauthorized();
      return handler({ ...ctx, user });
    };
  }

  function requireAdmin(handler) {
    return requireUser(async (ctx) => {
      if (ctx.user.role !== 'admin') throw forbidden('admin role required');
      return handler(ctx);
    });
  }

  return { requireUser, requireAdmin };
}

module.exports = { createGuard };
