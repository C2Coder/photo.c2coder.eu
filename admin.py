"""Admin UI for rolls, albums and site texts (photo-admin.c2cdn.eu).

Content lives as JSON in a git clone of this repo (PHOTO_REPO). Every change
is committed and pushed, which triggers the GitHub Pages build. Images go
straight to R2 (see media.py). Auth is Cloudflare Access - every request must
carry a valid Access JWT, so the hetzner IP alone gets you nothing.

Config comes from the environment (~/.config/photo-admin/env on hetzner):
R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, PHOTO_REPO,
GIT_SSH_KEY, CF_ACCESS_TEAM, CF_ACCESS_AUD. ADMIN_DEV=1 skips auth (local only).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path, PurePath

from flask import Flask, abort, jsonify, redirect, render_template_string, request, url_for

import media

ROOT = Path(__file__).resolve().parent
REPO = Path(os.environ.get("PHOTO_REPO", ROOT))
CONTENT = REPO / "content"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
DEV = os.environ.get("ADMIN_DEV") == "1"

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 95 * 1024 * 1024  # under Cloudflare's 100 MB request limit


# --- auth ---------------------------------------------------------------------

_jwks = None


@app.before_request
def check_access():
    if DEV:
        return
    global _jwks
    import jwt

    token = request.headers.get("Cf-Access-Jwt-Assertion", "")
    try:
        if _jwks is None:
            _jwks = jwt.PyJWKClient(f"https://{os.environ['CF_ACCESS_TEAM']}/cdn-cgi/access/certs")
        key = _jwks.get_signing_key_from_jwt(token).key
        jwt.decode(token, key, algorithms=["RS256"], audience=os.environ["CF_ACCESS_AUD"])
    except Exception:
        abort(403)
    if request.method == "POST" and request.headers.get("Origin", f"https://{request.host}") != f"https://{request.host}":
        abort(403)


# --- content (git) ------------------------------------------------------------

LOCK = threading.Lock()
_last_sync = 0.0


def git(*args: str) -> None:
    env = dict(os.environ)
    if os.environ.get("GIT_SSH_KEY"):
        env["GIT_SSH_COMMAND"] = f"ssh -i {os.environ['GIT_SSH_KEY']} -o IdentitiesOnly=yes"
    subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True, env=env, timeout=60)


def sync(force: bool = False) -> None:
    global _last_sync
    if REPO == ROOT or (not force and time.time() - _last_sync < 30):
        return
    git("fetch", "-q", "origin", "main")
    git("reset", "-q", "--hard", "origin/main")
    _last_sync = time.time()


def load(name: str) -> dict:
    return json.loads((CONTENT / name).read_text(encoding="utf-8"))


def read(name: str) -> dict:
    with LOCK:
        sync()
        return load(name)


def mutate(name: str, message: str, fn) -> None:
    """Re-read `name` from origin, apply fn(data), commit and push."""
    with LOCK:
        sync(force=True)
        data = load(name)
        fn(data)
        with open(CONTENT / name, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        if REPO == ROOT:
            return
        git("add", f"content/{name}")
        git("commit", "-q", "-m", message)
        git("push", "-q", "origin", "HEAD:main")


def find(items: list[dict], slug: str) -> dict:
    item = next((i for i in items if i["slug"] == slug), None)
    if item is None:
        abort(404)
    return item


def by_date(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda i: i.get("date", ""), reverse=True)


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def form_fields(keys: tuple[str, ...]) -> dict:
    return {key: request.form.get(key, "").strip() for key in keys}


ROLL_FIELDS = ("title", "date", "place", "description", "showcase", "album")
ALBUM_FIELDS = ("title", "date", "place", "description")


# --- album processing -----------------------------------------------------------

STATUS: dict[str, dict] = {}


def process_album(slug: str, zip_key: str) -> None:
    status = STATUS[slug]
    prefix = f"albums/{slug}"
    try:
        with tempfile.TemporaryFile() as tmp:
            status["state"] = "downloading zip"
            media.r2().download_fileobj(media.BUCKET, zip_key, tmp)
            size = tmp.tell()
            tmp.seek(0)
            with zipfile.ZipFile(tmp) as zf:
                entries = [
                    e for e in zf.infolist()
                    if not e.is_dir() and "__MACOSX" not in e.filename
                    and not PurePath(e.filename).name.startswith(".")
                    and PurePath(e.filename).suffix.lower() in (".jpg", ".jpeg")
                ]
                entries.sort(key=lambda e: media.natural_key(e.filename))
                if not entries:
                    raise ValueError("no .jpg files in the zip")
                status.update(state="processing", total=len(entries), done=0)
                names = []
                for entry in entries:
                    names.append(media.upload_image(prefix, zf.read(entry), PurePath(entry.filename).name))
                    status["done"] += 1

        old = {}

        def apply(data):
            album = find(data["albums"], slug)
            old.update(zip=album.get("zip"), images=album.get("images", []))
            album.update(zip=zip_key, zip_size=size, images=names)

        status["state"] = "publishing"
        mutate("albums.json", f"album {slug}: new photos", apply)

        stale = [f"{prefix}/{n}" for n in old["images"] if n not in names]
        stale += [f"{prefix}/thumb/{n}" for n in old["images"] if n not in names]
        if old["zip"] and old["zip"] != zip_key:
            stale.append(old["zip"])
        media.delete_keys(stale)
        status["state"] = "done"
    except Exception as exc:
        status.update(state="error", error=str(exc))


# --- pages --------------------------------------------------------------------

BASE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex">
<title>Photo admin</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700;900&family=Roboto+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/css/site.css">
<style>
  .admin-wrap { max-width: 860px; margin: 0 auto; padding: 40px 28px 80px; }
  .admin-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin: 34px 0 20px; flex-wrap: wrap; }
  .admin-head:first-child { margin-top: 0; }
  .admin-head h1, .admin-head h2 { font-size: 1.8rem; margin: 0; }
  .field { margin-bottom: 18px; }
  .field label {
    display: block; font-family: var(--mono); font-size: .72rem; letter-spacing: .08em; text-transform: uppercase;
    color: var(--ink-faint); margin-bottom: 6px;
  }
  .field input[type=text], .field input[type=date], .field input[type=file], .field textarea, .field select {
    width: 100%; font-family: var(--sans); font-size: .95rem; padding: 10px 12px;
    border: 1px solid var(--ink); background: var(--paper); color: var(--ink);
  }
  .field textarea { resize: vertical; min-height: 70px; }
  .field textarea.code { font-family: var(--mono); font-size: .8rem; min-height: 520px; }
  .row { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 0; border-top: 1px solid var(--line); }
  .row img { width: 72px; height: 54px; object-fit: cover; border: 1px solid var(--line); }
  .row-main { display: flex; align-items: center; gap: 16px; }
  .row-actions { display: flex; gap: 10px; }
  .image-grid { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px; }
  .image-card { border: 1px solid var(--line); padding: 8px; font-family: var(--mono); font-size: .72rem; text-align: center; }
  .image-card img { width: 110px; height: 80px; object-fit: cover; margin-bottom: 6px; border: 1px solid var(--line); }
  .image-card label { display: flex; align-items: center; gap: 6px; justify-content: center; margin-top: 4px; color: var(--ink-soft); text-transform: none; letter-spacing: 0; }
  .thumbs { display: grid; grid-template-columns: repeat(auto-fill, minmax(90px, 1fr)); gap: 6px; margin-top: 8px; }
  .thumbs img { width: 100%; aspect-ratio: 4 / 3; object-fit: cover; border: 1px solid var(--line); }
  .flash { font-family: var(--mono); font-size: .8rem; color: var(--accent); margin: 10px 0 20px; }
  .danger { border-color: var(--accent); color: var(--accent); }
  .danger:hover { background: var(--accent); color: var(--accent-contrast); }
  progress { width: 100%; height: 10px; accent-color: var(--accent); }
</style>
</head>
<body>
  <header class="masthead">
    <div class="wrap masthead-row">
      <a href="{{ url_for('index') }}" class="wordmark">Photo admin<span class="wordmark-dot">.</span></a>
      <div class="masthead-controls">
        <a class="ctrl-btn" href="https://photo.c2coder.eu" target="_blank" rel="noopener">SITE</a>
      </div>
    </div>
  </header>
  <div class="admin-wrap">
    {{ body|safe }}
  </div>
</body>
</html>
"""

