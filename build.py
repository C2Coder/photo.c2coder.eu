from __future__ import annotations

import json
import sys
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
CONTENT = ROOT / "content"
DIST = ROOT / "dist"


def load_json(name: str):
    with open(CONTENT / name, "r", encoding="utf-8") as handle:
        return json.load(handle)


def build() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(TEMPLATES))
    data = load_json("site.json")
    projects = load_json("projects.json")
    year = datetime.now().year

    projects["projects"].sort(
        key=lambda p: datetime.strptime(p["date"], "%Y-%m-%d"), reverse=True
    )

    site = dict(data["site"])
    site["shared"] = data["shared"]
    html = env.get_template("index.html").render(now=year, site=site, projects=projects)
    (DIST / "index.html").write_text(html, encoding="utf-8")

    c_name = ROOT / "CNAME"
    if c_name.exists():
        shutil.copy2(c_name, DIST / "CNAME")

    portfolio = ROOT / "portfolio"
    if portfolio.exists():
        shutil.copytree(portfolio, DIST / "portfolio", dirs_exist_ok=True)

    static = ROOT / "static"
    if static.exists():
        shutil.copytree(static, DIST / "static", dirs_exist_ok=True)


def serve() -> None:
    from livereload import Server

    build()
    server = Server()
    server.watch(str(TEMPLATES / "*.html"), build)
    server.watch(str(CONTENT / "*.json"), build)
    server.watch(str(ROOT / "portfolio" / "**"), build)
    server.watch(str(ROOT / "static" / "**"), build)
    server.serve(root=str(DIST), host="0.0.0.0", port=8001)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    else:
        build()
