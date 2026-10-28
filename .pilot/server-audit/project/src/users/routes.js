'use strict';

const { unauthorized } = require('../lib/errors');
const { paginate } = require('../lib/pagination');

function registerUserRoutes(router, { users, tokens, guard, store }) {
  router.add('POST', '/users', async ({ body }) => ({ status: 201, body: users.register(body) }));

  router.add('POST', '/sessions', async ({ body }) => {
    const user = users.verifyCredentials(body.email, body.password);
    if (!user) throw unauthorized('invalid email or password');
    return { status: 201, body: { token: tokens.issue({ sub: user.id }) } };
  });

  router.add('GET', '/users/me', guard.requireUser(async ({ user }) => ({ status: 200, body: user })));

  router.add('GET', '/users', guard.requireAdmin(async ({ query }) => ({
    status: 200,
    body: paginate(store.list('users').map(users.toPublic), query),
  })));
}

module.exports = { registerUserRoutes };
