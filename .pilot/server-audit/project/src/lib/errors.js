'use strict';

class AppError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'AppError';
    this.code = code;
  }
}

const invalid = (message) => new AppError('invalid', message);
const unauthorized = (message = 'authentication required') => new AppError('unauthorized', message);
const forbidden = (message = 'not allowed') => new AppError('forbidden', message);
const notFound = (message = 'not found') => new AppError('not_found', message);
const conflict = (message) => new AppError('conflict', message);

module.exports = { AppError, invalid, unauthorized, forbidden, notFound, conflict };
