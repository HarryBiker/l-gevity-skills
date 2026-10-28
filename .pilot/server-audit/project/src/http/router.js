'use strict';

const { AppError, notFound } = require('../lib/errors');
const { sendJson, sendText, readJson } = require('./respond');

const STATUS_BY_CODE = {
  invalid: 400,
  unauthorized: 401,
  forbidden: 403,
  not_found: 404,
  conflict: 409,
};

const BODY_METHODS = new Set(['POST', 'PUT', 'PATCH']);

function matchPath(parts, segments) {
  if (parts.length !== segments.length) return null;
  const params = {};
  for (let i = 0; i < parts.length; i += 1) {
    if (parts[i].startsWith(':')) {
      params[parts[i].slice(1)] = decodeURIComponent(segments[i]);
    } else if (parts[i] !== segments[i]) {
      return null;
    }
  }
  return params;
}

function createRouter() {
  const routes = [];

  function add(method, pattern, handler) {
    routes.push({ method, parts: pattern.split('/').filter(Boolean), handler });
  }

  async function dispatch(req, res) {
    const url = new URL(req.url, 'http://localhost');
    const segments = url.pathname.split('/').filter(Boolean);
    let pathMatched = false;
    for (const route of routes) {
      const params = matchPath(route.parts, segments);
      if (!params) continue;
      pathMatched = true;
      if (route.method !== req.method) continue;
      const body = BODY_METHODS.has(req.method) ? await readJson(req) : {};
      const query = Object.fromEntries(url.searchParams);
      const result = await route.handler({ req, params, query, body });
      if (result.text !== undefined) return sendText(res, result.status, result.text, result.contentType);
      return sendJson(res, result.status, result.body);
    }
    if (pathMatched) return sendJson(res, 405, { error: 'method not allowed' });
    throw notFound('route not found');
  }

  async function handle(req, res) {
    try {
      await dispatch(req, res);
    } catch (error) {
      if (error instanceof URIError) return sendJson(res, 400, { error: 'malformed path' });
      if (error instanceof AppError) return sendJson(res, STATUS_BY_CODE[error.code] || 400, { error: error.message });
      return sendJson(res, 500, { error: 'internal error' });
    }
  }

  return { add, handle };
}

module.exports = { createRouter };
