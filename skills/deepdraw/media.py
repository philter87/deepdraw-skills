#!/usr/bin/env python3
"""Pictures, made small enough to live inside the page.

    python3 media.py photo.jpg                  # -> photo.dd.webp beside it
    python3 media.py https://…/chart.png pics/  # fetched, shrunk, written there
    python3 media.py photo.jpg --data-uri       # the href itself, on stdout

You rarely need this: `build.py` inlines whatever an image node's `href` points
at — a path beside the document or an `https://` URL — and shrinks it on the
way in. Write the path in the JSON and never look at base64. Reach for this
script to see what a picture costs before you use it, or to keep a fetched copy
so the build stops going to the network.

The budget is the point. A drawing is one HTML file somebody opens from a disk,
and a phone screenshot pasted in whole is 4 MB of base64 in a file that is
otherwise 250 KB. Every picture is scaled to fit MAX_EDGE and re-encoded to
land under MAX_BYTES, which is invisible at the size a shape actually draws.

Pillow does the scaling. Without it a picture still goes in, at its original
size, with a warning when that is heavy.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Longest edge, in pixels. A shape holding a picture is a couple of hundred
# points across; this is that on a retina screen with room to zoom in.
MAX_EDGE = 900
# What one picture may weigh once encoded, before quality is stepped down.
MAX_BYTES = 250_000
# A fetch that has not finished by here is a fetch that is not going to.
FETCH_TIMEOUT = 20
# The ceiling on what will even be read off the network, matching the web app.
FETCH_LIMIT = 10 * 1024 * 1024

CACHE = Path(tempfile.gettempdir()) / "deepdraw-cache"

MIME_BY_SIGNATURE = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)

EXTENSION = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}


class MediaError(Exception):
    """A picture that cannot be used, said in one sentence a person can act on."""


# --- getting the bytes -------------------------------------------------------


def fetch(url: str) -> bytes:
    """A remote picture, cached in the temp dir so a rebuild stays offline."""
    cached = CACHE / "images" / hashlib.sha256(url.encode()).hexdigest()[:32]
    if cached.is_file():
        return cached.read_bytes()

    # A default urllib User-Agent is refused by enough hosts to be worth naming
    # ourselves instead; Wikipedia in particular answers it with a 403.
    request = urllib.request.Request(url, headers={"User-Agent": "deepdraw-skill"})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
            # Read against a ceiling rather than into memory: a URL that streams
            # forever should be a refusal, not a hung build.
            data = response.read(FETCH_LIMIT + 1)
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise MediaError(f"could not fetch {url}: {error}") from error
    if len(data) > FETCH_LIMIT:
        raise MediaError(f"{url} is over {FETCH_LIMIT // 1024 // 1024} MB")

    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data


def read(src: str, base: Path) -> bytes:
    """The bytes behind a path, a URL or a `data:` URI. `base` is the document."""
    if src.startswith(("http://", "https://")):
        return fetch(src)
    if src.startswith("data:"):
        head, _, payload = src.partition(",")
        if not payload:
            raise MediaError("a data: URI with nothing after the comma")
        if ";base64" not in head:
            return urllib.parse.unquote_to_bytes(payload)
        try:
            return base64.b64decode(payload, validate=False)
        except binascii.Error as error:
            raise MediaError(f"undecodable data: URI ({error})") from error
    if src.startswith(("file://", "//")) or re.match(r"^[a-zA-Z][\w+.-]*:", src):
        raise MediaError(f"only a path, https:// or data: — not {src.split(':')[0]}:")
    path = Path(src)
    path = path if path.is_absolute() else base / path
    if not path.is_file():
        raise MediaError(f"no such image: {path}")
    return path.read_bytes()


def sniff(data: bytes) -> str:
    """What the bytes actually are. The extension and the server both lie."""
    for signature, mime in MIME_BY_SIGNATURE:
        if data.startswith(signature):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:400].lstrip()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:2000]):
        return "image/svg+xml"
    raise MediaError("not a picture in any format a browser draws")


# --- making them small -------------------------------------------------------


def _pillow():
    try:
        from PIL import Image, ImageOps, features  # noqa: PLC0415
    except ImportError:
        return None
    return Image, ImageOps, features


def optimize(
    data: bytes,
    max_edge: int = MAX_EDGE,
    max_bytes: int = MAX_BYTES,
) -> tuple[bytes, str, tuple[int, int] | None, list[str]]:
    """Scaled to fit and re-encoded under the budget.

    Returns the bytes, their mime type, the pixel size and anything worth
    saying out loud. The original is kept whenever it is already smaller than
    what re-encoding would produce — a 3 KB logo does not need a WebP of it.
    """
    mime = sniff(data)
    notes: list[str] = []
    if mime == "image/svg+xml":
        raise MediaError("an SVG belongs in an icon node — see icons.py")

    loaded = _pillow()
    if loaded is None:
        if len(data) > max_bytes:
            notes.append(
                f"{len(data) // 1024} KB and not shrunk — `pip install Pillow` to scale it"
            )
        return data, mime, None, notes
    Image, ImageOps, features = loaded

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as error:  # Pillow raises a zoo of these
        raise MediaError(f"unreadable image ({error})") from error

    # An animated GIF is the one picture worth leaving alone: every path below
    # keeps the first frame and silently throws the animation away.
    if getattr(image, "n_frames", 1) > 1:
        if len(data) > max_bytes:
            notes.append(f"animated, {len(data) // 1024} KB, kept whole")
        return data, mime, image.size, notes

    image = ImageOps.exif_transpose(image)
    original = image.size
    has_alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
    image = image.convert("RGBA" if has_alpha else "RGB")

    webp = features.check("webp")
    # PNG is the only encoder here with no quality knob to turn, so trying the
    # same frame three times would encode the same bytes three times.
    qualities = (82,) if (not webp and has_alpha) else (82, 72, 62)

    def encode(frame, quality: int) -> tuple[bytes, str]:
        if webp:
            return _encode(frame, "WEBP", quality=quality, method=6)
        if has_alpha:
            return _encode(frame, "PNG", optimize=True)
        return _encode(frame, "JPEG", quality=quality, optimize=True, progressive=True)

    # Never upscale, and never encode the same frame twice: a 400px picture
    # under a 900px ceiling has one row, not three.
    edges: list[int] = []
    for edge in (max_edge, round(max_edge * 0.75), round(max_edge * 0.55)):
        edge = min(edge, max(image.size))
        if edge not in edges:
            edges.append(edge)

    best: tuple[bytes, str, tuple[int, int]] | None = None
    # Quality first, then size: a picture is better slightly softer than
    # slightly smaller, and only a very heavy one gets to the second row.
    for edge in edges:
        frame = image
        if max(frame.size) > edge:
            frame = frame.copy()
            frame.thumbnail((edge, edge), Image.LANCZOS)
        for quality in qualities:
            encoded, mime_out = encode(frame, quality)
            if best is None or len(encoded) < len(best[0]):
                best = (encoded, mime_out, frame.size)
            if len(encoded) <= max_bytes:
                return _keep_smaller(data, mime, original, best, notes)

    assert best is not None
    if len(best[0]) > max_bytes:
        notes.append(f"still {len(best[0]) // 1024} KB at {best[2][0]}×{best[2][1]}")
    return _keep_smaller(data, mime, original, best, notes)


def _keep_smaller(
    data: bytes,
    mime: str,
    original: tuple[int, int],
    best: tuple[bytes, str, tuple[int, int]],
    notes: list[str],
) -> tuple[bytes, str, tuple[int, int], list[str]]:
    """The original when it is already the smaller of the two.

    Only when nothing had to be scaled — at the same pixel size, a hand-tuned
    PNG or an already-optimized JPEG routinely beats an automatic re-encode,
    and re-encoding it would cost quality to gain bytes.
    """
    encoded, mime_out, size = best
    if size == original and len(data) <= len(encoded):
        return data, mime, original, notes
    return encoded, mime_out, size, notes


def _encode(image, fmt: str, **options) -> tuple[bytes, str]:
    buffer = io.BytesIO()
    image.save(buffer, fmt, **options)
    return buffer.getvalue(), f"image/{fmt.lower()}"


def data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def resolve(
    src: str,
    base: Path,
    max_edge: int = MAX_EDGE,
    max_bytes: int = MAX_BYTES,
) -> tuple[str, tuple[int, int] | None, list[str]]:
    """A path, URL or data: URI as one optimized `data:` URI. What build.py calls."""
    data, mime, size, notes = optimize(read(src, base), max_edge, max_bytes)
    return data_uri(data, mime), size, notes


# --- command line ------------------------------------------------------------


def human(count: int) -> str:
    return f"{count / 1024:.0f} KB" if count >= 1024 else f"{count} B"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("src", help="an image file, or an http(s) URL")
    parser.add_argument("out", nargs="?", help="file or directory; default: beside src")
    parser.add_argument("--max-edge", type=int, default=MAX_EDGE, metavar="PX")
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES, metavar="N")
    parser.add_argument("--data-uri", action="store_true", help="print the href instead of writing a file")
    args = parser.parse_args()

    try:
        raw = read(args.src, Path.cwd())
        data, mime, size, notes = optimize(raw, args.max_edge, args.max_bytes)
    except MediaError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)

    if args.data_uri:
        print(data_uri(data, mime))
    else:
        stem = Path(args.src.split("?")[0].split("#")[0]).stem or "image"
        # "pics/" and "pics" both mean a directory; only a name with a suffix
        # on it — `small.webp` — is meant as the file itself.
        # No destination means beside the picture, which for a URL is here.
        source_dir = Path(args.src).parent if not args.src.startswith("http") else Path.cwd()
        target = args.out or str(source_dir)
        out = Path(target)
        if target.endswith(("/", os.sep)) or out.is_dir() or not out.suffix:
            out = out / f"{stem}.dd{EXTENSION.get(mime, '.bin')}"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(out)

    where = f", {size[0]}×{size[1]}" if size else ""
    print(f"{human(len(data))}{where}, from {human(len(raw))}", file=sys.stderr)
    for note in notes:
        print(f"warning: {note}", file=sys.stderr)


if __name__ == "__main__":
    main()
