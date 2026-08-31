#!/usr/bin/env python3
"""Icons, off Iconify and into a drawing.

    python3 icons.py search database          # names you can use
    python3 icons.py get mdi:database lucide:server --out icons/
    python3 icons.py get mdi:database --markup   # the <svg> itself, on stdout

An `icon` node's `href` is raw SVG markup, so the usual flow is:

    python3 icons.py get mdi:database --out icons/
    "db": { "type": "icon", "href": "icons/mdi-database.svg", "text": "Postgres" }

`build.py` inlines the file — and understands `"href": "iconify:mdi:database"`
directly, if you would rather not keep the file. Either way the built page has
the markup in it and needs no network.

Iconify has ~200k icons in ~150 sets, each set under its own licence (mostly
Apache/MIT/CC-BY); `search` prints the set with every hit. Icons drawn in
`currentColor` — most of them — take the node's `style.textColor`, so one icon
recolours per shape without another download.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

API = "https://api.iconify.design"
TIMEOUT = 20
CACHE = Path(tempfile.gettempdir()) / "deepdraw-cache" / "icons"

# The library rebuilds an icon from this list before it draws it (`sanitize.ts`)
# and shows an empty frame for markup that does not survive — so a file checked
# here is a file that will not turn into a hole in the drawing.
ALLOWED_ELEMENTS = {
    "svg", "g", "defs", "symbol", "use", "title", "desc",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "clipPath", "mask", "pattern",
    "linearGradient", "radialGradient", "stop",
}

ALLOWED_ATTRIBUTES = {
    "viewBox", "width", "height", "preserveAspectRatio", "transform", "id", "class",
    "d", "points", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "dx", "dy", "offset", "rotate",
    "fill", "fill-opacity", "fill-rule", "clip-rule", "opacity", "color",
    "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray",
    "stroke-dashoffset", "stroke-miterlimit", "stroke-opacity",
    "stop-color", "stop-opacity", "gradientUnits", "gradientTransform", "spreadMethod",
    "clipPathUnits", "maskUnits", "maskContentUnits", "patternUnits", "patternContentUnits",
    "clip-path", "mask", "font-family", "font-size", "font-style", "font-weight",
    "letter-spacing", "text-anchor", "dominant-baseline", "vector-effect", "paint-order",
    "href",
}

LOCAL_REFERENCE = re.compile(r"^#[\w.:-]+$")
LOCAL_URL_FUNCTION = re.compile(r"^url\(\s*['\"]?#[\w.:-]+['\"]?\s*\)$", re.I)


class IconError(Exception):
    """An icon that cannot be had, said in one sentence a person can act on."""


def _get(url: str, missing: str | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "deepdraw-skill"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        # A name nobody has is the common failure, and "HTTP Error 404" is not
        # what somebody who mistyped an icon name needs to read.
        raise IconError(missing if error.code == 404 and missing else f"{url}: {error}") from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise IconError(f"{url}: {error}") from error


def search(query: str, limit: int = 24, api: str = API) -> list[str]:
    """Icon names — `prefix:name` — for a word, best first."""
    url = f"{api}/search?query={urllib.parse.quote(query)}&limit={limit}"
    try:
        data = json.loads(_get(url))
    except json.JSONDecodeError as error:
        raise IconError(f"unreadable answer from {api} ({error})") from error
    return [name for name in data.get("icons", []) if isinstance(name, str)]


def fetch(name: str, api: str = API) -> str:
    """One icon's SVG markup. `name` is `prefix:icon`, as search prints it.

    Cached in the temp dir, so a document referring to `iconify:mdi:database`
    goes to the network once and every rebuild after that is offline.
    """
    prefix, _, icon = name.partition(":")
    if not prefix or not icon:
        raise IconError(f"'{name}' is not a prefix:name — try `search`")
    cached = CACHE / filename(name)
    if cached.is_file():
        return cached.read_text(encoding="utf-8")

    markup = _get(
        f"{api}/{urllib.parse.quote(prefix)}/{urllib.parse.quote(icon)}.svg",
        missing=f"no icon called {name} — `icons.py search {icon.split('-')[0]}` lists what there is",
    )
    text = markup.decode("utf-8", "replace").strip()
    # A miss answers 404 through urlopen, but a set that exists and an icon in
    # it that does not answers 200 with a plain-text apology.
    if not text.startswith("<svg"):
        raise IconError(f"no icon called {name} — try `search`")

    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8", newline="\n")
    return text


def check(markup: str) -> list[str]:
    """What the library's sanitizer would throw away. Empty means it draws."""
    text = markup.strip()
    if not text.startswith("<"):
        return ["not markup at all — an icon's href is the <svg> itself"]
    try:
        root = ET.fromstring(re.sub(r"<\?xml[^>]*\?>|<!--.*?-->", "", text, flags=re.S))
    except ET.ParseError as error:
        return [f"not well-formed XML ({error}) — the library refuses it whole"]

    local = lambda tag: tag.rsplit("}", 1)[-1]  # noqa: E731 — {ns}name -> name
    if local(root.tag) != "svg":
        return [f"the root element is <{local(root.tag)}>, not <svg>"]

    problems: list[str] = []
    for element in root.iter():
        tag = local(element.tag)
        if tag not in ALLOWED_ELEMENTS:
            problems.append(f"<{tag}> is dropped" + (" (it fetches)" if tag == "image" else ""))
            continue
        for attribute, value in element.attrib.items():
            name = local(attribute)
            if name.startswith("xmlns"):
                continue
            if name not in ALLOWED_ATTRIBUTES:
                problems.append(f"{tag}[{name}] is dropped")
            elif name == "href" and not LOCAL_REFERENCE.match(value.strip()):
                problems.append(f"{tag}[href] leaves the file: {value[:40]}")
            elif "url(" in value.lower() and not LOCAL_URL_FUNCTION.match(value.strip()):
                problems.append(f"{tag}[{name}] points outside the file: {value[:40]}")
    # The same missing attribute repeated forty times is one thing to fix.
    return sorted(set(problems))


def filename(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + ".svg"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--api", default=API, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    finder = sub.add_parser("search", help="icon names for a word")
    finder.add_argument("query")
    finder.add_argument("--limit", type=int, default=24)

    getter = sub.add_parser("get", help="write icons as .svg files")
    getter.add_argument("names", nargs="+", metavar="prefix:name")
    getter.add_argument("--out", type=Path, default=Path("icons"), help="directory; default: ./icons")
    getter.add_argument("--markup", action="store_true", help="print the markup instead")

    args = parser.parse_args()

    try:
        if args.command == "search":
            names = search(args.query, args.limit, args.api)
            if not names:
                print(f"nothing for '{args.query}'", file=sys.stderr)
            # Grouped by set, because picking one set for the whole drawing is
            # what makes a row of icons look drawn by one hand.
            by_set: dict[str, list[str]] = {}
            for name in names:
                by_set.setdefault(name.split(":")[0], []).append(name)
            for prefix, hits in by_set.items():
                print(f"{prefix:<16} {' '.join(name.split(':', 1)[1] for name in hits)}")
            return

        for name in args.names:
            markup = fetch(name, args.api)
            for problem in check(markup):
                print(f"warning: {name}: {problem}", file=sys.stderr)
            if args.markup:
                print(markup)
                continue
            args.out.mkdir(parents=True, exist_ok=True)
            path = args.out / filename(name)
            path.write_text(markup, encoding="utf-8", newline="\n")
            print(path)
    except IconError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
