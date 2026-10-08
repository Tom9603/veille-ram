// Réseau d'abord pour tout (appli et données) : on affiche toujours la dernière
// version publiée. Le cache ne sert qu'hors ligne ou si le réseau traîne trop.
const VERSION = "veille-ram-v6";
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
const SHELL_TIMEOUT_MS = 4000;

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

function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("timeout")), ms);
    promise.then((v) => { clearTimeout(timer); resolve(v); }, (e) => { clearTimeout(timer); reject(e); });
  });
}

async function networkFirst(request, { timeout, markCached }) {
  const cache = await caches.open(VERSION);
  const key = request.mode === "navigate" ? "./" : request.url.split("?")[0];
  const network = fetch(request, { cache: "no-store" }).then(async (response) => {
    if (response.ok) await cache.put(key, response.clone());
    return response;
  });
  try {
    return await (timeout ? withTimeout(network, timeout) : network);
  } catch (err) {
    const cached = await cache.match(key, { ignoreSearch: true });
    if (!cached) return network;  // rien en cache : on attend quand même le réseau
    if (!markCached) return cached;
    const headers = new Headers(cached.headers);
    headers.set("x-veille-cache", "1");
    return new Response(await cached.blob(), { status: 200, headers });
  }
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  event.respondWith(isData(url)
    ? networkFirst(event.request, { markCached: true })
    : networkFirst(event.request, { timeout: SHELL_TIMEOUT_MS }));
});
