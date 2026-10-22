from __future__ import annotations

import json
import sys
import shutil
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
CONTENT = ROOT / "content"
DIST = ROOT / "dist"


def load_json(name: str):
    with open(CONTENT / name, "r", encoding="utf-8") as handle:
        return json.load(handle)


def base_url() -> str:
    return "https://" + (ROOT / "CNAME").read_text().strip()


def ld(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


def write_seo_files(base: str, paths: list[str]) -> None:
    today = date.today().isoformat()
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    urls = "".join(f"  <url><loc>{base}{p}</loc><lastmod>{today}</lastmod></url>\n" for p in paths)
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>\n',
        encoding="utf-8",
    )


def human_size(size: int) -> str:
    if size >= 1e9:
        return f"{size / 1e9:.1f} GB"
    return f"{size / 1e6:.0f} MB" if size >= 1e7 else f"{size / 1e6:.1f} MB"


def write_album(env: Environment, site: dict, album: dict, base: str) -> None:
    cdn = site["cdn"]
    url = f"{base}/albums/{album['slug']}/"
    images = [f"{cdn}/albums/{album['slug']}/{name}" for name in album["images"]]
    description = album.get("description") or f"{len(images)} photos from {album['title']}, {album.get('place', '')} ({album['date']})."
    seo = {
        "title": f"{album['title']} - C2Coder Photo album",
        "description": description,
        "url": url,
        "type": "website",
        "image": images[0] if images else None,
        "card": "summary_large_image",
        "jsonld": ld({
            "@context": "https://schema.org",
            "@type": "ImageGallery",
            "name": album["title"],
            "url": url,
            "dateCreated": album["date"],
            "author": {"@id": base + "/#person"},
            "image": images[:50],
        }),
    }
    out = DIST / "albums" / album["slug"] / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        env.get_template("album.html").render(
            seo=seo, site=site, album=album, nav_prefix="/", zip_size=human_size(album["zip_size"])
        ),
        encoding="utf-8",
    )


def build() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(TEMPLATES))
    env.filters["dmy"] = lambda iso: datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    data = load_json("site.json")
    projects = load_json("projects.json")
    albums = [a for a in load_json("albums.json")["albums"] if a.get("images")]
    year = datetime.now().year

    # Thumbnail sizes keep vertical photos vertical; 4:3 for anything not measured.
    for item in projects["projects"] + albums:
        sizes = item.get("sizes", {})
        item["sizes"] = {n: sizes.get(n, [800, 600]) for n in item["images"]}

    # Rolls without photos yet and links to albums still empty are left out.
    album_slugs = {a["slug"] for a in albums}
    projects["projects"] = [p for p in projects["projects"] if p["images"]]
    for p in projects["projects"]:
        if p.get("album") not in album_slugs:
            p["album"] = ""
    projects["projects"].sort(
        key=lambda p: datetime.strptime(p["date"], "%Y-%m-%d"), reverse=True
    )

    site = dict(data["site"])
    site["shared"] = data["shared"]
    base = base_url()
    contact = site["shared"]["contact"]
    main_site = site["hero"]["secondary"]["href"]
    covers = [
        {
            "@type": "ImageObject",
            "contentUrl": f"{site['cdn']}/rolls/{p['slug']}/{p['image']}",
            "name": p["title"],
            "caption": p["description"],
        }
        for p in projects["projects"]
    ]
    seo = {
        "title": "C2Coder Photo - Event Photography from Czechia",
        "description": "C2Coder photo portfolio: event photography from Trutnov, Brno and across Czechia - maker faires, exhibitions, races and nature. Photos by C2Coder.",
        "url": base + "/",
        "type": "website",
        "image": covers[0]["contentUrl"] if covers else None,
        "card": "summary_large_image",
        "jsonld": ld({
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "WebSite",
                    "@id": base + "/#website",
                    "name": site["title"],
                    "url": base + "/",
                    "inLanguage": "en",
                    "alternateName": ["photo c2coder", "c2coder photo"],
                    "publisher": {"@id": base + "/#person"},
                },
                {
                    "@type": "Person",
                    "@id": base + "/#person",
                    "name": "C2Coder",
                    "jobTitle": "Photographer",
                    "url": main_site,
                    "email": contact["photo"],
                    "sameAs": [contact["instagram"], main_site, "https://link.c2coder.eu", "https://qr.c2coder.eu"],
                },
                {
                    "@type": "ImageGallery",
                    "name": site["title"],
                    "url": base + "/",
                    "author": {"@id": base + "/#person"},
                    "image": covers,
                },
            ],
        }),
    }

    html = env.get_template("index.html").render(now=year, seo=seo, site=site, projects=projects, nav_prefix="")
    (DIST / "index.html").write_text(html, encoding="utf-8")

    for album in albums:
        write_album(env, site, album, base)

    write_seo_files(base, ["/"] + [f"/albums/{a['slug']}/" for a in albums])

    c_name = ROOT / "CNAME"
    if c_name.exists():
        shutil.copy2(c_name, DIST / "CNAME")

    static = ROOT / "static"
    if static.exists():
        shutil.copytree(static, DIST / "static", dirs_exist_ok=True)
        if (static / "favicon.ico").exists():
            shutil.copy2(static / "favicon.ico", DIST / "favicon.ico")


def serve() -> None:
    from livereload import Server

    build()
    server = Server()
    server.watch(str(TEMPLATES / "*.html"), build)
    server.watch(str(CONTENT / "*.json"), build)
    server.watch(str(ROOT / "static" / "**"), build)
    server.serve(root=str(DIST), host="0.0.0.0", port=8001)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    else:
        build()
