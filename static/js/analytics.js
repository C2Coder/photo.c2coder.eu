const GA_ID = 'G-QH4JFJHT9Z';

window.dataLayer = window.dataLayer || [];
function gtag() { dataLayer.push(arguments); }
gtag('consent', 'default', { analytics_storage: 'denied', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied' });

(() => {
  const bar = document.getElementById('consent');
  let loaded = false;

  const get = () => { try { return localStorage.getItem('photo-consent'); } catch { return null; } };
  const set = v => { try { localStorage.setItem('photo-consent', v); } catch {} };

  function load() {
    gtag('consent', 'update', { analytics_storage: 'granted' });
    if (loaded) return;
    loaded = true;
    gtag('js', new Date());
    gtag('config', GA_ID);
    const s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
    document.head.appendChild(s);
  }

  function clearCookies() {
    const host = location.hostname.split('.');
    const domains = [location.hostname];
    for (let i = 1; i < host.length - 1; i++) domains.push('.' + host.slice(i).join('.'));
    document.cookie.split(';').forEach(c => {
      const n = c.split('=')[0].trim();
      if (!n.startsWith('_ga')) return;
      document.cookie = n + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
      domains.forEach(d => document.cookie = n + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; domain=' + d);
    });
  }

  function choose(v) {
    set(v);
    bar.hidden = true;
    if (v === 'yes') load();
    else {
      gtag('consent', 'update', { analytics_storage: 'denied' });
      clearCookies();
    }
  }

  document.getElementById('consent_yes').onclick = () => choose('yes');
  document.getElementById('consent_no').onclick = () => choose('no');
  document.getElementById('cookies').onclick = () => { bar.hidden = false; };

  const c = get();
  if (c === 'yes') load();
  else if (c !== 'no') bar.hidden = false;
})();
