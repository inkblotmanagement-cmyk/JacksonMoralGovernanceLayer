// Runtime configuration for the JMGL dashboard. Overwrite this file at deploy time
// (the nginx image generates it from JMGL_PUBLIC_API_BASE_URL).
// apiBaseUrl: "" means same origin (the dashboard and API are served behind one host).
window.__JMGL_CONFIG__ = { apiBaseUrl: "" };
