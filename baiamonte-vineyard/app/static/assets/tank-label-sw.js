const VERSION = "1.4.22";
const CACHE = `baiamonte-cellar-label-${VERSION}`;
const scopeUrl = new URL(self.registration.scope);
const scoped = (path) => new URL(path.replace(/^\//, ""), scopeUrl).toString();
const SHELL = [
  scoped(`assets/tank-label.css?v=${VERSION}`),
  scoped(`assets/tank-label.js?v=${VERSION}`),
  scoped(`brand/logo.png?v=${VERSION}`),
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key.startsWith("baiamonte-cellar-label-") && key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data?.type !== "CACHE_LABEL_PAGE") return;
  const url = new URL(String(event.data.url || ""));
  const relative = url.pathname.slice(scopeUrl.pathname.length);
  if (url.origin !== scopeUrl.origin || !url.pathname.startsWith(scopeUrl.pathname) || !/^(?:tank|kiosk)\/[A-Za-z0-9-]+$/.test(relative)) return;
  event.waitUntil(fetch(url, {cache: "no-store"}).then((response) => {
    if (!response.ok) return;
    return caches.open(CACHE).then((cache) => cache.put(url.toString(), response));
  }).catch(() => {}));
});

const offlineResponse = async (request) => {
  const cached = await caches.match(request);
  if (!cached) return null;
  const headers = new Headers(cached.headers);
  headers.set("X-Baiamonte-Offline", "1");
  return new Response(await cached.clone().arrayBuffer(), {status: cached.status, statusText: cached.statusText, headers});
};

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== scopeUrl.origin || !url.pathname.startsWith(scopeUrl.pathname)) return;
  const relative = url.pathname.slice(scopeUrl.pathname.length);
  const isLabelPage = request.mode === "navigate" && /^(?:tank|kiosk)\/[A-Za-z0-9-]+$/.test(relative);
  const isLabelData = /^api\/(?:tank|kiosk)\/[A-Za-z0-9-]+$/.test(relative);
  const isShell = /^(?:assets\/tank-label\.(?:css|js)|brand\/(?:logo\.png|icon\.(?:png|svg)))$/.test(relative);
  if (!isLabelPage && !isLabelData && !isShell) return;

  if (isShell) {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      if (response.ok) caches.open(CACHE).then((cache) => cache.put(request, response.clone()));
      return response;
    })));
    return;
  }

  event.respondWith(fetch(request).then(async (response) => {
    if (response.ok) {
      caches.open(CACHE).then((cache) => cache.put(request, response.clone()));
      return response;
    }
    return (await offlineResponse(request)) || response;
  }).catch(async () => (await offlineResponse(request)) || new Response("Cellar label unavailable offline", {status: 503})));
});
