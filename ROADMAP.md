# Roadmap

Ideas for future versions of innomd. Nothing here is committed — these
are notes on directions we have considered and decided to revisit later.

## Under consideration

### PlantUML activity: nested forks and partitions

The current activity adapter handles `start`/`stop`/`:label;`, `if/
then/else/endif` (with `elseif` chains), `while`/`endwhile`, and
`repeat`/`repeat while`. What it *flattens* (parses but doesn't
reflect in the rendered structure):

- `fork` / `fork again` / `end fork` — parallel splits collapse to a
  sequential flow
- `partition Name { … }` — the partition wrapper is dropped, contents
  render inline

A future pass could render parallel splits as two side-by-side branches
(similar to the if/else split) and partitions as labeled grouping
boxes around their contained nodes.

### Other mermaid diagram types

State machines, ER diagrams, mindmaps, gitGraph, timeline, pie,
quadrant, user-journey are still on the code-block fallback path.
Each would need its own renderer; class/sequence/gantt show the
template. State and ER are graph-shaped (Sugiyama re-use); gitGraph
and timeline are time-axis-shaped (gantt re-use).

### Modern mermaid `@{shape:…}` syntax

Mermaid v11+ introduces a unified shape declaration syntax —
`A@{ shape: cyl, label: "Database" }` — which the current adapter
doesn't recognize. Implementing it requires extending the node parser
to accept the brace-block form and mapping the ~30 new shape names to
existing or new `NodeShape` variants.

### Clickable images and links in watch mode

**Problem.** In a normal terminal, Ctrl+click on an OSC 8 hyperlink opens
it natively (browser, default viewer, etc.). In innomd's watch mode we
capture mouse events for scrolling, which disables the terminal's own
link handling — so Ctrl+click on an image reference does nothing.

**Sketch.**

- Keep `hyperlinks=True` so rich emits OSC 8 sequences in the rendered
  output.
- When building the line buffer, parse OSC 8 sequences
  (`ESC ] 8 ; ; URL ST … ESC ] 8 ; ; ST`) and record, per line, the
  column ranges that map to each URL.
- In the existing mouse handler, detect Ctrl+left-click (SGR button
  code `16`, modifier bit `+16`) and look up the click coordinate
  against the recorded ranges.
- On hit: resolve relative paths against the MD file's directory,
  dispatch via `xdg-open` / `open` / `os.startfile` depending on
  platform.

**Open questions / edge cases.**

- `.ipynb` cells can embed images as base64 — would need to dump to a
  tempfile before opening. Defer to a later pass.
- Differentiate plain mouse selection (drag) from clicks so text
  selection still works.
- Fallback for terminals that don't support SGR modifiers: do nothing
  (don't break existing behavior).

**Why this is deferred.** In one-shot (non-watch) rendering the terminal
already handles Ctrl+click on OSC 8 links. The gap only exists in watch
mode, which is a subset of use. Cost/benefit is moderate; revisit if
usage patterns make it worthwhile.

## Done

- **0.3.0** — interactive file picker when innomd is run without a file
  argument or with a directory argument.
- **Diagram engine — Mermaid flowcharts.** Format-agnostic IR
  (`GraphIR`) + mermaid adapter + grandalf Sugiyama layout + Unicode
  ASCII renderer with 14 node-shape variants (rect, round, stadium,
  diamond/rhombus, hexagon, circle, parallelograms, trapezoids, double
  circle, cylinder, subroutine, asymmetric). Falls back to a code block
  for unsupported syntax.
- **Diagram engine — Mermaid sequence diagrams.** Lifelines + sync/
  async/self-message rendering, `loop`/`alt`/`opt`/`par` block markers
  (gestrichelt rule with bracketed label), participant header repeated
  at the bottom for long diagrams, lifeline preservation at message
  crossings via `┼` glyphs.
- **Diagram engine — Mermaid class diagrams.** Class boxes with name
  + member compartments, UML edge decorations (`△` inheritance at
  parent, `◆` composition / `◇` aggregation at the whole, `▶`
  association at the target, dashed line for dependency, both ends
  for bidirectional). Connected components are shelf-packed left to
  right instead of stacked vertically.
- **Diagram engine — Mermaid gantt charts.** Date axis with year/month-
  day ticks, task bars styled per state (`█` done, `▓` active, `░`
  future), `after <id>` dependencies resolved to absolute dates,
  sections rendered as labeled groups.
- **Diagram engine — pluggable type dispatch.** First-line detection of
  diagram type (flowchart / sequence / class / gantt) so future
  PlantUML adapters can plug into the same renderers without changing
  the public entry point.
- **Diagram engine — PlantUML adapters (sequence, class, gantt).**
  Recognizes ` ```plantuml `, ` ```puml `, ` ```uml `, and the
  `plantumlcode` variant. Auto-detects `@startuml` / `@startgantt` and
  sniffs the body to pick the right adapter.
- **Diagram engine — PlantUML C4 architecture diagrams.** Dedicated
  adapter for the C4-PlantUML macro vocabulary (`Person`, `System`,
  `Container`, `ContainerDb`, `Component`, `Rel`, `BiRel`,
  `System_Boundary` / `Enterprise_Boundary` / `Container_Boundary`).
  Handles named parameters (`$tags=…`, `$sprite=…`) by dropping them
  and using the positional sequence. Plain PlantUML component
  primitives (`rectangle`, `frame`, `interface`, `component`,
  `database`, `queue`, `actor`, `cloud`, `node`, `card`, `folder`,
  `file`) are recognized in the same adapter so component diagrams
  render too.
- **Diagram engine — PlantUML activity diagrams.** Control-flow
  parser for `start` / `stop`, `:Action;` action steps, `if (cond)
  then (yes) … else (no) … endif` decisions with `elseif` chains,
  `while … endwhile` loops, and `repeat … repeat while (cond)` loops.
  Compiles the activity tree into `GraphIR` and renders via the
  flowchart pipeline.
- **Sequence diagrams — notes and activations.** `Note left/right/
  over of X: text` (single-line and multi-line forms) renders as
  small box anchored to the lifeline. `activate X` / `deactivate X`
  overlays a thin vertical bar on the participant's lifeline for the
  duration. Both work for mermaid and PlantUML.
- **Diagram engine — fence-language flexibility and indented fences.**
  In addition to ` ```mermaid `/` ```plantuml `, the parser now
  accepts `puml`, `uml`, and `plantumlcode`. Fences nested inside
  list items (4-space indent) are detected and dedented before
  parsing, so real-world docs with numbered-list-wrapped diagrams
  render correctly.
