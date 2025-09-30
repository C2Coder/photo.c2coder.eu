from jinja2 import Environment, FileSystemLoader
from livereload import Server
import os
import sys
from datetime import datetime

# Jinja setup
env = Environment(loader=FileSystemLoader("templates"))

def write_output(file_path: str, content: str):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

def render():
    os.makedirs("dist", exist_ok=True)
    cur_year = datetime.now().year
    write_output("dist/index.html", env.get_template("index.html").render(now = cur_year))
    write_output("dist/cz/index.html", env.get_template("index_cz.html").render(now = cur_year))


if __name__ == "__main__":
    render()  # first build

    if "--serve" in sys.argv:
        server = Server()
        # watch templates and static files for changes
        server.watch("templates/*.html", render)
        server.watch("static/*", render)
        # serve the "dist" folder with livereload
        server.serve(root="dist", port=5000, host="0.0.0.0")