INDEX_BODY = """
<p class="tag-label">Changes are pushed to GitHub, the site updates in about a minute.</p>
<div class="admin-head">
  <h1>Rolls</h1>
  <a class="btn btn-solid" href="{{ url_for('new_roll') }}">+ Add roll</a>
</div>
{% for p in rolls %}
<div class="row">
  <div class="row-main">
    {% if p.image %}<img src="{{ cdn }}/rolls/{{ p.slug }}/thumb/{{ p.image }}" alt="">{% endif %}
    <div>
      <strong>{{ p.title }}</strong><br>
      <span class="tag-label">{{ p.slug }} · {{ p.date }} · {{ p.images|length }} photos{% if p.album %} · album {{ p.album }}{% endif %}</span>
    </div>
  </div>
  <div class="row-actions">
    <a class="btn btn-line" href="{{ url_for('edit_roll', slug=p.slug) }}">Edit</a>
  </div>
</div>
{% else %}<p class="tag-label">No rolls yet.</p>{% endfor %}

<div class="admin-head">
  <h2>Albums</h2>
  <a class="btn btn-solid" href="{{ url_for('new_album') }}">+ Add album</a>
</div>
{% for a in albums %}
<div class="row">
  <div class="row-main">
    {% if a.images %}<img src="{{ cdn }}/albums/{{ a.slug }}/thumb/{{ a.images[0] }}" alt="">{% endif %}
    <div>
      <strong>{{ a.title }}</strong><br>
      <span class="tag-label">{{ a.slug }} · {{ a.date }} · {{ a.images|length }} photos</span>
    </div>
  </div>
  <div class="row-actions">
    {% if a.images %}<a class="btn btn-line" href="https://photo.c2coder.eu/albums/{{ a.slug }}/" target="_blank" rel="noopener">View</a>{% endif %}
    <a class="btn btn-line" href="{{ url_for('edit_album', slug=a.slug) }}">Edit</a>
  </div>
</div>
{% else %}<p class="tag-label">No albums yet.</p>{% endfor %}

<div class="admin-head">
  <h2>Site</h2>
  <a class="btn btn-line" href="{{ url_for('edit_site') }}">Edit texts</a>
</div>
"""

