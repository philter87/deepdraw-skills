# Document format

One JSON document holds the whole hierarchy. Nodes live in a flat `nodes` map
and form a tree through `parentId`; **a node's children are its nested drawing**.
There is no separate drawing entity.

```json
{
  "version": 1,
  "id": "optional",
  "title": "Shown in the tab and the top bar",
  "rootId": "root",
  "nodes": { "<id>": { ...node }, ... }
}
```

`allowEdit` sits beside the document, not in it: `true` opens the page in edit
mode with a Save button that writes the file back; absent opens it read-only in
view mode. **`build.py` writes it for you** — every built page is editable
unless you pass `--read-only` — so a document need not carry it.

## Absent means default

The reader fills in everything a file leaves out, so write only what you mean:

- no `parentId` (or one naming a missing node) → the top level
- no `index` → declaration order, which is also z-order
- no `w`/`h` → the type's own size
- a style property you don't name → the type's default for **that property**
  (naming `fill` keeps the stroke, font and alignment)
- no root node → one is made, so a bare list of shapes is a one-level drawing
- `"from": "api"` on an arrow means `{"nodeId": "api"}`

## Node

| field | |
|---|---|
| `type` | see below. The only field a node really needs |
| `parentId` | which drawing it is in. Absent = top level |
| `index` | z-order and tree order among siblings. Absent = declaration order |
| `x`, `y`, `w`, `h` | in the **parent drawing's own coordinates**, top-left origin |
| `rotation` | degrees, about the centre |
| `text` | the label drawn on the shape. **No wrapping** — break with `\n` |
| `markdown` | notes shown in the pane when the node is selected |
| `style` | see below |
| `from`, `to` | arrows only |
| `points` | `draw` only |
| `href` | the picture: see **Pictures** below |
| `groupId` | siblings sharing a string move together |

## Types and their deviations from the default style

Everything not listed is `fill #ffffff`, `stroke #334155`, centred, 14px.

| type | default size | its own defaults |
|---|---|---|
| `rect` | 160×100 | — |
| `ellipse` | 140×100 | `radius: 0` |
| `diamond` | 140×100 | `radius: 0` |
| `sticky` | 140×140 | `#fef08a` on `#eab308`, 1px, `hAlign: left`, `vAlign: top` |
| `text` | 160×32 | no fill, no stroke, `hAlign: left` |
| `container` | 320×240 | no fill, `strokeStyle: dashed`, `vAlign: top`, `radius: 4` |
| `arrow` | — | `fill: none`, `arrowEnd: open` |
| `draw` | — | `fill: none`, no radius, no label |
| `fatArrow` | 160×70 | `fill: #e2e8f0`; points right, rotate to turn it |
| `icon` | 64×64 | no fill/stroke, `vAlign: below` (label under the glyph) |
| `image` | 160×120 | no fill/stroke, `vAlign: below` |
| `group` | 160×100 | invisible box; a nesting shape with nothing drawn |
| `root` | — | the top level. Its `markdown` is the document's front page |
| `square` | 120×120 | legacy; use `rect` |

## Style

| property | default | |
|---|---|---|
| `fill` | `#ffffff` | also `transparent` / `none` |
| `stroke` | `#334155` | |
| `strokeWidth` | `2` | |
| `strokeStyle` | `solid` | `dashed`, `dotted` |
| `radius` | `8` | corner radius |
| `textColor` | `#0f172a` | |
| `fontSize` | `14` | |
| `fontFamily` | `system-ui, sans-serif` | |
| `hAlign` | `center` | `left`, `right` |
| `vAlign` | `middle` | `above`, `top`, `bottom`, `below` — `above`/`below` put the label outside the shape |
| `opacity` | `1` | |
| `arrowStart` | `none` | arrows: `triangle`, `open`, `dot` |
| `arrowEnd` | `open` | `triangle`, `dot`; `none` makes a plain connector |
| `sloppiness` | `1` | how hand-drawn the outline is: `0` exact, `2` pronounced |

## Arrows

