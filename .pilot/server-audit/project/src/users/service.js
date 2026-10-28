'use strict';

const crypto = require('node:crypto');
const { invalid, conflict } = require('../lib/errors');

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD_LENGTH = 8;

function hashPassword(password, salt) {
  return crypto.scryptSync(password, salt, 32).toString('hex');
}

function normalizeEmail(email) {
  return typeof email === 'string' ? email.trim().toLowerCase() : '';
}

function toPublic(user) {
  return { id: user.id, email: user.email, name: user.name, role: user.role, createdAt: user.createdAt };
}

function createUserService({ store }) {
  function register({ email, password, name }, role = 'customer') {
    const normalized = normalizeEmail(email);
    if (!EMAIL_PATTERN.test(normalized)) throw invalid('a valid email is required');
    if (typeof password !== 'string' || password.length < MIN_PASSWORD_LENGTH) {
      throw invalid(`password must be at least ${MIN_PASSWORD_LENGTH} characters`);
    }
    if (typeof name !== 'string' || name.trim() === '') throw invalid('name is required');
    if (store.findOne('users', (user) => user.email === normalized)) throw conflict('email already registered');
    const salt = crypto.randomBytes(16).toString('hex');
    return toPublic(store.insert('users', {
      email: normalized,
      name: name.trim(),
      role,
      salt,
      passwordHash: hashPassword(password, salt),
      createdAt: new Date().toISOString(),
    }));
  }

  function verifyCredentials(email, password) {
    if (typeof password !== 'string') return null;
    const normalized = normalizeEmail(email);
    const user = store.findOne('users', (candidate) => candidate.email === normalized);
    if (!user) return null;
    const expected = Buffer.from(user.passwordHash, 'hex');
    const actual = Buffer.from(hashPassword(password, user.salt), 'hex');
    return crypto.timingSafeEqual(expected, actual) ? toPublic(user) : null;
  }

  function find(id) {
    const user = store.get('users', id);
    return user ? toPublic(user) : null;
  }

  return { register, verifyCredentials, find, toPublic };
}

module.exports = { createUserService };
