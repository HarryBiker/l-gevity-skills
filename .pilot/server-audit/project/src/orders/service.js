'use strict';

const { invalid, notFound, conflict } = require('../lib/errors');
const { isAmount, sumLines } = require('../lib/money');
const { paginate } = require('../lib/pagination');

const TRANSITIONS = {
  pending: ['paid', 'cancelled'],
  paid: ['shipped', 'cancelled'],
  shipped: ['delivered', 'cancelled'],
  delivered: [],
  cancelled: [],
};

function normalizeItems(items) {
  if (!Array.isArray(items) || items.length === 0) throw invalid('an order needs at least one item');
  return items.map((item) => {
    if (!item || typeof item.sku !== 'string' || item.sku.trim() === '') throw invalid('every item needs a sku');
    if (!isAmount(item.unitPrice)) throw invalid('unitPrice must be a positive amount with at most two decimals');
    if (!Number.isInteger(item.quantity) || item.quantity < 1) throw invalid('quantity must be a positive integer');
    return { sku: item.sku.trim(), unitPrice: item.unitPrice, quantity: item.quantity };
  });
}

function createOrderService({ store }) {
  function create(user, { items }) {
    const lines = normalizeItems(items);
    return store.insert('orders', {
      userId: user.id,
      items: lines,
      total: sumLines(lines),
      status: 'pending',
      createdAt: new Date().toISOString(),
    });
  }

  function get(id) {
    const order = store.get('orders', id);
    if (!order) throw notFound('order not found');
    return order;
  }

  function getOwned(user, id) {
    const order = get(id);
    if (user.role !== 'admin' && order.userId !== user.id) throw notFound('order not found');
    return order;
  }

  function list(user, query) {
    const visible = store.list('orders', (order) => user.role === 'admin' || order.userId === user.id);
    return paginate(visible, query);
  }

  function all() {
    return store.list('orders');
  }

  function transition(order, next, patch = {}) {
    if (!TRANSITIONS[order.status].includes(next)) {
      throw conflict(`order cannot move from ${order.status} to ${next}`);
    }
    return store.update('orders', order.id, { ...patch, status: next, updatedAt: new Date().toISOString() });
  }

  return {
    create,
    get,
    getOwned,
    list,
    all,
    cancel: (user, id) => transition(getOwned(user, id), 'cancelled'),
    ship: (id) => transition(get(id), 'shipped'),
    deliver: (id) => transition(get(id), 'delivered'),
    markPaid: (id, paymentId) => transition(get(id), 'paid', { paymentId }),
  };
}

module.exports = { createOrderService };
