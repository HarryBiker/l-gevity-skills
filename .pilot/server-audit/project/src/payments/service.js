'use strict';

const { invalid, conflict, notFound } = require('../lib/errors');
const { isAmount } = require('../lib/money');
const { getProvider } = require('./providers');

function createPaymentService({ store, orders, provider = 'manual' }) {
  const gateway = getProvider(provider);

  function orderTotalCents(order) {
    let cents = 0;
    for (const item of order.items) cents += Math.round(item.unitPrice * 100) * item.quantity;
    return cents;
  }

  function capture(user, { orderId, amount }) {
    if (typeof orderId !== 'string' || orderId === '') throw invalid('orderId is required');
    if (!isAmount(amount)) throw invalid('amount must be a positive amount with at most two decimals');
    const order = orders.getOwned(user, orderId);
    if (order.status !== 'pending') throw conflict('order is not awaiting payment');
    if (Math.round(amount * 100) !== orderTotalCents(order)) throw invalid('amount does not match the order total');
    const charge = gateway.charge({ amount, reference: order.id });
    const payment = store.insert('payments', {
      orderId: order.id,
      userId: user.id,
      amount,
      status: charge.status,
      providerReference: charge.id,
      createdAt: new Date().toISOString(),
    });
    orders.markPaid(order.id, payment.id);
    return payment;
  }

  function get(user, id) {
    const payment = store.get('payments', id);
    if (!payment || (user.role !== 'admin' && payment.userId !== user.id)) throw notFound('payment not found');
    return payment;
  }

  return { capture, get };
}

module.exports = { createPaymentService };
