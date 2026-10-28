'use strict';

const crypto = require('node:crypto');

const providers = new Map();

function registerProvider(name, provider) {
  if (!provider || typeof provider.charge !== 'function') {
    throw new TypeError(`payment provider ${name} must implement charge()`);
  }
  providers.set(name, provider);
}

function getProvider(name) {
  const provider = providers.get(name);
  if (!provider) throw new Error(`unknown payment provider: ${name}`);
  return provider;
}

registerProvider('manual', {
  charge({ amount, reference }) {
    return { id: `man_${crypto.randomUUID()}`, status: 'captured', amount, reference };
  },
});

module.exports = { registerProvider, getProvider };
