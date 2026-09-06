#!/usr/bin/env python3
"""Fill a deepdraw document into the vendored standalone page.

    python3 build.py drawing.json [out.html] [--title "Tab title"]
                     [--read-only] [--strict]
                     [--credit "Name|https://url"] [--no-credit]

The template carries the whole minified library inline, so the output is one
self-contained file that opens from a disk with no network. Only three marks in
it are replaced: the <title>, the JSON payload, and the credit fragment.

Three things happen to the document on the way in:

- **It is checked** against the format (`reference/spec.md`) — every mistake
  that renders as silence rather than as an error. A dangling id, a misspelt
  type, a style property nobody reads: the page would open and simply not be
  the drawing that was meant. Fatal ones refuse the build; the rest are
  warnings, which `--strict` promotes.
- **Its pictures are inlined.** An `image` href may be a path beside the JSON
  or an `https://` URL; it is fetched, scaled and re-encoded into a `data:`
  URI (`media.py`). An `icon` href may be a `.svg` file or `iconify:mdi:home`,
  and is inlined as markup (`icons.py`). So the document stays small and
  readable and the page stays offline.
- **It opens editable**, unless `--read-only`. A drawing somebody cannot move a
  box in is a picture, and if that is what was wanted it is worth saying.

The page signs itself bottom right — "Created with deepdraw.app", and beside it
this skill, because a reader who wants another drawing like this one wants the
tool that made it rather than this copy of it.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import icons
import media

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "reference" / "template.html"
STAMP = HERE / "reference" / ".deepdraw-version"

# The library states these itself (`TEMPLATE_MARKS`), and refuses to publish a
# template where any of them appears more than once — so each is filled exactly
# once and the copies inside the inlined bundle are spelled so as not to match.
MARKS = {
    "title": "__DEEPDRAW_TITLE__",
    "document": "__DEEPDRAW_DOCUMENT_JSON__",
    "credit": "__DEEPDRAW_CREDIT__",
}

# Name and URL of whatever generated the file, as `Name|https://url`.
SKILL_CREDIT = "deepdraw-skills|https://github.com/philter87/deepdraw-skills"

TYPES = {
    "root", "rect", "square", "ellipse", "diamond", "fatArrow", "container",
    "sticky", "text", "image", "icon", "arrow", "draw", "group",
}

NODE_FIELDS = {
    "id", "kind", "type", "parentId", "index", "x", "y", "w", "h", "rotation",
    "text", "markdown", "style", "from", "to", "href", "points", "groupId",
    "targetId",
}

NUMBERS = ("index", "x", "y", "w", "h", "rotation")
STRINGS = ("text", "markdown", "href", "groupId")

STYLE_NUMBERS = ("strokeWidth", "radius", "fontSize", "opacity", "sloppiness")
STYLE_STRINGS = ("fill", "stroke", "textColor", "fontFamily")
STYLE_ENUMS = {
    "strokeStyle": {"solid", "dashed", "dotted"},
    "hAlign": {"left", "center", "right"},
    "vAlign": {"above", "top", "middle", "bottom", "below"},
    "arrowStart": {"none", "triangle", "open", "dot"},
    "arrowEnd": {"none", "triangle", "open", "dot"},
}
STYLE_FIELDS = set(STYLE_NUMBERS) | set(STYLE_STRINGS) | set(STYLE_ENUMS)

ENDPOINT_FIELDS = {"nodeId", "side", "anchor", "x", "y"}
SIDES = {"top", "right", "bottom", "left"}

# The image box a picture is fitted into when the document gives no size, the
# same one the toolbar would have drawn.
DEFAULT_IMAGE = (160, 120)
# A drawing is framed by at least this much, so a level laid out smaller than
# it opens further in than whoever wrote it meant.
MIN_CANVAS = 300


def die(message: str) -> "NoReturn":  # noqa: F821
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


# --- checking ----------------------------------------------------------------


class Report:
    """What is wrong with the document, in two piles."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    """The object, refusing a key written twice.

    `json` keeps the last of two identical keys without a word, so a document
    with `"api"` defined twice silently loses one shape — and the shape it
    loses is the one you can see in the file.
    """
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def is_number(value: object) -> bool:
    """A number, and not a `true` — which Python would otherwise count as 1."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def endpoint_target(value: object) -> str | None:
    """The node an endpoint names. `"from": "api"` is shorthand for `{nodeId}`."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        target = value.get("nodeId")
        return target if isinstance(target, str) else None
    return None


def check_endpoint(report: Report, node_id: str, end: str, value: object) -> None:
    where = f"{node_id}.{end}"
    if isinstance(value, str):
        return  # the shorthand, understood by the reader
    if not isinstance(value, dict):
        report.error(f"{where} is neither a node id nor an endpoint object")
        return
    for key in set(value) - ENDPOINT_FIELDS:
        report.warn(f"{where}.{key} is not an endpoint field ({', '.join(sorted(ENDPOINT_FIELDS))})")
    if "nodeId" in value and not isinstance(value["nodeId"], str):
        report.error(f"{where}.nodeId is not a string")
    side = value.get("side")
    if side is not None and side not in SIDES:
        report.error(f"{where}.side is {side!r}, not one of {', '.join(sorted(SIDES))}")
    anchor = value.get("anchor")
    if anchor is not None:
        if not isinstance(anchor, dict) or not all(
            is_number(anchor.get(axis)) for axis in "xy"
        ):
            report.error(f"{where}.anchor is not {{x, y}}")
        elif not all(0 <= anchor[axis] <= 1 for axis in "xy"):
            report.warn(f"{where}.anchor is a fraction of the box, 0..1 — not a coordinate")
    if "nodeId" not in value and not all(is_number(value.get(axis)) for axis in "xy"):
        report.error(f"{where} pins to nothing: give it a nodeId, or an x and a y")


def check_style(report: Report, node_id: str, style: object) -> None:
    if not isinstance(style, dict):
        report.error(f"{node_id}.style is not an object")
        return
    for key, value in style.items():
        if key not in STYLE_FIELDS:
            report.warn(f"{node_id}.style.{key} is not a style property — it is dropped")
        elif key in STYLE_NUMBERS and not is_number(value):
            report.error(f"{node_id}.style.{key} is {value!r}, not a number")
        elif key in STYLE_STRINGS and not isinstance(value, str):
            report.error(f"{node_id}.style.{key} is {value!r}, not a string")
        elif key in STYLE_ENUMS and value not in STYLE_ENUMS[key]:
            report.error(
                f"{node_id}.style.{key} is {value!r}, not one of "
                f"{', '.join(sorted(STYLE_ENUMS[key]))}"
            )


def check(doc: object) -> Report:
    """Everything wrong with the document that a blank page would not explain.

    The reader is deliberately forgiving — a missing field is a default, an
    unknown one is carried through, an unknown type is drawn as a rectangle. So
    nearly every mistake in a hand-written document arrives as a drawing that is
    quietly not the one that was meant, and this is the only place that says so.
    """
    report = Report()
    if not isinstance(doc, dict):
        die("the document is not a JSON object")
    nodes = doc.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        die('no "nodes" object — a document is a map of nodes, keyed by id')

    for key in set(doc) - {"version", "id", "title", "rootId", "allowEdit", "nodes"}:
        report.warn(f'"{key}" is not a document field — it is ignored')

    ids = set(nodes)
    root_id = doc.get("rootId")
    if root_id is not None and root_id not in ids:
        report.warn(f'rootId "{root_id}" names no node; an empty root is made for it')
    if root_id is None:
        declared = [key for key, node in nodes.items()
                    if isinstance(node, dict) and node.get("type") == "root"]
        root_id = declared[0] if declared else "root"

    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            report.error(f"{node_id} is not an object")
            continue
        check_node(report, node_id, node, ids, root_id)

    check_tree(report, nodes, root_id)
    return report


def check_node(report: Report, node_id: str, node: dict, ids: set[str], root_id: str) -> None:
    kind = node.get("kind", "link" if isinstance(node.get("targetId"), str) else "shape")
    node_type = node.get("type", "root" if node_id == root_id else "rect")

    if isinstance(node.get("id"), str) and node["id"] != node_id:
        report.error(
            f'{node_id} carries "id": "{node["id"]}", which is the id it actually gets — '
            f"every reference to {node_id} points at nothing. Drop the field; the key is the id"
        )
    for key in set(node) - NODE_FIELDS:
        report.warn(f"{node_id}.{key} is not a node field — it is carried through and never drawn")
    if kind not in ("shape", "link"):
        report.error(f'{node_id}.kind is {kind!r}, not "shape" or "link"')
    if kind == "link":
        # A link is drawn as whatever it points at, so it has no type of its own.
        if "type" in node:
            report.warn(f"{node_id} is a link; it is drawn as {node.get('targetId')!r}, "
                        "so its own type is never used")
    elif not isinstance(node_type, str) or node_type not in TYPES:
        report.error(f"{node_id}.type is {node_type!r} — a rectangle is drawn for it. "
                     f"One of: {', '.join(sorted(TYPES))}")
        node_type = "rect"

    for field in NUMBERS:
        value = node.get(field)
        if value is not None and not is_number(value):
            report.error(f"{node_id}.{field} is {value!r}, not a number")
        elif field in ("w", "h") and is_number(value) and value <= 0:
            report.error(f"{node_id}.{field} is {value}; a shape with no size is invisible")
    for field in STRINGS:
        value = node.get(field)
        if value is not None and not isinstance(value, str):
            report.error(f"{node_id}.{field} is {value!r}, not a string")
    if "style" in node:
        check_style(report, node_id, node["style"])

    parent = node.get("parentId")
    if isinstance(parent, str) and parent and parent not in ids:
        report.error(f'{node_id}.parentId names no node: "{parent}"')
    if node_id == root_id and parent:
        report.warn(f"{node_id} is the root; its parentId is ignored")

    if kind == "link":
        target = node.get("targetId")
        if not isinstance(target, str) or not target:
            report.error(f"{node_id} is a link with no targetId")
        elif target not in ids:
            report.error(f'{node_id}.targetId names no node: "{target}"')
        elif target == node_id:
            report.error(f"{node_id} links to itself")
        return

    if node_type == "arrow":
        for end in ("from", "to"):
            if end not in node:
                report.error(f"{node_id} is an arrow with no {end}")
                continue
            check_endpoint(report, node_id, end, node[end])
            target = endpoint_target(node[end])
            if target and target not in ids:
                report.error(f'{node_id}.{end} names no node: "{target}"')
        for field in ("x", "y", "w", "h"):
            if field in node:
                report.warn(f"{node_id}.{field} is derived on an arrow — it is ignored")
    else:
        for end in ("from", "to"):
            if end in node:
                report.warn(f'{node_id} has "{end}" but is a {node_type}, not an arrow')

    if node_type == "draw":
        points = node.get("points")
        if not isinstance(points, list):
            report.error(f"{node_id}.points is not a list of x, y, x, y… numbers")
        elif len(points) < 4:
            report.error(f"{node_id} is a draw with no path: points needs two points at least")
        elif len(points) % 2:
            report.error(f"{node_id}.points has {len(points)} numbers — pairs, so an even count")
        elif not all(is_number(value) for value in points):
            report.error(f"{node_id}.points holds something that is not a number")
        elif not all(-0.2 <= value <= 1.2 for value in points):
            report.warn(f"{node_id}.points is normalised to the node's own box, 0..1 — "
                        "these look like canvas coordinates")
    elif "points" in node:
        report.warn(f'{node_id} has "points" but is a {node_type}, not a draw')

    if node_type in ("image", "icon") and not node.get("href"):
        report.warn(f"{node_id} is an {node_type} with no href — it draws an empty frame")
    elif "href" in node and node_type not in ("image", "icon"):
        report.warn(f'{node_id} has "href" but is a {node_type} — only image and icon draw one')


def check_tree(report: Report, nodes: dict, root_id: str) -> None:
    """The shape of the hierarchy: cycles, and levels laid out too small."""
    parent_of: dict[str, str] = {}
    for node_id, node in nodes.items():
        if not isinstance(node, dict) or node_id == root_id:
            continue
        parent = node.get("parentId")
        parent_of[node_id] = parent if isinstance(parent, str) and parent in nodes else root_id

    for node_id in parent_of:
        seen = {node_id}
        walk = parent_of.get(node_id)
        while walk and walk not in seen:
            seen.add(walk)
            walk = parent_of.get(walk)
        if walk:
            report.error(f"{node_id} is inside itself: {' -> '.join(sorted(seen))}")
            break  # one cycle explains the rest

    # An arrow can only join shapes in the drawing it is in; one pinned to a
    # node a level away draws to nowhere, and nothing on screen says why.
    for node_id, node in nodes.items():
        if not isinstance(node, dict) or node.get("type") != "arrow":
            continue
        here = parent_of.get(node_id, root_id)
        for end in ("from", "to"):
            target = endpoint_target(node.get(end))
            if target and target in nodes and parent_of.get(target, root_id) != here:
                report.warn(
                    f"{node_id}.{end} is {target}, which is in another drawing — "
                    "an arrow can only join shapes that share a parent"
                )

    children: dict[str, list[dict]] = {}
    for node_id, parent in parent_of.items():
        children.setdefault(parent, []).append(nodes[node_id])

    def extent(node: dict, axis: str, default: float) -> tuple[float, float] | None:
        # Only nodes whose geometry is sound; the rest are already reported.
        start, size = node.get(axis), node.get("w" if axis == "x" else "h", default)
        if not is_number(start) or not is_number(size):
            return None
        return start, start + size

    for parent, siblings in children.items():
        boxes = [node for node in siblings if node.get("type") != "arrow"]
        spans = [
            (x, y) for x, y in ((extent(n, "x", 160), extent(n, "y", 100)) for n in boxes)
            if x and y
        ]
        if len(spans) < 2:
            continue
        width = max(x[1] for x, _ in spans) - min(x[0] for x, _ in spans)
        height = max(y[1] for _, y in spans) - min(y[0] for _, y in spans)
        if width < MIN_CANVAS and height < MIN_CANVAS:
            report.warn(
                f"the drawing inside {parent} spans {round(width)}×{round(height)}; "
                f"a level is framed at {MIN_CANVAS}×{MIN_CANVAS}, so it opens further in "
                "than you laid it out"
            )


# --- pictures ----------------------------------------------------------------


def inline_assets(doc: dict, base: Path) -> list[str]:
    """Every image and icon href turned into something the page carries itself.

    An href that is already a data URI or already markup is left alone, except
    that an oversized picture is still shrunk: the budget is about the file
    somebody opens, not about where the bytes came from.
    """
    notes: list[str] = []
    for node_id, node in doc["nodes"].items():
        if not isinstance(node, dict):
            continue
        href = node.get("href")
        if not isinstance(href, str) or not href.strip():
            continue
        href = href.strip()
        if node.get("type") == "icon":
            notes += inline_icon(node_id, node, href, base)
        elif node.get("type") == "image":
            notes += inline_image(node_id, node, href, base)
    return notes


def inline_icon(node_id: str, node: dict, href: str, base: Path) -> list[str]:
    if href.startswith("<"):
        markup = href
    elif href.startswith("iconify:"):
        try:
            markup = icons.fetch(href[len("iconify:"):])
        except icons.IconError as error:
            die(f"{node_id}: {error}")
    else:
        path = Path(href)
        path = path if path.is_absolute() else base / path
        if not path.is_file():
            die(f"{node_id}: no such icon file: {path}\n"
                "       an icon href is markup, a .svg path, or iconify:prefix:name")
        markup = path.read_text(encoding="utf-8").strip()

    node["href"] = markup
    return [f"{node_id}: {problem}" for problem in icons.check(markup)]


def inline_image(node_id: str, node: dict, href: str, base: Path) -> list[str]:
    # A browser draws an inline SVG in an <image> perfectly well, and there is
    # nothing to re-encode: it is already the smallest form of itself.
    if href.startswith("data:image/svg+xml"):
        return []
    try:
        uri, size, notes = media.resolve(href, base)
    except media.MediaError as error:
        die(f"{node_id}: {error}")

    node["href"] = uri
    if size:
        fit_box(node, size)
    return [f"{node_id}: {note}" for note in notes]


def fit_box(node: dict, size: tuple[int, int]) -> None:
    """The picture's own proportions, for whatever the document left out.

    Give a width and get the matching height; give neither and the picture is
    fitted inside the default image box. A photograph in a square is a
    photograph nobody can read, and working the arithmetic out by hand for
    every picture is exactly the sort of thing a build should do.
    """
    natural_w, natural_h = size
    w, h = node.get("w"), node.get("h")
    if is_number(w) and is_number(h):
        return
    if is_number(w):
        node["h"] = round(w * natural_h / natural_w)
    elif is_number(h):
        node["w"] = round(h * natural_w / natural_h)
    else:
        scale = min(DEFAULT_IMAGE[0] / natural_w, DEFAULT_IMAGE[1] / natural_h)
        node["w"] = round(natural_w * scale)
        node["h"] = round(natural_h * scale)


# --- the page ----------------------------------------------------------------


def fill(page: str, mark: str, value: str) -> str:
    found = page.count(mark)
    if found != 1:
        die(f"the {mark} mark appears {found} times in the template, not once")
    return page.replace(mark, value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("json", type=Path, help="the deepdraw document")
    parser.add_argument("out", type=Path, nargs="?", help="default: <name>.deepdraw.html")
    parser.add_argument("--title", help="the browser tab title; default: the document's")
    parser.add_argument("--read-only", action="store_true",
                        help="open in view mode, with no Save button")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    parser.add_argument("--credit", default=SKILL_CREDIT, metavar="NAME|URL",
                        help="who generated the file, shown bottom right")
    parser.add_argument("--no-credit", dest="credit", action="store_const", const="",
                        help="leave the page signed by the library alone")
    args = parser.parse_args()

    if not args.json.is_file():
        die(f"no such file: {args.json}")
    if not TEMPLATE.is_file():
        die(f"missing {TEMPLATE}")

    # Parse before writing a page around it: invalid JSON renders as a blank
    # white page, with the reason only in the browser console.
    source = args.json.read_text(encoding="utf-8")
    try:
        doc = json.loads(source, object_pairs_hook=no_duplicate_keys)
    except ValueError as error:
        die(f"invalid JSON: {error}")

    report = check(doc)
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for message in report.errors:
        print(f"error: {message}", file=sys.stderr)
    if report.errors:
        raise SystemExit(1)
    if report.warnings and args.strict:
        die(f"{len(report.warnings)} warning(s), and --strict")

    for note in inline_assets(doc, args.json.resolve().parent):
        print(f"warning: {note}", file=sys.stderr)

    # A drawing you cannot move a box in is a picture. Editing is what this
    # format is for, so the file opens in it — with a Save button that writes
    # back to the file it was opened from — unless somebody says otherwise.
    if args.read_only:
        doc.pop("allowEdit", None)
    else:
        doc["allowEdit"] = True

    out = args.out
    if out is None:
        name = args.json.name
        for suffix in (".json", ".deepdraw"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        out = args.json.with_name(f"{name}.deepdraw.html")

    title = args.title if args.title is not None else (doc.get("title") or "DeepDraw")
    credit = ""
    if args.credit:
        name, _, url = args.credit.partition("|")
        credit = (f' &middot; <a href="{html.escape(url, quote=True)}"'
                  f' target="_blank" rel="noreferrer noopener">{html.escape(name)}</a>')

    page = TEMPLATE.read_text(encoding="utf-8")
    page = fill(page, MARKS["title"], html.escape(str(title)))
    page = fill(page, MARKS["credit"], credit)
    # The payload sits inside a <script>, so a "<" in a label, in markdown or in
    # an icon's markup would end the tag early. It is the same character to a
    # JSON reader, and the library's own export escapes it here for the same
    # reason.
    payload = json.dumps(doc, ensure_ascii=False).replace("<", "\\u003c")
    page = fill(page, MARKS["document"], payload)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    stamp = STAMP.read_text(encoding="utf-8").strip() if STAMP.is_file() else "unknown"
    mode = "read-only" if args.read_only else "editable"
    print(f"{out} ({len(page.encode('utf-8')) // 1024} KB, {mode}, deepdraw {stamp})")


if __name__ == "__main__":
    main()
