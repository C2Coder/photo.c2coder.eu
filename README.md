# photo.c2coder.eu

Source for [photo.c2coder.eu](https://photo.c2coder.eu) - my photography
portfolio, organized as dated "rolls" (one shoot/event per entry, with a
lightbox gallery), plus full albums with a zip download. A static site built by
a small Python + Jinja2 generator, deployed to GitHub Pages. Images are served
from Cloudflare R2, and content is managed through an admin UI on hetzner.

The main site at [c2coder.eu](https://c2coder.eu) (`../c2coder.github.io` in
this checkout) is a sibling site built the same way - see its `DESIGN.md` for
the shared visual language between the two.

## Layout

```
content/
  site.json      # site chrome: nav, hero copy, about text, contact block, `cdn` base URL
  projects.json  # rolls: a few cherry-picked photos each, optional link to an album
  albums.json    # albums: every photo of an event + the zip download
templates/       # base.html, index.html (homepage), album.html (/albums/<slug>/)
static/          # CSS, JS, icons (copied into dist/ as-is)
build.py         # renders content/*.json into dist/
admin.py         # admin UI (photo-admin.c2cdn.eu, or locally with `make admin`)
media.py         # image processing + R2 upload, used by the admin
deploy/          # hetzner setup for the admin
docs/            # cloudflare.md - CDN, Access, rate limiting
```

No images live in the repo. They are all on R2 behind `https://photo.c2cdn.eu`
(see `docs/cloudflare.md`).

## Content model

A roll (`projects.json`):

```
{
  "slug": "my-event-2026", "title": "...", "description": "...", "showcase": "...",
  "date": "2026-04-11", "place": "...",
  "image": "1-ab12cd34.jpg",          // cover, also first in images
  "images": ["1-ab12cd34.jpg", ...],  // rolls/<slug>/<name> and rolls/<slug>/thumb/<name> on R2
  "album": "my-event-2026"            // optional, slug of an album
}
```

An album (`albums.json`) has `slug`, `title`, `date`, `place`, `description`,
`zip` (R2 key), `zip_size` and `images` (the same name scheme under `albums/<slug>/`).

## Admin

`https://photo-admin.c2cdn.eu`, behind Cloudflare Access (email code to me@c2coder.eu).
It manages rolls, albums and `site.json`. Each change is committed and pushed to `main`
from its own clone (`~/.local/share/photo-admin/repo` on hetzner), so the site
rebuilds about a minute later. Run `git pull` before editing content locally.

- Roll images are uploaded one by one, each gets a thumbnail, and it is downscaled to
  2048 px only if larger.
- Album zips go from the browser straight to R2 (presigned PUT, up to 5 GB). The admin
  then extracts the `.jpg` files, makes thumbnails and web copies, and publishes. The zip is
  served exactly as uploaded. A new zip replaces the album's photos.

Locally: `make admin` (127.0.0.1:8327, no auth, writes `content/` directly without
committing). It needs the R2 variables from `~/.config/photo-admin/env` in the environment.

Hetzner setup: create `~/.config/photo-admin/env` (`R2_ENDPOINT`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `CF_ACCESS_TEAM`, `CF_ACCESS_AUD`), then
`sudo bash deploy/deploy.sh`. On the first run it prints the deploy key command for GitHub.

## Build & run

```
make build       # renders content/*.json + templates -> dist/
make serve       # build once, then serve dist/ on :8001
make serve-live  # rebuild on every content/template/asset change, serve on :8001
make admin       # local admin on http://127.0.0.1:8327
```

## Deployment

Pushing to `main` runs `.github/workflows/pages.yml`, which builds the site and
publishes `dist/` to GitHub Pages. The custom domain (`photo.c2coder.eu`) is set
via the `CNAME` file at the repo root, which `build.py` copies into `dist/` on
every build.
