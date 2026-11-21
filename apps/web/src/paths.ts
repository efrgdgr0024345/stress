/** Keep requests and navigation inside the current application mount. */
export const APP_BASE = new URL(".", window.location.href).pathname;
export const appPath = (path = "") => APP_BASE + path.replace(/^\//, "");