ROLL_BODY = """
<div class="admin-head">
  <h1>{{ "Edit roll" if roll else "Add roll" }}</h1>
  <a class="btn btn-line" href="{{ url_for('index') }}">&larr; Back</a>
</div>
{% if error %}<p class="flash">{{ error }}</p>{% endif %}
<form method="post">
  {% if not roll %}
  <div class="field"><label>Slug</label><input type="text" name="slug" placeholder="my-event-14-05-2026" required></div>
  {% endif %}
  <div class="field"><label>Date</label><input type="date" name="date" value="{{ roll.date }}" required></div>
  <div class="field"><label>Title</label><input type="text" name="title" value="{{ roll.title }}" required></div>
  <div class="field"><label>Place</label><input type="text" name="place" value="{{ roll.place }}"></div>
  <div class="field"><label>Description</label><textarea name="description">{{ roll.description }}</textarea></div>
  <div class="field"><label>Showcase note</label><textarea name="showcase">{{ roll.showcase }}</textarea></div>
  <div class="field">
    <label>Full album</label>
    <select name="album">
      <option value="">- none -</option>
      {% for a in albums %}<option value="{{ a.slug }}" {{ 'selected' if roll.album == a.slug else '' }}>{{ a.title }} ({{ a.slug }})</option>{% endfor %}
    </select>
  </div>

  {% if roll and roll.images %}
  <div class="field">
    <label>Images (pick cover, check to delete)</label>
    <div class="image-grid">
      {% for img in roll.images %}
      <div class="image-card">
        <img src="{{ cdn }}/rolls/{{ roll.slug }}/thumb/{{ img }}" alt="">
        <label><input type="radio" name="cover" value="{{ img }}" {{ 'checked' if img == roll.image else '' }}> cover</label>
        <label><input type="checkbox" name="delete_images" value="{{ img }}"> delete</label>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <button class="btn btn-solid" type="submit">{{ "Save" if roll else "Create roll, then add images" }}</button>
</form>

{% if roll %}
<div class="admin-head"><h2>Add images</h2></div>
<div class="field">
  <input type="file" id="files" accept="image/*" multiple>
</div>
<p class="flash" id="upStatus"></p>
<script>
document.getElementById("files").addEventListener("change", async function () {
  var files = Array.from(this.files), status = document.getElementById("upStatus");
  for (var i = 0; i < files.length; i++) {
    status.textContent = "uploading " + (i + 1) + " / " + files.length + ": " + files[i].name;
    var fd = new FormData(); fd.append("image", files[i]);
    var r = await fetch("{{ url_for('roll_image', slug=roll.slug) }}", { method: "POST", body: fd });
    if (!r.ok) { status.textContent = "failed on " + files[i].name + ": " + (await r.text()).slice(0, 200); return; }
  }
  status.textContent = "publishing...";
  var r = await fetch("{{ url_for('roll_publish', slug=roll.slug) }}", { method: "POST" });
  if (!r.ok) { status.textContent = "publish failed: " + (await r.text()).slice(0, 200); return; }
  location.reload();
});
</script>

<div class="admin-head"><h2>Delete roll</h2></div>
<form method="post" action="{{ url_for('delete_roll', slug=roll.slug) }}" onsubmit="return confirm('Delete this roll and its images?');">
  <button class="btn btn-line danger" type="submit">Delete roll</button>
</form>
{% endif %}
"""

