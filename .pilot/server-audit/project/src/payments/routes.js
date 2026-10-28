'use strict';

function registerPaymentRoutes(router, { payments, guard }) {
  router.add('POST', '/payments', guard.requireUser(async ({ user, body }) => ({
    status: 201,
    body: payments.capture(user, body),
  })));

  router.add('GET', '/payments/:id', guard.requireUser(async ({ user, params }) => ({
    status: 200,
    body: payments.get(user, params.id),
  })));
}

module.exports = { registerPaymentRoutes };
