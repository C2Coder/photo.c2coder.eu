# Cloudflare setup (c2cdn.eu)

Zone `c2cdn.eu` (Free plan), registered at wedos, nameservers on Cloudflare.
Account tokens are in `~/config/cloudflare/photo.token` (never in the repo).

| Thing | Value |
|---|---|
| R2 bucket | `photo`, EU jurisdiction (API calls need `cf-r2-jurisdiction: eu`) |
| Public bucket domain | `photo.c2cdn.eu` (R2 custom domain, cached by Cloudflare) |
| Bucket CORS | PUT/GET/HEAD from `https://photo-admin.c2cdn.eu` and `http://127.0.0.1:8327` |
| Admin | `photo-admin.c2cdn.eu` A/AAAA -> hetzner, proxied |
| Access app `photo-admin` | allow `me@c2coder.eu` (email code), team `c2coder.cloudflareaccess.com` |
| Access app `photo-admin acme` | bypass on `/.well-known/acme-challenge` so certbot renewals work |
| Rate limit rule | `*.zip` on `photo.c2cdn.eu`: more than 5 requests / 10 s per IP -> blocked for 10 s |

## Why zip downloads can't hurt

- R2 has no egress fees, so downloads cost nothing. Reads are 10M/month free, then $0.36/M.
- Files under 512 MB are served from Cloudflare's cache and don't touch R2 at all.
- The rate limit rule above, plus Cloudflare's own DDoS protection.
- Zips are uploaded once and never generated on request, so there's no CPU to exhaust.

## R2 layout

```
rolls/<slug>/<stem>-<hash>.jpg          web size (max 2048 px, original bytes if already smaller)
rolls/<slug>/thumb/<stem>-<hash>.jpg    800 px thumbnail
albums/<slug>/<slug>-<rand>.zip         the uploaded zip, untouched, Content-Disposition attachment
albums/<slug>/<stem>-<hash>.jpg
albums/<slug>/thumb/<stem>-<hash>.jpg
```

Everything is `Cache-Control: immutable`. Names change with content, so the cache never goes stale.