ALBUM_BODY = """
<div class="admin-head">
  <h1>{{ "Edit album" if album else "Add album" }}</h1>
  <a class="btn btn-line" href="{{ url_for('index') }}">&larr; Back</a>
</div>
{% if error %}<p class="flash">{{ error }}</p>{% endif %}
<form method="post">
  {% if not album %}
  <div class="field"><label>Slug</label><input type="text" name="slug" placeholder="my-event-14-05-2026" required></div>
  {% endif %}
  <div class="field"><label>Date</label><input type="date" name="date" value="{{ album.date }}" required></div>
  <div class="field"><label>Title</label><input type="text" name="title" value="{{ album.title }}" required></div>
  <div class="field"><label>Place</label><input type="text" name="place" value="{{ album.place }}"></div>
  <div class="field"><label>Description</label><textarea name="description">{{ album.description }}</textarea></div>
  <button class="btn btn-solid" type="submit">{{ "Save" if album else "Create album, then upload zip" }}</button>
</form>

{% if album %}
<div class="admin-head"><h2>Photos</h2></div>
<p class="tag-label">
  {% if album.images %}{{ album.images|length }} photos, zip {{ (album.zip_size / 1e6)|round|int }} MB.
  Uploading a new zip replaces all of them.{% else %}No photos yet.{% endif %}
  Link the album to a roll from the roll's edit page.
</p>
<div class="field" style="margin-top: 14px;">
  <label>Zip with .jpg files</label>
  <input type="file" id="zip" accept=".zip,application/zip">
</div>
<progress id="bar" value="0" max="1" hidden></progress>
<p class="flash" id="upStatus"></p>
{% if album.images %}
<div class="thumbs">
  {% for img in album.images %}<img src="{{ cdn }}/albums/{{ album.slug }}/thumb/{{ img }}" alt="" loading="lazy">{% endfor %}
</div>
{% endif %}
<script>
var bar = document.getElementById("bar"), status = document.getElementById("upStatus");

// watching: true once this page started (or saw) a run, so "done" reloads only after a run
function poll(watching) {
  fetch("{{ url_for('album_status', slug=album.slug) }}").then(function (r) { return r.json(); }).then(function (s) {
    if (!s.state) return;
    if (s.state === "error") { status.textContent = "error: " + s.error; return; }
    if (s.state === "done") { if (watching) location.reload(); return; }
    status.textContent = s.state + (s.total ? " " + s.done + " / " + s.total : "");
    if (s.total) { bar.hidden = false; bar.max = s.total; bar.value = s.done; }
    setTimeout(function () { poll(true); }, 1500);
  });
}
poll(false);

document.getElementById("zip").addEventListener("change", async function () {
  var file = this.files[0];
  if (!file) return;
  var r = await fetch("{{ url_for('album_presign', slug=album.slug) }}", { method: "POST" });
  if (!r.ok) { status.textContent = "presign failed: " + (await r.text()).slice(0, 200); return; }
  var up = await r.json();
  var xhr = new XMLHttpRequest();
  xhr.open("PUT", up.url);
  Object.keys(up.headers).forEach(function (h) { xhr.setRequestHeader(h, up.headers[h]); });
  bar.hidden = false;
  xhr.upload.onprogress = function (e) {
    bar.max = e.total; bar.value = e.loaded;
    status.textContent = "uploading zip " + Math.round(e.loaded / 1e6) + " / " + Math.round(e.total / 1e6) + " MB";
  };
  xhr.onerror = function () { status.textContent = "upload failed"; };
  xhr.onload = async function () {
    if (xhr.status !== 200) { status.textContent = "upload failed: " + xhr.status; return; }
    var fd = new FormData(); fd.append("key", up.key);
    var p = await fetch("{{ url_for('album_process', slug=album.slug) }}", { method: "POST", body: fd });
    if (!p.ok) { status.textContent = "processing failed: " + (await p.text()).slice(0, 200); return; }
    poll(true);
  };
  xhr.send(file);
});
</script>

<div class="admin-head"><h2>Delete album</h2></div>
<form method="post" action="{{ url_for('delete_album', slug=album.slug) }}" onsubmit="return confirm('Delete this album, its photos and zip?');">
  <button class="btn btn-line danger" type="submit">Delete album</button>
</form>
{% endif %}
"""

