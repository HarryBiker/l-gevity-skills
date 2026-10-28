'use strict';

const crypto = require('node:crypto');

function createStore() {
  const collections = new Map();

  function collection(name) {
    if (!collections.has(name)) collections.set(name, new Map());
    return collections.get(name);
  }

  return {
    insert(name, doc) {
      const record = { ...doc, id: crypto.randomUUID() };
      collection(name).set(record.id, record);
      return structuredClone(record);
    },
    get(name, id) {
      const record = collection(name).get(id);
      return record ? structuredClone(record) : null;
    },
    update(name, id, patch) {
      const record = collection(name).get(id);
      if (!record) return null;
      Object.assign(record, patch);
      return structuredClone(record);
    },
    list(name, predicate = () => true) {
      return [...collection(name).values()].filter(predicate).map((record) => structuredClone(record));
    },
    findOne(name, predicate) {
      for (const record of collection(name).values()) {
        if (predicate(record)) return structuredClone(record);
      }
      return null;
    },
  };
}

module.exports = { createStore };
