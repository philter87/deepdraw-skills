# deepdraw-skills

A skill for creating interactive and nested drawings.

`skills/deepdraw` writes a deepdraw document as JSON and builds it into one
self-contained HTML page — the drawing plus the library, inlined, no network.
Every shape on the board can hold markdown notes and a whole drawing of its own,
so a picture is something you read into rather than only look at.

## Install

Copy or symlink the skill where your agent looks for skills:

```bash
ln -s "$PWD/skills/deepdraw" ~/.claude/skills/deepdraw     # user-wide
ln -s "$PWD/skills/deepdraw" /path/to/project/.claude/skills/deepdraw
```

It is a deliberate skill: it activates when somebody asks for a deepdraw
drawing, not for diagrams in general.

## Use it by hand

```bash
python3 skills/deepdraw/build.py skills/deepdraw/examples/brainstorm.deepdraw.json
open skills/deepdraw/examples/brainstorm.deepdraw.html
```

Python 3 is the only requirement, on any platform. `build.py` rejects invalid
JSON and dangling references before writing a page around them, and signs the
result bottom right — "Created with deepdraw.ai · deepdraw-skills" — so a reader
who wants another drawing like it can find what made it. `--no-credit` leaves
the page signed by the library alone.

## Layout

```
skills/deepdraw/
  SKILL.md                    what the agent reads
  build.py                    JSON -> standalone HTML
  reference/
    spec.md                   the document format
    cookbook.md               grids, freehand paths, board recipes
    template.html             the page, with the library inlined
    .deepdraw-version         which library build that is
  examples/
    architecture.deepdraw.json
    brainstorm.deepdraw.json
```

## Updating the library

`reference/template.html` is a vendored copy of `deepdraw/lib/dist/template.html`
and `.deepdraw-version` records which build it came from. To move to a newer
library, rebuild the lib and copy both again:

```bash
cp ../deepdraw/lib/dist/template.html skills/deepdraw/reference/template.html
jq -r .version ../deepdraw/lib/package.json > skills/deepdraw/reference/.deepdraw-version
```
