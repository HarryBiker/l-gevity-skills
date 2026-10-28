'use strict';

function isAmount(value) {
  return typeof value === 'number'
    && Number.isFinite(value)
    && value > 0
    && Math.abs(value * 100 - Math.round(value * 100)) < 1e-6;
}

function lineTotal(item) {
  return item.unitPrice * item.quantity;
}

function sumLines(items) {
  return items.reduce((total, item) => total + lineTotal(item), 0);
}

module.exports = { isAmount, sumLines };
