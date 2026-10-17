// Retire the previous Liftosaur PWA service worker. The old worker was served
// from this URL and cached the app at the GitHub Pages project root.
self.addEventListener('install', event => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const scopePath = new URL(self.registration.scope).pathname;
    const cachePrefix = `liftosaur-app:${scopePath}:`;
    const oldCaches = (await caches.keys()).filter(name => name.startsWith(cachePrefix));
    await Promise.all(oldCaches.map(name => caches.delete(name)));
    await self.clients.claim();

    // Keep this worker active long enough to clear the old cache and reload
    // open PWA windows, then unregister it so the progress site stays network-only.
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    await self.registration.unregister();
    await Promise.all(windows.map(client => client.navigate(client.url)));
  })());
});
