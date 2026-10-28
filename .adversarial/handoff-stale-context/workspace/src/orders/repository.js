export async function saveOrder(store, order) {
  await store.put(order.id, order);
}
