"""Local-only management UI for adding/editing portfolio rolls.

Not part of the built static site - never copied into dist/ and never
deployed. Binds to 127.0.0.1 only, so it's reachable exclusively when
you're running it on your own machine (`make admin`).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, redirect, render_template_string, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

import build as sitebuild

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
PORTFOLIO = ROOT / "portfolio"
PROJECTS_FILE = CONTENT / "projects.json"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

app = Flask(__name__, static_folder="static", static_url_path="/static")


def load_projects() -> dict:
    with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_projects(data: dict) -> None:
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    sitebuild.build()


def find_roll(data: dict, slug: str) -> dict | None:
    return next((p for p in data["projects"] if p["slug"] == slug), None)


def roll_images(slug: str) -> list[str]:
    folder = PORTFOLIO / slug
    if not folder.exists():
        return []
    return sorted(f.name for f in folder.iterdir() if f.suffix.lower() in IMAGE_EXTS)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def save_uploads(slug: str, files) -> None:
    folder = PORTFOLIO / slug
    folder.mkdir(parents=True, exist_ok=True)
    for file in files:
        if not file or not file.filename:
            continue
        name = secure_filename(file.filename)
        if Path(name).suffix.lower() not in IMAGE_EXTS:
            continue
        file.save(folder / name)


def apply_cover_order(project: dict, slug: str, cover: str | None) -> None:
    images = roll_images(slug)
    if not images:
        project["image"] = ""
        project["images"] = []
        return
    if not cover or cover not in images:
        cover = images[0]
    ordered = [cover] + [name for name in images if name != cover]
    project["image"] = cover
    project["images"] = ordered


BASE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Roll admin - C2Coder Photo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700;900&family=Roboto+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/css/site.css">
<style>
  :root[data-theme] {}
  .admin-wrap { max-width: 820px; margin: 0 auto; padding: 40px 28px 80px; }
  .admin-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 34px; flex-wrap: wrap; }
  .field { margin-bottom: 18px; }
  .field label {
    display: block; font-family: var(--mono); font-size: .72rem; letter-spacing: .08em; text-transform: uppercase;
    color: var(--ink-faint); margin-bottom: 6px;
  }
  .field input[type=text], .field input[type=date], .field input[type=file], .field textarea {
    width: 100%; font-family: var(--sans); font-size: .95rem; padding: 10px 12px;
    border: 1px solid var(--ink); background: var(--paper); color: var(--ink);
  }
  .field textarea { resize: vertical; min-height: 70px; font-family: var(--sans); }
  .roll-row {
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    padding: 16px 0; border-top: 1px solid var(--line);
  }
  .roll-row:first-child { border-top: none; }
  .roll-row img { width: 72px; height: 54px; object-fit: cover; border: 1px solid var(--line); }
  .roll-row-main { display: flex; align-items: center; gap: 16px; }
  .roll-row-actions { display: flex; gap: 10px; }
  .image-grid { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px; }
  .image-card { border: 1px solid var(--line); padding: 8px; font-family: var(--mono); font-size: .72rem; text-align: center; }
  .image-card img { width: 110px; height: 80px; object-fit: cover; margin-bottom: 6px; border: 1px solid var(--line); }
  .image-card label { display: flex; align-items: center; gap: 6px; justify-content: center; margin-top: 4px; color: var(--ink-soft); text-transform: none; letter-spacing: 0; }
  .flash { font-family: var(--mono); font-size: .8rem; color: var(--accent); margin-bottom: 20px; }
  .danger { border-color: var(--accent); color: var(--accent); }
  .danger:hover { background: var(--accent); color: var(--accent-contrast); }
</style>
</head>
<body>
  <header class="masthead">
    <div class="wrap masthead-row">
      <a href="{{ url_for('index') }}" class="wordmark">Roll admin<span class="wordmark-dot">.</span></a>
      <div class="masthead-controls">
        <span class="tag-label">localhost only</span>
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
<div class="admin-head">
  <h1>Rolls</h1>
  <a class="btn btn-solid" href="{{ url_for('new_roll') }}">+ Add roll</a>
</div>
{% if not projects %}
<p class="tag-label">No rolls yet.</p>
{% endif %}
{% for p in projects %}
<div class="roll-row">
  <div class="roll-row-main">
    {% if p.image %}<img src="/portfolio/{{ p.slug }}/{{ p.image }}" alt="">{% endif %}
    <div>
      <strong>{{ p.title }}</strong><br>
      <span class="tag-label">{{ p.slug }} · {{ p.date }}</span>
    </div>
  </div>
  <div class="roll-row-actions">
    <a class="btn btn-line" href="{{ url_for('edit_roll', slug=p.slug) }}">Edit</a>
    <form method="post" action="{{ url_for('delete_roll', slug=p.slug) }}" onsubmit="return confirm('Delete this roll and its images?');">
      <button class="btn btn-line danger" type="submit">Delete</button>
    </form>
  </div>
</div>
{% endfor %}
"""

