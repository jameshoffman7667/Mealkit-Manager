/* Service worker. Caches only the app shell. It never stores API responses, sign-in pages or any
   page that shows account data: navigations always go to the network and fall back to /offline. */
const VERSION = "0.4.1";
const CACHE = "mealkit-manager-v" + VERSION;
const SHELL = [
  "/offline",
  "/static/style.css",
  "/static/app.js",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  // No skipWaiting here: a waiting worker is activated only when the user taps "Reload" in the page.
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (req.mode === "navigate") {
    // Network first. Pages are never cached; only the offline page is shown when the server is unreachable.
    event.respondWith(fetch(req).catch(() => caches.match("/offline")));
    return;
  }
  // Shell files only (cache first). Everything else, including /api/ and /export.json, goes to the network.
  if (SHELL.includes(url.pathname)) {
    event.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
  }
});
