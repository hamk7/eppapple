const CACHE='preisfinder-v4-ipad';
const CORE=['./','./index.html','./manifest.webmanifest','./icon-180.png','./icon-512.png','./current.json','./history-summary.json'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(Promise.all([
  self.clients.claim(),
  caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))
])));
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(u.origin!==location.origin) return;
  if(u.pathname.endsWith('/current.json') || u.pathname.endsWith('/history-summary.json')){
    e.respondWith(fetch(e.request).then(r=>{
      const copy=r.clone();
      const clean=new Request(u.origin+u.pathname);
      caches.open(CACHE).then(c=>c.put(clean,copy));
      return r;
    }).catch(()=>caches.match(new Request(u.origin+u.pathname),{ignoreSearch:true})));
  }else{
    e.respondWith(fetch(e.request).then(r=>{
      const copy=r.clone(); caches.open(CACHE).then(c=>c.put(e.request,copy)); return r;
    }).catch(()=>caches.match(e.request,{ignoreSearch:true})));
  }
});
