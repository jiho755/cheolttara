const CACHE = 'cheolttara-v2';
const FILES = ['./', 'index.html', 'styles.css', 'app.js', 'manifest.json', 'data/seasonal_items.json', 'data/places.json', 'data/festivals.json',
  'icons/icon.svg', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/icon-maskable-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  // 축제 데이터는 매일 바뀌므로 네트워크 우선 (오프라인이면 캐시). 외부 이미지는 위에서 이미 제외됨.
  if (url.pathname.endsWith('/data/festivals.json')) {
    e.respondWith(fetch(req).then((res) => {
      if (res && res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {}); }
      return res;
    }).catch(() => caches.match(req, { ignoreSearch: true })));
    return;
  }
  e.respondWith(
    caches.match(req, { ignoreSearch: true }).then((hit) => {
      const net = fetch(req).then((res) => {
        if (res && res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req.mode === 'navigate' ? 'index.html' : req, copy)).catch(() => {}); }
        return res;
      });
      if (hit) { net.catch(() => {}); return hit; }
      return net.catch(() => caches.match('index.html'));
    })
  );
});
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: 'window' }).then((cs) => cs.length ? cs[0].focus() : self.clients.openWindow('./')));
});
