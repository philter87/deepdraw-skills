# Cookbook

Numbers that work, so you spend your effort on the content rather than on
arithmetic. All of it is a starting grid, not a rule.

## Grids

**A top level that is an index.** Six boxes in a row, each opening into its own
drawing:

```
caption text   x 20,  y 90,  w 900, h 34
box i          x 20 + i*210, y 180, w 170, h 150
arrow i→i+1    side right → side left
```

**A nested drawing, three columns.** Room for a label and two lines of it:

```
box (col c, row r)   x 40 + c*360, y 60 + r*250, w 320, h 170
```

**Detail level, five or six boxes.** Three across, two below, offset:

```
row 0   x 40 / 400 / 760, y 60,  w 300, h 150
row 1   x 220 / 580,      y 280, w 300, h 150
```

**A sticky wall, one column per person:**

```
column label  x 40 + c*300, y 140, w 210, h 28,  fontSize 18, the pad's stroke colour
sticky        x 40 + c*300, y 180 + r*134, w 210, h 118
rotation      -2, 1.5, -1, 2, -1.5 … cycled, never 0
```

Leave **90px** between shapes an arrow labels, or the label lands on them.
Give every level at least 300×300 of content; that is the minimum canvas.

## Freehand sets

`points` is normalised to the node's box, so each set works at any size. Pick
the box to frame what you are marking, then paste the path.

```jsonc
// ring around something — box ≈ the target grown by 15px
[0.5,0.03, 0.22,0.07, 0.05,0.29, 0.04,0.63, 0.2,0.91, 0.52,0.98,
 0.83,0.92, 0.97,0.64, 0.94,0.29, 0.75,0.07, 0.45,0.03, 0.27,0.12]

// squiggle strike-out / underline — box w × 12
[0,0.5, 0.14,0, 0.28,1, 0.42,0, 0.56,1, 0.7,0, 0.84,1, 1,0.4]

// hand-drawn rule under a title — box w × 10
[0,0.7, 0.25,0.25, 0.5,0.85, 0.75,0.2, 1,0.6]

// tick — box 40 × 36
[0,0.55, 0.35,1, 1,0]

// box drawn round a group — box ≈ the group grown by 12px
[0.02,0.06, 0.98,0.02, 0.96,0.95, 0.03,0.98, 0.02,0.05]

// scrawled arrow, one stroke that doubles back — box 120 × 40
[0,0.5, 1,0.5, 0.82,0.22, 1,0.5, 0.82,0.78]
```

Freehand is `stroke` + `strokeWidth` only; 3px red (`#dc2626`) is the marker
everybody reads as "this one".

## Boards worth making

**System map.** Top level: one box per service, dashed containers for the trust
or ownership zones, arrows for the calls. Inside each box: its own internals.
Notes carry the constraint that the picture cannot — the transaction boundary,
the retry policy, the thing that broke last quarter.
→ `examples/architecture.deepdraw.json`

**Brainstorm or retro.** A column of stickies per person, pad colour = author,
freehand ring on the winner, a dashed `container` for the parking lot, one or
two arrows where two ideas touched. Notes hold what was actually said.
→ `examples/brainstorm.deepdraw.json`

**Timeline.** A row of era boxes left to right, plain arrows between them, and a
dashed container underneath for the threads that run through every era. Each era
opens into what happened in it.

**Decision flow.** `diamond` for the question, green box for the happy path, red
box for the refusal, labelled arrows for the branches, a `sticky` in the corner
for the case nobody has handled yet.

**A document.** One `rect` per section on the top level, a paragraph of markdown
in each, and inside it a drawing of what that section is about. The tree pane
becomes the table of contents.

## Choosing between a container and a nested drawing

| | use |
|---|---|
| "these three are one zone" | `container` — the members stay visible |
| "there is a whole picture in here" | nesting — `parentId` |
| "the detail is a paragraph, not a picture" | `markdown` on the shape |

Nesting a shape that holds one box wastes a click. Grouping two shapes that are
already next to each other wastes a rectangle.

## Before you build

- Every `nodeId` in an arrow points at a shape **in the same drawing**.
- Labels have `\n` where they need to break; nothing runs past its box.
- Nothing overlaps that did not mean to — arrow labels especially.
- Each nested drawing lays out from 0,0 and is at least 300×300.
- Colour means one thing, and the caption or root notes say what.
- Root has notes: what this is, how to read it.
