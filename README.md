<p align="center">
  <img src="assets/innomatica-logo.png" alt="Innomatica GmbH" width="96">
</p>

<h1 align="center">innomd — Terminal Markdown Viewer with LaTeX Math Support</h1>

<p align="center">
  <em>Render Markdown files with real LaTeX math formulas, beautiful tables,
  and syntax-highlighted code — directly in your terminal.</em>
</p>

<p align="center">
  <a href="#installation">Install</a> ·
  <a href="#usage">Usage</a> ·
  <a href="#features">Features</a> ·
  <a href="#comparison">vs glow / mdcat / bat</a> ·
  <a href="#faq">FAQ</a> ·
  <a href="#license">License</a>
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue.svg">
  <img alt="Python" src="https://img.shields.io/badge/python-3.9%2B-blue.svg">
  <img alt="Platform" src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS-lightgrey.svg">
</p>

---

**innomd** is a command-line Markdown viewer for Linux and macOS that
renders LaTeX math (`$$…$$`, `$…$`, `\[…\]`, `\(…\)`) as clean Unicode,
so scientific notes, physics formulas, and technical documentation read
naturally in any terminal. Most CLI Markdown viewers — glow, mdcat, bat —
print `$$\lambda = \frac{b}{T}$$` as raw LaTeX source. `innomd` shows it
as a proper formula:

```
$$\lambda_{\text{peak}} = \frac{b}{T} \quad \text{with } b = 2{,}898 \times 10^{-3} \text{ m·K}$$
```

renders as

```
▌ λₚₑₐₖ = b/T   with b = 2,898 × 10⁻³ m·K
```

---

## Who is this for?

- Scientists, engineers, and students who keep notes in Markdown with
  embedded LaTeX math and want to read them in a terminal instead of a
  browser.
- Data scientists and ML engineers who want to skim `.ipynb` notebooks
  without starting Jupyter.
- Developers writing technical documentation (physics, ML, signal
  processing) who already use tools like `glow`, `mdcat`, or `bat` and
  miss proper math rendering.
- Anyone who prefers a fast, keyboard-driven Markdown preview over
  spinning up VS Code or a PDF viewer.

## Features

- **LaTeX math to Unicode**: `$$…$$`, `$…$`, `\[…\]`, `\(…\)`
  - Greek letters (`\lambda`, `\varepsilon`, `\sigma`, `\pi`, …)
  - Operators (`\cdot`, `\times`, `\nabla`, `\int`, `\sum`, `\propto`, `\approx`, …)
  - Fractions (`\frac`, `\dfrac`, `\tfrac`), roots (`\sqrt`, `\sqrt[n]{x}`)
  - Sub- and superscripts, including nested braces
  - `\text{…}`, `\vec`, `\hat`, `\bar`, `\dot`
  - Blackboard bold (`\mathbb{R}`, `\mathbb{N}`, `\mathbb{Z}`, …)
- **Jupyter notebook support** — pass any `.ipynb` file and it's rendered as
  Markdown: cells, code with syntax highlighting, stream and execution
  outputs.
- **Live reload** — `innomd --watch file.md` re-renders on every save, ideal
  for writing notes in one pane and previewing in another.
- **Theme presets** — 9 built-in color themes: `default`, `nord`, `dracula`,
  `gruvbox`, `solarized-dark`, `solarized-light`, `tokyonight`, `github`,
  `mono`. List with `innomd --list-themes`.
- **Rich Markdown rendering** via [rich](https://github.com/Textualize/rich):
  headings, lists, blockquotes, links, syntax-highlighted code blocks.
- **Beautiful tables** with rounded Unicode borders and column alignment.
- **Subtle horizontal rules** (`---` renders as centered `· · ·`).
- **Pager integration** (`less -R`) with automatic TTY detection.
- **Code-block safe** — math inside fenced code blocks is never substituted.
- **Pure Python** — one script, one dependency (`rich`), no Node, no Go toolchain.

## Installation

Requires Python 3.9+ and [rich](https://pypi.org/project/rich/).

```bash
git clone https://github.com/Innomatica-GmbH/innomd.git
cd innomd
pip install -r requirements.txt
ln -s "$(pwd)/innomd" ~/.local/bin/innomd
```

Or drop `innomd` anywhere on your `$PATH`.

## Usage

```bash
innomd README.md                  # render a file (uses pager on TTY)
innomd analysis.ipynb             # render a Jupyter notebook
innomd --watch notes.md           # live-reload preview
innomd -t dracula file.md         # use a preset theme
innomd -t nord -c dracula file.md # preset + override code theme
innomd --list-themes              # list available presets
cat notes.md | innomd             # pipe from stdin
innomd -P file.md                 # no pager
innomd -w 100 file.md             # fixed width
innomd -r file.md                 # raw preprocessed markdown
```

### Options

| Flag                    | Description                                   |
|-------------------------|-----------------------------------------------|
| `-P`, `--no-pager`      | Print directly, no pager                      |
| `-r`, `--raw`           | Output preprocessed markdown, no render       |
| `-w N`, `--width N`     | Force terminal width in columns               |
| `-t`, `--theme`         | Preset theme (see `--list-themes`)            |
| `-c`, `--code-theme`    | Override Pygments code theme only             |
| `-W`, `--watch`         | Live-reload: re-render on file change         |
| `--list-themes`         | List available preset themes                  |

## Comparison

How `innomd` stacks up against other terminal Markdown viewers:

| Tool     | LaTeX math | Tables | Code highlighting | Images | Language |
|----------|:----------:|:------:|:-----------------:|:------:|:--------:|
| **innomd** | ✅ (Unicode) | ✅ | ✅ | — | Python |
| glow     | ❌ | ✅ | ✅ | — | Go |
| mdcat    | ❌ | ✅ | ✅ | ✅ (Kitty/iTerm2) | Rust |
| bat      | ❌ | ❌ | ✅ (syntax only) | — | Rust |
| frogmouth | ❌ | ✅ | ✅ | — | Python |

If you don't write formulas, use `glow` or `mdcat` — they're excellent.
If you do, this tool exists because nothing else did the job in the terminal.

## FAQ

**Does `innomd` render math like a LaTeX compiler?**
No. It substitutes LaTeX commands with Unicode glyphs. Matrices, large
alignments, and exotic notation will not look like PDF output. Physics
formulas, basic algebra, and common engineering notation render cleanly.

**Why Python and not Rust/Go?**
Because `rich` already solves 90 % of the Markdown-in-terminal problem,
and math preprocessing is a small layer on top. One dependency, one file,
no cross-compilation headaches.

**Why not just use a browser or VS Code preview?**
For quick notes, cat-ing a `.md` in the terminal is faster than opening
a GUI. This tool is for people who already live in tmux.

**Does it work on Windows?**
Probably, via WSL. Native Windows Terminal support is untested.

## Limitations

`innomd` approximates LaTeX with Unicode — it will not render arbitrary math
to pixel perfection. Terminals can't. For papers, export to PDF with `pandoc`.
Notation that survives well: physics formulas, basic algebra, common operators.
Notation that degrades: matrices, commutative diagrams, large alignments.

## Contributing

Issues and pull requests welcome. Keep changes small and focused; there are
no runtime dependencies besides `rich`.

## License

[MIT](LICENSE) © 2026 Innomatica GmbH

Maintainer: Ivan Maradzhiyski &lt;ivan.maradzhiyski@innomatica.de&gt;

---

<p align="center">
  Built by <a href="https://innomatica.de">Innomatica GmbH</a> —
  software engineering for DACH and beyond.
</p>
