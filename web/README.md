# JMGL dashboard

React + TypeScript (Vite) single-page app: evaluate an action, browse the laws, view the audit
log (admin key), and enter an API key. Accessible (labels, live regions, keyboard focus, skip
link, 44 px touch targets, reduced-motion and dark-mode support) and mobile-friendly.

```bash
npm ci
npm run dev        # http://localhost:5173, proxies /v1 to http://127.0.0.1:8000 (VITE_PROXY_TARGET)
npm run build      # static files in dist/
npm test           # vitest
```

## Pointing at an API

* **Same origin (default):** serve `dist/` and the API under one hostname (nginx image, Render
  rewrites, or the Terraform load balancer). `config.js` keeps `apiBaseUrl: ""`.
* **Different origin:** edit `dist/config.js` at deploy time (or set `JMGL_PUBLIC_API_BASE_URL` in
  the nginx image) and add the dashboard origin to the API's `JMGL_CORS_ORIGINS`.

The API key is kept in `sessionStorage` (cleared when the tab closes) unless the user ticks
"Remember on this device".

## Container

`Dockerfile` builds with Node 22 and serves with `nginx-unprivileged` on port 8080 (non-root,
read-only root filesystem OK, only `/tmp` must be writable). Environment:
`JMGL_API_UPSTREAM` (default `http://api:8000`), `JMGL_PUBLIC_API_BASE_URL` (default empty).
`/metrics`, `/docs` and `/openapi.json` are not exposed through the dashboard host.