FORM_BODY = """
<div class="admin-head">
  <h1>{{ "Edit roll" if editing else "Add roll" }}</h1>
  <a class="btn btn-line" href="{{ url_for('index') }}">&larr; Back</a>
</div>
{% if error %}<p class="flash">{{ error }}</p>{% endif %}
<form method="post" enctype="multipart/form-data">
  <div class="field">
    <label>Slug</label>
    <input type="text" name="slug" value="{{ project.slug if project else '' }}" {{ 'readonly' if editing else '' }} placeholder="my-event-2026" required>
  </div>
  <div class="field">
    <label>Date</label>
    <input type="date" name="date" value="{{ project.date if project else '' }}" required>
  </div>
  <div class="field">
    <label>Title</label>
    <input type="text" name="title" value="{{ project.title if project else '' }}" required>
  </div>
  <div class="field">
    <label>Place</label>
    <input type="text" name="place" value="{{ project.place if project else '' }}">
  </div>
  <div class="field">
    <label>Description</label>
    <textarea name="description">{{ project.description if project else '' }}</textarea>
  </div>
  <div class="field">
    <label>Showcase note</label>
    <textarea name="showcase">{{ project.showcase if project else '' }}</textarea>
  </div>

  {% if editing and images %}
  <div class="field">
    <label>Existing images (pick cover, check to delete)</label>
    <div class="image-grid">
      {% for img in images %}
      <div class="image-card">
        <img src="/portfolio/{{ project.slug }}/{{ img }}" alt="">
        <div>{{ img }}</div>
        <label><input type="radio" name="cover" value="{{ img }}" {{ 'checked' if img == project.image else '' }}> cover</label>
        <label><input type="checkbox" name="delete_images" value="{{ img }}"> delete</label>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <div class="field">
    <label>{{ "Add images" if editing else "Images" }}</label>
    <input type="file" name="images" accept="image/*" multiple {{ 'required' if not editing else '' }}>
  </div>

  <button class="btn btn-solid" type="submit">{{ "Save changes" if editing else "Create roll" }}</button>
</form>
"""


def render(body_template: str, **ctx) -> str:
    body = render_template_string(body_template, **ctx)
    return render_template_string(BASE, body=body)


@app.route("/portfolio/<slug>/<path:filename>")
def portfolio_image(slug: str, filename: str):
    return send_from_directory(PORTFOLIO / slug, filename)


@app.route("/")
def index():
    data = load_projects()
    projects = sorted(
        data["projects"],
        key=lambda p: datetime.strptime(p["date"], "%Y-%m-%d"),
        reverse=True,
    )
    return render(INDEX_BODY, projects=projects)


@app.route("/new", methods=["GET", "POST"])
def new_roll():
    if request.method == "GET":
        return render(FORM_BODY, editing=False, project=None, images=[], error=None)

    data = load_projects()
    slug = slugify(request.form.get("slug", ""))
    if not slug or not SLUG_RE.match(slug):
        return render(FORM_BODY, editing=False, project=None, images=[], error="Invalid slug.")
    if find_roll(data, slug) is not None:
        return render(FORM_BODY, editing=False, project=None, images=[], error="A roll with this slug already exists.")

    files = request.files.getlist("images")
    if not any(f and f.filename for f in files):
        return render(FORM_BODY, editing=False, project=None, images=[], error="At least one image is required.")

    save_uploads(slug, files)

    project = {
        "slug": slug,
        "title": request.form.get("title", ""),
        "description": request.form.get("description", ""),
        "date": request.form.get("date", ""),
        "place": request.form.get("place", ""),
        "showcase": request.form.get("showcase", ""),
        "image": "",
        "images": [],
    }
    apply_cover_order(project, slug, None)

    data["projects"].append(project)
    save_projects(data)
    return redirect(url_for("index"))


@app.route("/edit/<slug>", methods=["GET", "POST"])
def edit_roll(slug: str):
    data = load_projects()
    project = find_roll(data, slug)
    if project is None:
        abort(404)

    if request.method == "GET":
        return render(FORM_BODY, editing=True, project=project, images=roll_images(slug), error=None)

    for key in ("title", "description", "place", "showcase", "date"):
        project[key] = request.form.get(key, "")

    for name in request.form.getlist("delete_images"):
        target = PORTFOLIO / slug / secure_filename(name)
        if target.exists():
            target.unlink()

    save_uploads(slug, request.files.getlist("images"))

    cover = request.form.get("cover")
    apply_cover_order(project, slug, cover)

    save_projects(data)
    return redirect(url_for("index"))


@app.route("/delete/<slug>", methods=["POST"])
def delete_roll(slug: str):
    data = load_projects()
    project = find_roll(data, slug)
    if project is None:
        abort(404)

    data["projects"] = [p for p in data["projects"] if p["slug"] != slug]
    save_projects(data)

    folder = PORTFOLIO / slug
    if folder.exists():
        for f in folder.iterdir():
            f.unlink()
        folder.rmdir()

    return redirect(url_for("index"))


if __name__ == "__main__":
    # 127.0.0.1 only - never exposed beyond this machine.
    # debug=False: the Werkzeug interactive debugger is an RCE risk the moment
    # this port is ever forwarded/tunneled, even accidentally.
    app.run(host="127.0.0.1", port=8002, debug=False)
