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

Python 3 and nothing else. It refuses to build on invalid JSON or a dangling id,
warns when the page would open read-only, and signs the page bottom right with
this skill (`--no-credit` drops that).

## Skeleton

Write every field you mean and nothing else — **absent means the default**
(`reference/spec.md`). A node needs a `type`; ids are the map keys.

```json
{
  "version": 1,
  "title": "Order service",
  "rootId": "root",
  "allowEdit": true,
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

`"allowEdit": true` opens the file in edit mode with a Save button. Leave it out
for something meant to be read: view mode gives the two-step click that previews
a nested drawing inside its shape before opening it.

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
| `icon` | inline SVG in `href` | 64×64 |
| `image` | `data:` URI in `href` | 160×120 |
| `group`, `link` | see `reference/spec.md` | — |

## The seven things that catch you out

1. **Labels do not wrap.** Break lines yourself with `\n`, ~18 characters a line.
2. **A nested drawing is its own canvas.** Children of a shape use their own
   coordinates from 0,0 — not the parent's box, not its size. Give each one
   300×300 at least.
3. **A container groups; it does not nest.** Its members are *siblings* declared
   *after* it, drawn on top of it. Use nesting for detail worth a click, a
   container for "these three belong together".
4. **Declaration order is z-order.** Containers and background shapes first.
5. **Arrow ends:** `{"nodeId":"x","side":"right"}` pins an edge midpoint;
   `{"nodeId":"x"}` alone lets the end slide to face the other end — better for
   diagonals; `{"x":..,"y":..}` is a free point.
6. **Markdown is what puts a shape in the hierarchy tree** (so does a nested
   drawing). A box with notes is navigable; one without is only on the canvas.
7. **Arrow labels sit at the midpoint**, so leave ~90px between the shapes an
   arrow labels, or the text lands on them.

## Then

Build it, and check the output opened and looks right — either in a browser, or
by describing the layout back from the JSON. Report the path.

## Files

- `reference/spec.md` — every field, every default, arrows, freehand, groups, links
- `reference/cookbook.md` — layout grids, freehand point sets, common boards
- `examples/architecture.deepdraw.json` — nesting, containers, decision flow, icon, block arrow
- `examples/brainstorm.deepdraw.json` — stickies, freehand annotation, parking lot
- `reference/template.html` — the vendored page; `build.py` fills three marks in it

## Not without a backend

Generated pages have no server, so: AI image generation, icon *search*, image
upload, live collaboration, presence, sharing links and persistence are out.
Icons and images still work when you write the SVG or the `data:` URI yourself.
