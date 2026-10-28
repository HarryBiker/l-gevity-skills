'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const { notFound } = require('../lib/errors');

const CSV_HEADER = 'id,userId,status,total,createdAt';

function toCsvRow(order) {
  return [order.id, order.userId, order.status, order.total.toFixed(2), order.createdAt].join(',');
}

function registerReportRoutes(router, { orders, guard, reportDir }) {
  router.add('POST', '/reports/orders', guard.requireAdmin(async () => {
    await fs.mkdir(reportDir, { recursive: true });
    const name = `orders-${Date.now()}-${crypto.randomBytes(3).toString('hex')}.csv`;
    const rows = orders.all().map(toCsvRow);
    await fs.writeFile(path.join(reportDir, name), `${[CSV_HEADER, ...rows].join('\n')}\n`, 'utf8');
    return { status: 201, body: { name } };
  }));

  router.add('GET', '/reports/:name', guard.requireAdmin(async ({ params }) => {
    let text;
    try {
      text = await fs.readFile(path.join(reportDir, params.name), 'utf8');
    } catch {
      throw notFound('report not found');
    }
    return { status: 200, text, contentType: 'text/csv; charset=utf-8' };
  }));
}

module.exports = { registerReportRoutes };