SITE_BODY = """
<div class="admin-head">
  <h1>Site texts</h1>
  <a class="btn btn-line" href="{{ url_for('index') }}">&larr; Back</a>
</div>
{% if error %}<p class="flash">{{ error }}</p>{% endif %}
<form method="post">
  <div class="field"><label>site.json</label><textarea class="code" name="json">{{ text }}</textarea></div>
  <button class="btn btn-solid" type="submit">Save</button>
</form>
"""


def render(body_template: str, **ctx) -> str:
    ctx.setdefault("cdn", load("site.json")["site"]["cdn"])
    body = render_template_string(body_template, **ctx)
    return render_template_string(BASE, body=body)


@app.route("/")
def index():
    return render(INDEX_BODY, rolls=by_date(read("projects.json")["projects"]), albums=by_date(read("albums.json")["albums"]))


# --- rolls --------------------------------------------------------------------

@app.route("/rolls/new", methods=["GET", "POST"])
def new_roll():
    albums = by_date(read("albums.json")["albums"])
    if request.method == "GET":
        return render(ROLL_BODY, roll=None, albums=albums, error=None)

    slug = slugify(request.form.get("slug", ""))
    if not SLUG_RE.match(slug) or any(p["slug"] == slug for p in read("projects.json")["projects"]):
        return render(ROLL_BODY, roll=None, albums=albums, error="Invalid or existing slug.")
    roll = {"slug": slug, **form_fields(ROLL_FIELDS), "image": "", "images": []}
    mutate("projects.json", f"roll {slug}: new", lambda d: d["projects"].append(roll))
    return redirect(url_for("edit_roll", slug=slug))


@app.route("/rolls/<slug>", methods=["GET", "POST"])
def edit_roll(slug: str):
    if request.method == "GET":
        roll = find(read("projects.json")["projects"], slug)
        return render(ROLL_BODY, roll=roll, albums=by_date(read("albums.json")["albums"]), error=None)

    removed = request.form.getlist("delete_images")

    def apply(data):
        roll = find(data["projects"], slug)
        roll.update(form_fields(ROLL_FIELDS))
        roll["images"] = [n for n in roll["images"] if n not in removed]
        cover = request.form.get("cover")
        if cover in roll["images"]:
            roll["images"] = [cover] + [n for n in roll["images"] if n != cover]
        roll["image"] = roll["images"][0] if roll["images"] else ""

    mutate("projects.json", f"roll {slug}: edit", apply)
    for name in removed:
        media.delete_image(f"rolls/{slug}", name)
    return redirect(url_for("edit_roll", slug=slug))


PENDING: dict[str, list[str]] = {}


@app.route("/rolls/<slug>/image", methods=["POST"])
def roll_image(slug: str):
    find(read("projects.json")["projects"], slug)
    file = request.files.get("image")
    if not file or Path(file.filename or "").suffix.lower() not in IMAGE_EXTS:
        return "not an image", 400
    name = media.upload_image(f"rolls/{slug}", file.read(), file.filename)
    PENDING.setdefault(slug, []).append(name)
    return "ok"


@app.route("/rolls/<slug>/publish", methods=["POST"])
def roll_publish(slug: str):
    names = PENDING.pop(slug, [])

    def apply(data):
        roll = find(data["projects"], slug)
        roll["images"] += [n for n in names if n not in roll["images"]]
        roll["image"] = roll["image"] or (roll["images"][0] if roll["images"] else "")

    if names:
        mutate("projects.json", f"roll {slug}: add {len(names)} photos", apply)
    return "ok"


