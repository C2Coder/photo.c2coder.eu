"""Image processing and R2 storage, shared by the admin and the migration.

Every image ends up as two objects on R2 under the same name:
    <prefix>/<stem>-<hash>.jpg        web size (original bytes if already small enough)
    <prefix>/thumb/<stem>-<hash>.jpg  thumbnail
The content hash in the name means the CDN never serves a stale copy.
"""

from __future__ import annotations

import functools
import hashlib
import io
import os
import re
from pathlib import PurePath

from PIL import Image, ImageOps

WEB_MAX = 2048
THUMB_WIDTH = 800
IMMUTABLE = "public, max-age=31536000, immutable"


BUCKET = os.environ.get("R2_BUCKET", "photo")


@functools.cache
def r2():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def put(key: str, data: bytes, content_type: str = "image/jpeg") -> None:
    r2().put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=content_type, CacheControl=IMMUTABLE)


def list_keys(prefix: str) -> list[str]:
    keys = []
    for page in r2().get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
        keys += [obj["Key"] for obj in page.get("Contents", [])]
    return keys


def delete_keys(keys: list[str]) -> None:
    for i in range(0, len(keys), 1000):
        chunk = [{"Key": k} for k in keys[i:i + 1000]]
        r2().delete_objects(Bucket=BUCKET, Delete={"Objects": chunk})


def delete_prefix(prefix: str) -> None:
    delete_keys(list_keys(prefix))


def natural_key(name: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def _jpeg(img: Image.Image, quality: int) -> bytes:
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def process(data: bytes, filename: str) -> tuple[str, bytes, bytes, list[int]]:
    """Return (name, web bytes, thumb bytes, thumb [w, h]). Always makes a thumbnail,
    only re-encodes the web copy when it is too big, rotated by EXIF or not a JPEG."""
    stem = re.sub(r"[^a-z0-9]+", "-", PurePath(filename).stem.lower()).strip("-") or "img"
    name = f"{stem}-{hashlib.sha256(data).hexdigest()[:8]}.jpg"

    with Image.open(io.BytesIO(data)) as raw:
        is_jpeg = raw.format == "JPEG"
        rotated = raw.getexif().get(0x0112, 1) != 1
        img = ImageOps.exif_transpose(raw)
        if is_jpeg and not rotated and max(img.size) <= WEB_MAX:
            web = data
        else:
            big = img.copy()
            big.thumbnail((WEB_MAX, WEB_MAX), Image.LANCZOS)
            web = _jpeg(big, 85)
        img.thumbnail((THUMB_WIDTH, THUMB_WIDTH * 2), Image.LANCZOS)
        thumb = _jpeg(img, 80)
        size = list(img.size)
    return name, web, thumb, size


def upload_image(prefix: str, data: bytes, filename: str) -> tuple[str, list[int]]:
    """Upload web + thumb, return (name, thumb [w, h]) - the size lets pages lay out
    vertical and horizontal photos before they load."""
    name, web, thumb, size = process(data, filename)
    put(f"{prefix}/{name}", web)
    put(f"{prefix}/thumb/{name}", thumb)
    return name, size


def delete_image(prefix: str, name: str) -> None:
    delete_keys([f"{prefix}/{name}", f"{prefix}/thumb/{name}"])
