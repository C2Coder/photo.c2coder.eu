from jinja2 import Environment, FileSystemLoader
from livereload import Server
import os
import sys
from datetime import datetime
import json
import shutil
# Jinja setup
env = Environment(loader=FileSystemLoader("templates"))

def write_output(file_path: str, content: str):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

def create_cname(name: str) -> None:
    with open("dist/CNAME", "w", encoding="utf-8") as f:
        f.write(name)

def render():
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    os.makedirs("dist", exist_ok=True)
    cur_year = datetime.now().year
    with open("portfolio/manifest.json", "r", encoding="utf-8") as f:
        projects = json.load(f).get("projects", [])

    create_cname("photo.c2coder.eu")
    if os.path.exists("portfolio"):
        shutil.copytree("portfolio", "dist/portfolio")
    if os.path.exists("static"):
        shutil.copytree("static", "dist/static", dirs_exist_ok=True)

    gallery = []
    for project in projects:
        photos_dir = project["slug"]
        photos_path = os.path.join("portfolio", photos_dir)
        if os.path.exists(photos_path):
            photos = [f for f in os.listdir(photos_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
            photos.sort()
            gallery.append({
                "slug": project["slug"],
                "title": project["title"],
                "photos": [f"/portfolio/{photos_dir}/{photo}" for photo in photos]
            })
        else:
            gallery.append({
                "slug": project["slug"],
                "title": project["title"],
                "photos": []
            })

    write_output("dist/index.html", env.get_template("index.html").render(now = cur_year, projects=projects, gallery=gallery))
    write_output("dist/cz/index.html", env.get_template("index_cz.html").render(now = cur_year, projects=projects, gallery=gallery))


if __name__ == "__main__":
    render()  # first build

    if "--serve" in sys.argv:
        server = Server()
        # watch templates and static files for changes
        server.watch("templates/*.html", render)
        server.watch("static/*", render)
        # serve the "dist" folder with livereload
        server.serve(root="dist", port=5000, host="0.0.0.0")

