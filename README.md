# RAS storefront preview

Initial storefront for RAS International Trading WLL, intended for rasqatar.com.

## Preview locally

Open index.html in a browser, or serve this directory with `python3 -m http.server 8000` and visit http://localhost:8000.

## Included

- 84 unique barcode entries from four client-supplied PDF lists; identical duplicate excluded.
- Supplier-PDF product images, descriptions, reference numbers, prices and carton quantities.
- Product search, category/list filters and responsive layout.
- Device-local draft cart with quantity controls. No orders, payments or personal information are submitted.

## Before launch

Confirm product scope (pet supplies and/or groceries), retail versus wholesale selling units, customer prices and currency for Cozina. Confirm stock, original product images, delivery areas/fees, business contact details and customer policies. Implement and test a secure order backend, stock validation, admin authentication, payment gateway/webhooks and notifications. Configure hosting and the domain only after deployment review. PDF descriptions and prices have not been independently approved for retail use.

## Validation

84 unique barcodes checked; JavaScript syntax check passed. Browser interaction and visual tests remain pending: the current execution environment has no installed Playwright Chromium binary. This is an initial frontend preview, not a production-ready ecommerce system.
