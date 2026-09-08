---
name: deepdraw
description: Draw a deepdraw drawing — a zoomable whiteboard where every shape can hold markdown notes and its own nested drawing — and build it into one self-contained HTML file. Use ONLY when the user explicitly asks for a deepdraw / deepdrawing, or asks to update a .deepdraw.json or .deepdraw.html file. Do not use it for ordinary diagrams, mermaid, SVG or slides.
disable-model-invocation: true
---

# deepdraw

**A skill for creating interactive and nested drawings.**

You write a JSON document; `build.py` wraps it in a page with the library inlined.
The result is one file that opens from a disk with no network.

```bash
python3 build.py mydrawing.deepdraw.json     # -> mydrawing.deepdraw.html
python3 build.py doc.json out.html --title "Tab title"
```

The build **checks the document** against the format and refuses on anything
that would render as silence — a dangling id, a misspelt `type`, a style
property nobody reads. What it only warns about, `--strict` refuses too. It
**inlines every picture and icon** (below), and signs the page bottom right with
this skill (`--no-credit` drops that).

The page **opens editable**, with a Save button that writes back to the file it
was opened from. `--read-only` opens it in view mode instead — worth it for
something meant to be read, where the two-step click previews a nested drawing
inside its shape before opening it.

## Skeleton

Write every field you mean and nothing else — **absent means the default**
(`reference/spec.md`). A node needs a `type`; ids are the map keys.

```json
{
  "version": 1,
  "title": "Order service",
  "rootId": "root",
  "nodes": {
    "root": { "type": "root", "markdown": "# Order service\n\nWhat this board is." },
    "api":  { "type": "rect", "x": 40, "y": 60, "w": 200, "h": 110, "text": "Order API",
              "markdown": "Detail that does not fit on the box.",
              "style": { "fill": "#ecfdf5", "stroke": "#059669" } },
    "db":   { "type": "rect", "x": 340, "y": 60, "w": 200, "h": 110, "text": "Postgres" },
    "e1":   { "type": "arrow", "from": { "nodeId": "api", "side": "right" },
                               "to":   { "nodeId": "db",  "side": "left" }, "text": "writes" },
    "t1":   { "parentId": "api", "type": "rect", "x": 40, "y": 60, "w": 200, "h": 100,
              "text": "inside the API" }
  }
}
```

## Shapes

| type | for | default size |
|---|---|---|
| `rect` | the default box | 160×100 |
| `ellipse` | a circle, a store, an actor | 140×100 |
| `diamond` | a decision | 140×100 |
| `sticky` | a note in somebody's voice; label sits top-left | 140×140 |
| `text` | titles, captions, margin notes — no box | 160×32 |
| `container` | **dashed frame that groups siblings**; holds nothing | 320×240 |
| `arrow` | a relationship; `from`/`to`, not x/y | — |
| `draw` | freehand: a ring, an underline, a strike-out | — |
| `fatArrow` | a block arrow, points right; rotate to turn it | 160×70 |
| `icon` | a glyph; `href` (see below) | 64×64 |
| `image` | a picture; `href` (see below) | 160×120 |
| `group`, `link` | see `reference/spec.md` | — |


## Pictures and icons

Write what the picture *is* in `href` and let the build carry it in. Nothing in
the document is ever base64, and the page still opens with no network.

```json
"shot": { "type": "image", "x": 40, "y": 60, "w": 420,
          "href": "screenshots/checkout.png", "text": "Checkout, today" },
"far":  { "type": "image", "x": 40, "y": 400,
          "href": "https://upload.wikimedia.org/…/Chart.png" },
"db":   { "type": "icon",  "x": 40, "y": 620, "href": "iconify:mdi:database",
          "text": "Postgres", "style": { "textColor": "#059669" } }
```

- **`image`** — a path beside the JSON, an `https://` URL, or a `data:` URI.
  Fetched, scaled to fit 900px and re-encoded under 250 KB on the way in.
  Give `w` **or** `h` and the other comes from the picture's own proportions;
  give neither and it is fitted into 160×120.
- **`icon`** — `iconify:prefix:name`, a path to a `.svg` file, or raw `<svg>`
  markup. Find names with `python3 icons.py search database`; most icons are
  drawn in `currentColor`, so `style.textColor` recolours them.
- **A picture's caption is its `text`**, which sits centred *below* the image or
  icon by default. That is where a label belongs — not in a `text` node you
  then have to keep aligned under it.

```bash
python3 icons.py search server            # names, grouped by set
python3 icons.py get mdi:database --out icons/
python3 media.py photo.jpg                # what it will weigh, as a file
```

## Hints
 - use colors as a way to group related shapes
 - remember to use images found online when investigating a subject to illustrate
 - you can also group shapes within a single layer using a dashed rect
 - plan a composition/layout where arrows dont cross over other shapes 
 - `python3 icons.py search QUERY` finds icons; keep one Iconify set across a
   drawing so the glyphs look drawn by one hand
 - an image's own `text` is its caption — it renders centred under the picture
 - NEVER use em-dash. That is – or —

## Then

Build it, and check the output opened and looks right — either in a browser, or
by describing the layout back from the JSON. Report the path.

## Files

- `media.py` — pictures: fetch, scale, re-encode. `build.py` calls it for you
- `icons.py` — icons: search Iconify, write `.svg` files, check markup
- `reference/spec.md` — every field, every default, arrows, freehand, groups, links
- `reference/cookbook.md` — layout grids, freehand point sets, common boards
- `examples/architecture.deepdraw.json` — nesting, containers, decision flow, icon, block arrow
- `examples/brainstorm.deepdraw.json` — stickies, freehand annotation, parking lot
- `reference/template.html` — the vendored page; `build.py` fills three marks in it

## Not without a backend

Generated pages have no server, so inside the page: AI image generation, icon
search, image upload, live collaboration, presence, sharing links and
persistence are out. Pictures and icons are put in **while building** —
`icons.py`, `media.py` and the hrefs above — and are part of the file after
that.
