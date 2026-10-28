'use strict';

const http = require('node:http');
const path = require('node:path');
const { createRouter } = require('./http/router');
const { createStore } = require('./store/memoryStore');
const { createTokenService } = require('./auth/tokens');
const { createGuard } = require('./auth/guard');
const { createUserService } = require('./users/service');
const { createOrderService } = require('./orders/service');
const { createPaymentService } = require('./payments/service');
const { registerUserRoutes } = require('./users/routes');
const { registerOrderRoutes } = require('./orders/routes');
const { registerPaymentRoutes } = require('./payments/routes');
const { registerReportRoutes } = require('./reports/routes');

function createApp(options = {}) {
  const store = createStore();
  const tokens = createTokenService({ secret: options.secret, ttlSeconds: options.tokenTtlSeconds ?? 3600 });
  const users = createUserService({ store });
  const orders = createOrderService({ store });
  const payments = createPaymentService({ store, orders, provider: options.paymentProvider });
  const guard = createGuard({ tokens, users });

  const router = createRouter();
  registerUserRoutes(router, { users, tokens, guard, store });
  registerOrderRoutes(router, { orders, guard });
  registerPaymentRoutes(router, { payments, guard });
  registerReportRoutes(router, { orders, guard, reportDir: options.reportDir || path.resolve('reports') });

  if (options.admin) users.register(options.admin, 'admin');

  const server = http.createServer((req, res) => router.handle(req, res));
  return {
    listen(port = 0, host = '127.0.0.1') {
      return new Promise((resolve) => server.listen(port, host, () => resolve(server.address().port)));
    },
    close() {
      return new Promise((resolve) => server.close(() => resolve()));
    },
  };
}

if (require.main === module) {
  const app = createApp({
    secret: process.env.APP_SECRET,
    reportDir: process.env.REPORT_DIR,
    admin: process.env.ADMIN_EMAIL
      ? { email: process.env.ADMIN_EMAIL, password: process.env.ADMIN_PASSWORD, name: 'Administrator' }
      : undefined,
  });
  app.listen(Number(process.env.PORT) || 3000, '0.0.0.0').then((port) => {
    process.stdout.write(`orders-service listening on ${port}\n`);
  });
}

module.exports = { createApp };
