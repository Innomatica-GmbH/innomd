# Roadmap

Ideas for future versions of innomd. Nothing here is committed — these
are notes on directions we have considered and decided to revisit later.

## Under consideration

### PlantUML adapters

The diagram engine's IRs (`GraphIR`, `SequenceIR`, `ClassIR`, `GanttIR`)
are deliberately format-agnostic — populated by mermaid adapters today,
and ready to accept PlantUML adapters tomorrow. Add:

- `adapters/plantuml.py` — PlantUML activity/flowchart syntax → `GraphIR`
- `adapters/plantuml_sequence.py` — `@startuml … @enduml` sequence → `SequenceIR`
- `adapters/plantuml_class.py` — PlantUML class syntax → `ClassIR`
- `adapters/plantuml_gantt.py` — PlantUML gantt → `GanttIR`

Detection key: ` ```plantuml ` fence language plus the `@start<kind>` /
`@end<kind>` markers inside, which identify the diagram type. The
existing renderers stay untouched — only parsing differs between
PlantUML and mermaid sources.

### Sequence diagrams: notes and activations

`Note left of X: …`, `Note right of X: …`, `Note over X,Y: …` and
`activate X` / `deactivate X` are currently parsed-then-skipped by the
sequence adapter. Adding minimal support is mechanical:

- IR: extend `SequenceIR` with a `notes` list and per-message
  activation flags.
- Renderer: notes as small left-/right-anchored boxes between message
  rows; activations as a thin vertical bar overlaid on the lifeline
  while the participant is active.

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
