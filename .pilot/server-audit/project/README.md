# orders-service

HTTP API for customer accounts, orders, payments, and order exports.
Node.js 20 or later; no third-party dependencies.

```sh
npm test                                  # node --test
APP_SECRET=change-me REPORT_DIR=./reports \
ADMIN_EMAIL=ops@example.com ADMIN_PASSWORD=change-me-too npm start
```

## API

| Method | Path | Caller | Result |
|:--|:--|:--|:--|
| POST | `/users` | anyone | Register `{ email, password, name }`; 201 with the profile |
| POST | `/sessions` | anyone | `{ email, password }`; 201 with `{ token }` |
| GET | `/users/me` | customer | Own profile |
| GET | `/users` | admin | Page of profiles |
| POST | `/orders` | customer | `{ items: [{ sku, unitPrice, quantity }] }`; 201 with the order |
| GET | `/orders` | customer | Page of own orders; admins see every order |
| GET | `/orders/:id` | customer | One order |
| POST | `/orders/:id/cancel` | customer | Cancel an order |
| POST | `/orders/:id/ship` | admin | Mark a paid order shipped |
| POST | `/orders/:id/deliver` | admin | Mark a shipped order delivered |
| POST | `/payments` | customer | `{ orderId, amount }`; 201 with the payment, the order becomes `paid` |
| GET | `/payments/:id` | customer | One payment |
| POST | `/reports/orders` | admin | Export every order as CSV; 201 with `{ name }` |
| GET | `/reports/:name` | admin | Download an export |

## Rules

- Requests authenticate with `Authorization: Bearer <token>`. Tokens are
  signed with `APP_SECRET` and expire after one hour.
- Customers read and change only their own orders and payments. Admins read
  all of them.
- Order lifecycle: `pending` → `paid` → `shipped` → `delivered`. A customer
  may cancel an order while it is `pending` or `paid`; a shipped or delivered
  order can no longer be cancelled.
- `unitPrice`, `amount`, and `total` are numbers in the currency unit with at
  most two decimals. An order total is exact to the cent.
- A payment amount must equal the order total.
- List endpoints accept `page` (1-based, default 1) and `pageSize` (default
  20, maximum 100) and return `{ items, page, pageSize, total, totalPages }`.
  `totalPages` is the number of pages needed to show every item, at least 1.
- Exports are written to and served from `REPORT_DIR`.
- Errors return `{ error }` with 400 for invalid input, 401 when
  unauthenticated, 403 for a missing role, 404 for unknown resources and for
  resources the caller may not see, and 409 for a state conflict.