@app.route("/rolls/<slug>/delete", methods=["POST"])
def delete_roll(slug: str):
    mutate("projects.json", f"roll {slug}: delete", lambda d: d.update(projects=[p for p in d["projects"] if p["slug"] != slug]))
    media.delete_prefix(f"rolls/{slug}/")
    return redirect(url_for("index"))


# --- albums -------------------------------------------------------------------

@app.route("/albums/new", methods=["GET", "POST"])
def new_album():
    if request.method == "GET":
        return render(ALBUM_BODY, album=None, error=None)

    slug = slugify(request.form.get("slug", ""))
    if not SLUG_RE.match(slug) or any(a["slug"] == slug for a in read("albums.json")["albums"]):
        return render(ALBUM_BODY, album=None, error="Invalid or existing slug.")
    album = {"slug": slug, **form_fields(ALBUM_FIELDS), "zip": "", "zip_size": 0, "images": []}
    mutate("albums.json", f"album {slug}: new", lambda d: d["albums"].append(album))
    return redirect(url_for("edit_album", slug=slug))


@app.route("/albums/<slug>", methods=["GET", "POST"])
def edit_album(slug: str):
    if request.method == "GET":
        return render(ALBUM_BODY, album=find(read("albums.json")["albums"], slug), error=None)
    mutate("albums.json", f"album {slug}: edit", lambda d: find(d["albums"], slug).update(form_fields(ALBUM_FIELDS)))
    return redirect(url_for("edit_album", slug=slug))


@app.route("/albums/<slug>/presign", methods=["POST"])
def album_presign(slug: str):
    find(read("albums.json")["albums"], slug)
    key = f"albums/{slug}/{slug}-{secrets.token_hex(4)}.zip"
    headers = {
        "Content-Type": "application/zip",
        "Content-Disposition": f'attachment; filename="{slug}.zip"',
        "Cache-Control": media.IMMUTABLE,
    }
    url = media.r2().generate_presigned_url(
        "put_object",
        Params={"Bucket": media.BUCKET, "Key": key, "ContentType": headers["Content-Type"],
                "ContentDisposition": headers["Content-Disposition"], "CacheControl": headers["Cache-Control"]},
        ExpiresIn=6 * 3600,
    )
    return jsonify(url=url, key=key, headers=headers)


@app.route("/albums/<slug>/process", methods=["POST"])
def album_process(slug: str):
    find(read("albums.json")["albums"], slug)
    key = request.form.get("key", "")
    if not key.startswith(f"albums/{slug}/") or not key.endswith(".zip"):
        return "bad key", 400
    if STATUS.get(slug, {}).get("state") not in (None, "done", "error"):
        return "already processing", 409
    STATUS[slug] = {"state": "starting"}
    threading.Thread(target=process_album, args=(slug, key), daemon=True).start()
    return "ok"


@app.route("/albums/<slug>/status")
def album_status(slug: str):
    return jsonify(STATUS.get(slug, {}))


@app.route("/albums/<slug>/delete", methods=["POST"])
def delete_album(slug: str):
    mutate("albums.json", f"album {slug}: delete", lambda d: d.update(albums=[a for a in d["albums"] if a["slug"] != slug]))

    def unlink(data):
        for p in data["projects"]:
            if p.get("album") == slug:
                p["album"] = ""

    mutate("projects.json", f"album {slug}: unlink rolls", unlink)
    media.delete_prefix(f"albums/{slug}/")
    STATUS.pop(slug, None)
    return redirect(url_for("index"))


# --- site texts ---------------------------------------------------------------

@app.route("/site", methods=["GET", "POST"])
def edit_site():
    if request.method == "GET":
        return render(SITE_BODY, text=json.dumps(read("site.json"), ensure_ascii=False, indent=2), error=None)
    text = request.form.get("json", "")
    try:
        new = json.loads(text)
        assert isinstance(new.get("site"), dict) and isinstance(new.get("shared"), dict)
    except (ValueError, AssertionError):
        return render(SITE_BODY, text=text, error="Not valid JSON with 'site' and 'shared'.")

    def apply(data):
        data.clear()
        data.update(new)

    mutate("site.json", f"site texts: edit {datetime.now():%Y-%m-%d}", apply)
    return redirect(url_for("index"))


if __name__ == "__main__":
    # Local testing only: ADMIN_DEV=1 python admin.py
    app.run(host="127.0.0.1", port=8327, debug=False)
