self.addEventListener("install", event => self.skipWaiting());

self.addEventListener("activate", event => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", event => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {}

  const title = data.title || "Rugby Today";
  const options = {
    body: data.body || data.alert || "There is a new rugby update.",
    tag: data.tag || "rugby-today",
    data: { url: data.url || "./" }
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

self.addEventListener("notificationclick", event => {
  event.notification.close();

  const url =
    event.notification.data && event.notification.data.url
      ? event.notification.data.url
      : "./";

  event.waitUntil(clients.openWindow(url));
});
