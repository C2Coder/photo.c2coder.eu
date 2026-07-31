# photo.c2coder.eu

Source for [photo.c2coder.eu](https://photo.c2coder.eu) — my photography
portfolio, organized as dated "rolls" (one shoot/event per entry, with a
lightbox gallery). A static site built by a small Python + Jinja2 generator,
deployed to GitHub Pages, plus a local-only admin UI for adding rolls without
hand-editing JSON.

The main site at [c2coder.eu](https://c2coder.eu) (`../c2coder.github.io` in
this checkout) is a sibling site built the same way — see its `DESIGN.md` for
the shared visual language between the two.

## Layout

```
content/
  site.json      # site chrome: nav, hero copy, about text, contact block
  projects.json  # one entry per roll: metadata + which images belong to it
portfolio/
  <slug>/        # the actual image files for each roll
templates/
  index.html     # the whole site: homepage + lightbox gallery
static/          # CSS, images (copied into dist/ as-is)
build.py         # renders content/*.json through templates/index.html into dist/
admin.py         # local-only Flask UI (127.0.0.1:8002) for managing rolls
```

## Content model

Each entry in `content/projects.json` → `projects` is a "roll":

```
{
  "slug": "my-event-2026",
  "title": "...", "description": "...", "showcase": "...",
  "date": "2026-04-11", "place": "...",
  "image": "1.jpg",            // cover thumbnail
  "images": ["1.jpg", "2.jpg"] // full gallery, cover first
}
```

- `description` is the short blurb on the roll card. `showcase` is the longer
  note shown inside the lightbox when a roll is opened.
- `date` must be `YYYY-MM-DD` (zero-padded) — rolls are sorted newest-first by
  this field at build time.
- Images referenced by `image`/`images` live under `portfolio/<slug>/`.

## Build & run

Requires Python 3 and the packages in `requirements.txt`
(`Jinja2`, `livereload`, `Flask`).

```
make build       # renders content/*.json + templates/index.html -> dist/
make serve       # build once, then serve dist/ on :8001
make serve-live  # build + rebuild on every content/template/asset change, serve on :8001
make admin       # local admin UI on http://127.0.0.1:8002 for adding/editing/deleting rolls
```

Equivalent to `python build.py` / `python build.py --serve` / `python admin.py`.

The admin UI handles slugging, image uploads, cover selection, and deleting a
roll (JSON entry + its image folder) — it writes straight to
`content/projects.json` and `portfolio/`, then rebuilds `dist/`, so you rarely
need to touch the JSON by hand. It's bound to `127.0.0.1` only and is never
part of the deployed site.

## Deployment

Pushing to `main` runs `.github/workflows/pages.yml`, which builds the site and
publishes `dist/` to GitHub Pages. The custom domain (`photo.c2coder.eu`) is set
via the `CNAME` file at the repo root, which `build.py` copies into `dist/` on
every build.
