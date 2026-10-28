'use strict';

function registerOrderRoutes(router, { orders, guard }) {
  router.add('POST', '/orders', guard.requireUser(async ({ user, body }) => ({
    status: 201,
    body: orders.create(user, body),
  })));

  router.add('GET', '/orders', guard.requireUser(async ({ user, query }) => ({
    status: 200,
    body: orders.list(user, query),
  })));

  router.add('GET', '/orders/:id', guard.requireUser(async ({ params }) => ({
    status: 200,
    body: orders.get(params.id),
  })));

  router.add('POST', '/orders/:id/cancel', guard.requireUser(async ({ user, params }) => ({
    status: 200,
    body: orders.cancel(user, params.id),
  })));

  router.add('POST', '/orders/:id/ship', guard.requireAdmin(async ({ params }) => ({
    status: 200,
    body: orders.ship(params.id),
  })));

  router.add('POST', '/orders/:id/deliver', guard.requireAdmin(async ({ params }) => ({
    status: 200,
    body: orders.deliver(params.id),
  })));
}

module.exports = { registerOrderRoutes };