`from` and `to` are endpoints; `x`/`y`/`w`/`h` on an arrow are derived, so leave
them out. Three kinds of end:

```json
{ "nodeId": "api", "side": "right" }          // pinned to an edge midpoint
{ "nodeId": "api", "anchor": { "x": 1, "y": 0.25 } }  // a point on the border, 0..1 of its box
{ "nodeId": "api" }                            // free: slides around the border to face the other end
{ "x": 320, "y": 180 }                         // a loose point in the drawing
```

All the pinned forms are proportional, so they survive a resize. Use `side` for
orthogonal rows and columns; use the free form for diagonals. An arrow's `text`
renders at its midpoint. Arrows can only join shapes **in the same drawing**.

## Freehand (`draw`)

`points` is a flat `x, y, x, y…` path **normalised to the node's own box**: 0 is
its left/top edge, 1 its right/bottom. So the same point set is a ring at any
size, and the box is what you move and scale. No label. See `cookbook.md` for
sets you can paste.

## Nesting

Give a node `parentId` and it becomes part of that shape's nested drawing. The
child's coordinates start again at 0,0 in a canvas of its own — a 170×150 parent
routinely holds a drawing 1200 wide. A drawing is framed by at least 300×300, so
lay each level out at 300+ or it opens further in than you meant.

A shape shows a badge for notes and a badge for a nested drawing, and appears in
the hierarchy tree if it has either.

## Groups and links

- `groupId`: a string shared by siblings that should move as one. Cheaper than a
  `group` node and does not change the tree.
- A **link node** (`"kind": "link"`, `targetId`) draws another node here, sharing
  its nested drawing, with its own geometry and optional `style`/`text`
  overrides. Use it when the same subsystem appears on two boards. Everything
  else in a document is `"kind": "shape"`, which is the default.

## Markdown

Rendered and sanitized: headings, emphasis, lists, tables, code, links,
blockquotes, images by URL or `data:` raster. No raw HTML, no `<svg>`, no
`<style>`. `@Name` — or `@[Name with spaces]` — links to a shape with that
label, rendered as a chip you can click.

## Pictures

An `image` and an `icon` both carry their picture in `href`, and both take their
label from `text` — which sits **centred below** the shape (`vAlign: below`), so
a caption is a field of the picture rather than a `text` node to keep aligned
under it.

**What the reader wants.** An `image` href is a URL the browser can load — in a
built page that means a `data:` URI, since the file has no network. An `icon`
href is raw SVG *markup*, rebuilt through an allowlist before it is drawn: `svg
g defs symbol use title desc path rect circle ellipse line polyline polygon text
tspan clipPath mask pattern linearGradient radialGradient stop`, with
presentation and geometry attributes. No `<image>`, no script, no animation, and
`href`/`url()` may only point inside the file. Markup that does not survive that
draws an empty frame, so `build.py` warns about what would be dropped.

**What you write.** `build.py` resolves the shorthands into the above, so the
document stays readable:

| `href` on… | may be | becomes |
|---|---|---|
| `image` | `pics/shot.png` — a path beside the JSON | a `data:` URI |
| `image` | `https://…/chart.png` | fetched, then a `data:` URI |
| `image` | `data:image/png;base64,…` | itself, shrunk if it is heavy |
| `icon` | `iconify:mdi:database` | the set's markup, fetched once and cached |
| `icon` | `icons/mdi-database.svg` — a path | the file's markup |
| `icon` | `<svg viewBox="0 0 24 24">…` | itself |

Every picture is scaled to fit 900px and re-encoded under 250 KB (`media.py`);
an SVG file belongs in an `icon`, not an `image`. Sizing follows the picture:
give `w` **or** `h` and the other is computed from its proportions, give neither
and it is fitted inside 160×120. Give both and it letterboxes — the renderer
never distorts a picture to fill a box.

Most Iconify icons are drawn in `currentColor`, which takes `style.textColor` —
one icon, recoloured per shape. `python3 icons.py search QUERY` lists names.
