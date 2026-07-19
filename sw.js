// sw.js
const CACHE_NAME = 'pos-cache-v1';
const urlsToCache = [
  '/pos',
  '/static/uploads/products/fallback.png',  // optional
  // Add any other static assets (CSS, JS) that are hosted externally? 
  // But we use CDN links, which are not cached here for simplicity.
];

// Install: cache the core page
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
      .then(() => self.skipWaiting())
  );
});

// Activate: clean up old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(name => name !== CACHE_NAME)
          .map(name => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: serve from cache, fallback to network
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
      .catch(() => {
        // Optionally return a fallback offline page
        return new Response('Offline – please connect to the internet', { status: 503 });
      })
  );
});