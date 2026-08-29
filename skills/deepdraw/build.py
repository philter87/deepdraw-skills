#!/usr/bin/env python3
"""Fill a deepdraw document into the vendored standalone page.

    python3 build.py drawing.json [out.html] [--title "Tab title"]
                     [--credit "Name|https://url"] [--no-credit]

The template carries the whole minified library inline, so the output is one
self-contained file that opens from a disk with no network. Only three marks in
it are replaced: the <title>, the JSON payload, and the credit fragment.

The page signs itself bottom right — "Created with deepdraw.ai", and beside it
this skill, because a reader who wants another drawing like this one wants the
tool that made it rather than this copy of it.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

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


def die(message: str) -> "NoReturn":  # noqa: F821
    print(message, file=sys.stderr)
    raise SystemExit(1)


def check(doc: object) -> None:
    """Everything wrong with the document that a blank page would not explain.

    A dangling id is legal to the reader — a `parentId` naming nothing means the
    top level — but it is almost always a typo, and the drawing it produces is
    wrong in a way nobody looks for.
    """
    if not isinstance(doc, dict):
        die("the document is not a JSON object")
    nodes = doc.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        die('no "nodes" object — a document is a map of nodes, keyed by id')

    ids = set(nodes)
    bad: list[str] = []
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            bad.append(f"{node_id} is not an object")
            continue
        parent = node.get("parentId")
        if parent and parent not in ids:
            bad.append(f"{node_id}.parentId -> {parent}")
        for end in ("from", "to"):
            value = node.get(end)
            # `"from": "api"` is shorthand for `{"nodeId": "api"}`.
            target = value if isinstance(value, str) else (value or {}).get("nodeId")
            if target and target not in ids:
                bad.append(f"{node_id}.{end} -> {target}")
        target = node.get("targetId")
        if target and target not in ids:
            bad.append(f"{node_id}.targetId -> {target}")
    if bad:
        die("dangling references:\n  " + "\n  ".join(bad))

    if doc.get("allowEdit") is not True:
        print('note: no "allowEdit": true — the page opens read-only', file=sys.stderr)


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
        doc = json.loads(source)
    except json.JSONDecodeError as error:
        die(f"invalid JSON: {error}")
    check(doc)

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
    # The payload sits inside a <script>, so a "<" in a label or in markdown
    # would end the tag early. It is the same character to a JSON reader, and
    # the library's own export escapes it here for the same reason.
    page = fill(page, MARKS["document"], source.replace("<", "\\u003c"))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    stamp = STAMP.read_text(encoding="utf-8").strip() if STAMP.is_file() else "unknown"
    print(f"{out} ({len(page.encode('utf-8'))} bytes, deepdraw {stamp})")


if __name__ == "__main__":
    main()
