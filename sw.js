// Coquille de l'appli en cache (mise à jour en arrière-plan),
// données toujours demandées au réseau d'abord, avec repli sur le cache hors ligne.
const VERSION = "veille-ram-v3";
const SHELL = [
  "./",
  "index.html",
  "style.css",
  "app.js",
  "manifest.webmanifest",
  "icons/icon-192.png",
  "icons/apple-touch-icon.png",
  "icons/favicon-32.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

function isData(url) {
  return url.pathname.endsWith(".json");
}

async function networkFirst(request) {
  const cache = await caches.open(VERSION);
  const key = request.url.split("?")[0];
  try {
    const response = await fetch(request, { cache: "no-store" });
    if (response.ok) await cache.put(key, response.clone());
    return response;
  } catch (err) {
    const cached = await cache.match(key);
    if (!cached) throw err;
    const headers = new Headers(cached.headers);
    headers.set("x-veille-cache", "1");
    return new Response(await cached.blob(), { status: 200, headers });
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(VERSION);
  const cached = await cache.match(request, { ignoreSearch: true });
  const refresh = fetch(request)
    .then((response) => {
      if (response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => cached);
  return cached || refresh;
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  event.respondWith(isData(url) ? networkFirst(event.request) : staleWhileRevalidate(event.request));
});
