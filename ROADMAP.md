# Roadmap

Ideas for future versions of innomd. Nothing here is committed — these
are notes on directions we have considered and decided to revisit later.

## Under consideration

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
