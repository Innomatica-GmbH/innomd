"""Tests for the diagram engine: adapter, layout, renderer, integration."""
import unittest

from conftest import load_innomd

innomd = load_innomd()


class TestMermaidAdapter(unittest.TestCase):
    """Mermaid → GraphIR parser."""

    def setUp(self):
        from innomd.diagrams.adapters.mermaid import parse
        from innomd.diagrams.errors import AdapterError
        from innomd.diagrams.ir import (
            ArrowStyle, Direction, EdgeStyle, NodeShape,
        )
        self.parse = parse
        self.AdapterError = AdapterError
        self.Direction = Direction
        self.EdgeStyle = EdgeStyle
        self.ArrowStyle = ArrowStyle
        self.NodeShape = NodeShape

    def test_simple_chain(self):
        ir = self.parse("graph TD\n  A --> B\n  B --> C")
        self.assertEqual(ir.direction, self.Direction.TD)
        self.assertEqual({n.id for n in ir.nodes}, {"A", "B", "C"})
        self.assertEqual(len(ir.edges), 2)
        for e in ir.edges:
            self.assertEqual(e.style, self.EdgeStyle.SOLID)
            self.assertEqual(e.arrow, self.ArrowStyle.END)

    def test_all_directions(self):
        for token, expected in (("TD", "TD"), ("LR", "LR"),
                                ("BT", "BT"), ("RL", "RL")):
            ir = self.parse(f"graph {token}\n  A --> B")
            self.assertEqual(ir.direction.value, expected)

    def test_node_shapes(self):
        ir = self.parse(
            'flowchart TD\n'
            '  A[Rect]\n'
            '  B(Round)\n'
            '  C((Circle))\n'
            '  D{Diamond}\n'
            '  E([Stadium])\n'
        )
        shapes = {n.id: n.shape for n in ir.nodes}
        self.assertEqual(shapes["A"], self.NodeShape.RECT)
        self.assertEqual(shapes["B"], self.NodeShape.ROUND)
        self.assertEqual(shapes["C"], self.NodeShape.CIRCLE)
        self.assertEqual(shapes["D"], self.NodeShape.DIAMOND)
        self.assertEqual(shapes["E"], self.NodeShape.STADIUM)

    def test_quoted_label(self):
        ir = self.parse('graph TD\n  A["with spaces & punct!"] --> B')
        a = next(n for n in ir.nodes if n.id == "A")
        self.assertEqual(a.label, "with spaces & punct!")

    def test_pipe_label(self):
        ir = self.parse("graph TD\n  A -->|hello| B")
        self.assertEqual(ir.edges[0].label, "hello")

    def test_inline_label(self):
        ir = self.parse("graph TD\n  A -- yes --> B")
        self.assertEqual(ir.edges[0].label, "yes")

    def test_dashed_and_thick_edges(self):
        ir = self.parse("graph TD\n  A -.-> B\n  A ==> C\n  A --- D")
        styles = {e.dst: (e.style, e.arrow) for e in ir.edges}
        self.assertEqual(styles["B"][0], self.EdgeStyle.DASHED)
        self.assertEqual(styles["C"][0], self.EdgeStyle.THICK)
        self.assertEqual(styles["D"][0], self.EdgeStyle.SOLID)
        self.assertEqual(styles["D"][1], self.ArrowStyle.NONE)

    def test_chained_edges_on_one_line(self):
        ir = self.parse("flowchart LR\n  A --> B --> C")
        self.assertEqual(len(ir.edges), 2)
        self.assertEqual({(e.src, e.dst) for e in ir.edges},
                         {("A", "B"), ("B", "C")})

    def test_missing_header_raises(self):
        with self.assertRaises(self.AdapterError):
            self.parse("A --> B")

    def test_unknown_direction_raises(self):
        with self.assertRaises(self.AdapterError):
            self.parse("graph XX\n  A --> B")

    def test_unclosed_bracket_raises(self):
        with self.assertRaises(self.AdapterError):
            self.parse("graph TD\n  A[unclosed --> B")

    def test_yaml_frontmatter_is_skipped(self):
        """Mermaid v10+ allows ``--- ... ---`` config preamble before the header."""
        ir = self.parse(
            "---\ntitle: My flow\n---\nflowchart LR\n  A --> B"
        )
        self.assertEqual(ir.direction, self.Direction.LR)
        self.assertEqual({n.id for n in ir.nodes}, {"A", "B"})

    def test_frontmatter_with_nested_config(self):
        ir = self.parse(
            "---\n"
            "title: foo\n"
            "config:\n"
            "  flowchart:\n"
            "    htmlLabels: false\n"
            "---\n"
            "graph TD\n"
            "  A --> B"
        )
        self.assertEqual(len(ir.nodes), 2)

    def test_single_node_is_valid(self):
        """``flowchart LR\\n  id`` defines one node and zero edges."""
        ir = self.parse("flowchart LR\n  id")
        self.assertEqual(len(ir.nodes), 1)
        self.assertEqual(ir.nodes[0].id, "id")
        self.assertEqual(len(ir.edges), 0)


class TestLayout(unittest.TestCase):
    """grandalf integration."""

    def setUp(self):
        from innomd.diagrams.adapters.mermaid import parse
        from innomd.diagrams.layout.grandalf import compute_layout
        self.parse = parse
        self.compute_layout = compute_layout

    def test_layout_assigns_coordinates_to_every_node(self):
        ir = self.parse("graph TD\n  A --> B\n  B --> C")
        lay = self.compute_layout(ir)
        ids = {nb.node.id for nb in lay.nodes}
        self.assertEqual(ids, {"A", "B", "C"})

    def test_layered_order_top_down(self):
        ir = self.parse("graph TD\n  A --> B\n  B --> C")
        lay = self.compute_layout(ir)
        by_id = {nb.node.id: nb for nb in lay.nodes}
        self.assertLess(by_id["A"].cy, by_id["B"].cy)
        self.assertLess(by_id["B"].cy, by_id["C"].cy)

    def test_lr_swaps_axes(self):
        ir = self.parse("flowchart LR\n  A --> B --> C")
        lay = self.compute_layout(ir)
        by_id = {nb.node.id: nb for nb in lay.nodes}
        # In LR mode, layers run left-to-right; cy should be similar.
        self.assertLess(by_id["A"].cx, by_id["B"].cx)
        self.assertLess(by_id["B"].cx, by_id["C"].cx)


class TestRenderer(unittest.TestCase):
    """Public render_mermaid entry point."""

    def setUp(self):
        from innomd.diagrams import render_mermaid
        self.render = render_mermaid

    def test_simple_chain_renders(self):
        out = self.render("graph TD\n  A --> B\n  B --> C", width=80)
        self.assertIsNotNone(out)
        joined = "\n".join(out)
        # Both labels appear in the output.
        self.assertIn("A", joined)
        self.assertIn("B", joined)
        self.assertIn("C", joined)
        # A vertical arrow is drawn somewhere.
        self.assertIn("▼", joined)

    def test_ascii_only_uses_ascii_glyphs(self):
        out = self.render("graph TD\n  A --> B", width=80, ascii_only=True)
        joined = "\n".join(out)
        self.assertIn("v", joined)              # arrow tip
        self.assertNotIn("▼", joined)
        self.assertNotIn("─", joined)           # no Unicode box-drawing
        self.assertIn("+", joined)              # corners

    def test_invalid_returns_none(self):
        # Garbage input must not raise.
        out = self.render("not mermaid at all\nrandom text", width=80)
        self.assertIsNone(out)

    def test_too_narrow_returns_none(self):
        # Below minimum width, the renderer must back out cleanly.
        out = self.render("graph TD\n  A --> B", width=5)
        self.assertIsNone(out)

    def test_dashed_and_thick_glyphs(self):
        # Single chains in TD give the longest vertical runs, which is where
        # dashed/thick line styles are most visible.
        dashed = self.render("graph TD\n  A -.-> B", width=80)
        self.assertIn("╎", "\n".join(dashed))
        thick = self.render("graph TD\n  A ==> B", width=80)
        self.assertIn("┃", "\n".join(thick))


class TestPreprocessIntegration(unittest.TestCase):
    """End-to-end: ``` mermaid blocks rendered via preprocess()."""

    def setUp(self):
        self.preprocess = innomd.preprocess

    def test_mermaid_fence_replaced_with_rendering(self):
        src = (
            "Intro\n\n"
            "```mermaid\n"
            "graph TD\n"
            "  A --> B\n"
            "```\n\n"
            "Outro\n"
        )
        out = self.preprocess(src, diagram_width=80)
        # Original mermaid header line is gone, replaced by box-drawing.
        self.assertNotIn("graph TD", out)
        self.assertIn("┌", out)

    def test_no_diagrams_flag_preserves_source(self):
        src = "```mermaid\ngraph TD\n  A --> B\n```\n"
        out = self.preprocess(src, diagrams_enabled=False, diagram_width=80)
        self.assertIn("graph TD", out)

    def test_invalid_mermaid_falls_back_to_original(self):
        src = "```mermaid\ngarbage not mermaid\n```\n"
        out = self.preprocess(src, diagram_width=80)
        # Fallback: original block kept verbatim, no rendering.
        self.assertIn("garbage not mermaid", out)
        self.assertIn("```mermaid", out)

    def test_non_mermaid_fence_left_alone(self):
        src = "```python\nprint('hi')\n```\n"
        out = self.preprocess(src, diagram_width=80)
        self.assertEqual(out, src)


class TestSequenceDiagram(unittest.TestCase):
    """Sequence diagram parser + renderer."""

    def setUp(self):
        from innomd.diagrams.adapters.mermaid_sequence import parse
        from innomd.diagrams.render.sequence import render
        from innomd.diagrams.ir_sequence import MessageStyle
        self.parse = parse
        self.render = render
        self.MessageStyle = MessageStyle

    def test_basic_message(self):
        ir = self.parse("sequenceDiagram\n  Alice->>Bob: hi")
        self.assertEqual({p.id for p in ir.participants}, {"Alice", "Bob"})
        self.assertEqual(len(ir.messages), 1)
        self.assertEqual(ir.messages[0].style, self.MessageStyle.SYNC)

    def test_async_message(self):
        ir = self.parse("sequenceDiagram\n  Alice-->>Bob: hi")
        self.assertEqual(ir.messages[0].style, self.MessageStyle.ASYNC)

    def test_self_message(self):
        ir = self.parse("sequenceDiagram\n  Alice->>Alice: think")
        self.assertEqual(ir.messages[0].src, ir.messages[0].dst)

    def test_explicit_participants(self):
        ir = self.parse(
            "sequenceDiagram\n"
            "  participant Alice as A\n"
            "  Alice->>Bob: hi"
        )
        labels = {p.id: p.label for p in ir.participants}
        self.assertEqual(labels["Alice"], "A")

    def test_loop_block_skipped(self):
        ir = self.parse(
            "sequenceDiagram\n"
            "  Alice->>Bob: m1\n"
            "  loop X\n"
            "    Alice->>Bob: m2\n"
            "  end"
        )
        self.assertEqual(len(ir.messages), 2)

    def test_renders_terminal_lines(self):
        ir = self.parse("sequenceDiagram\n  Alice->>Bob: hi")
        out = self.render(ir, width=80)
        self.assertTrue(any("Alice" in ln for ln in out))
        self.assertTrue(any("Bob" in ln for ln in out))
        self.assertTrue(any("▶" in ln for ln in out))


class TestClassDiagram(unittest.TestCase):
    """Class diagram parser + renderer."""

    def setUp(self):
        from innomd.diagrams.adapters.mermaid_class import parse
        from innomd.diagrams.layout.grandalf import compute_layout_class
        from innomd.diagrams.render.class_ import render
        from innomd.diagrams.ir_class import ClassEdgeKind
        self.parse = parse
        self.compute = compute_layout_class
        self.render = render
        self.ClassEdgeKind = ClassEdgeKind

    def test_inheritance_edge(self):
        ir = self.parse("classDiagram\n  Animal <|-- Dog")
        self.assertEqual(len(ir.edges), 1)
        # `Animal <|-- Dog` means Dog inherits from Animal — we store the
        # edge with src=Animal (parent, top of layout) and dst=Dog (child).
        e = ir.edges[0]
        self.assertEqual(e.kind, self.ClassEdgeKind.INHERITANCE)
        self.assertEqual(e.src, "Animal")
        self.assertEqual(e.dst, "Dog")

    def test_composition_edge(self):
        ir = self.parse("classDiagram\n  Car *-- Engine")
        self.assertEqual(ir.edges[0].kind, self.ClassEdgeKind.COMPOSITION)

    def test_member_lines(self):
        ir = self.parse(
            "classDiagram\n"
            "  Animal : +int age\n"
            "  Animal : +bark()\n"
        )
        animal = next(n for n in ir.nodes if n.id == "Animal")
        self.assertEqual(len(animal.members), 2)
        self.assertEqual(animal.members[0].text, "+int age")

    def test_renders_terminal_lines(self):
        ir = self.parse(
            "classDiagram\n"
            "  Animal <|-- Dog\n"
            "  Animal : +int age\n"
        )
        layout = self.compute(ir)
        out = self.render(layout, width=80)
        joined = "\n".join(out)
        self.assertIn("Animal", joined)
        self.assertIn("Dog", joined)
        self.assertIn("+int age", joined)


class TestGanttChart(unittest.TestCase):
    """Gantt chart parser + renderer."""

    def setUp(self):
        from innomd.diagrams.adapters.mermaid_gantt import parse
        from innomd.diagrams.render.gantt import render
        from innomd.diagrams.ir_gantt import TaskState
        self.parse = parse
        self.render = render
        self.TaskState = TaskState

    def test_basic_task(self):
        ir = self.parse(
            "gantt\n"
            "dateFormat YYYY-MM-DD\n"
            "Task A : t1, 2025-01-01, 5d"
        )
        self.assertEqual(len(ir.tasks), 1)
        self.assertEqual(ir.tasks[0].name, "Task A")

    def test_task_states(self):
        ir = self.parse(
            "gantt\n"
            "dateFormat YYYY-MM-DD\n"
            "Done one : done, t1, 2025-01-01, 1d\n"
            "Active : active, t2, 2025-01-02, 1d\n"
            "Future : t3, 2025-01-03, 1d"
        )
        states = {t.id: t.state for t in ir.tasks}
        self.assertEqual(states["t1"], self.TaskState.DONE)
        self.assertEqual(states["t2"], self.TaskState.ACTIVE)
        self.assertEqual(states["t3"], self.TaskState.FUTURE)

    def test_after_dependency(self):
        ir = self.parse(
            "gantt\n"
            "dateFormat YYYY-MM-DD\n"
            "First : t1, 2025-01-01, 3d\n"
            "Second : t2, after t1, 2d"
        )
        first, second = ir.tasks
        self.assertEqual(second.start, first.end)

    def test_section_grouping(self):
        ir = self.parse(
            "gantt\n"
            "dateFormat YYYY-MM-DD\n"
            "section Phase 1\n"
            "Setup : t1, 2025-01-01, 2d\n"
            "section Phase 2\n"
            "Deploy : t2, after t1, 2d"
        )
        self.assertEqual(ir.tasks[0].section, "Phase 1")
        self.assertEqual(ir.tasks[1].section, "Phase 2")

    def test_renders_terminal_lines(self):
        ir = self.parse(
            "gantt\n"
            "dateFormat YYYY-MM-DD\n"
            "title My project\n"
            "Setup : done, t1, 2025-01-01, 3d\n"
            "Deploy : active, t2, after t1, 2d"
        )
        out = self.render(ir, width=80)
        joined = "\n".join(out)
        self.assertIn("My project", joined)
        self.assertIn("Setup", joined)
        self.assertIn("Deploy", joined)


class TestDispatch(unittest.TestCase):
    """render_mermaid auto-dispatches by diagram type."""

    def setUp(self):
        from innomd.diagrams import render_mermaid
        self.render = render_mermaid

    def test_dispatch_flowchart(self):
        out = self.render("graph TD\n  A --> B", width=80)
        self.assertIsNotNone(out)
        self.assertIn("┌", "\n".join(out))   # box drawing → flowchart

    def test_dispatch_sequence(self):
        out = self.render("sequenceDiagram\n  A->>B: hi", width=80)
        self.assertIsNotNone(out)
        self.assertIn("▶", "\n".join(out))   # arrow → sequence

    def test_dispatch_class(self):
        out = self.render("classDiagram\n  A <|-- B", width=80)
        self.assertIsNotNone(out)
        joined = "\n".join(out)
        # Inheritance triangle is one of △ ▽ ◁ ▷ depending on direction.
        self.assertTrue(any(t in joined for t in "△▽◁▷"))

    def test_dispatch_gantt(self):
        out = self.render(
            "gantt\ndateFormat YYYY-MM-DD\nT : done, t1, 2025-01-01, 1d",
            width=80,
        )
        self.assertIsNotNone(out)
        self.assertIn("█", "\n".join(out))   # done bar → gantt

    def test_unknown_type_returns_none(self):
        out = self.render("not a known diagram type", width=80)
        self.assertIsNone(out)


class TestPlantUMLSequence(unittest.TestCase):
    """PlantUML sequence adapter."""

    def setUp(self):
        from innomd.diagrams.adapters.plantuml_sequence import parse
        from innomd.diagrams.ir_sequence import MessageStyle
        self.parse = parse
        self.MessageStyle = MessageStyle

    def test_basic_sync(self):
        ir = self.parse("@startuml\nAlice -> Bob: hi\n@enduml")
        self.assertEqual({p.id for p in ir.participants}, {"Alice", "Bob"})
        self.assertEqual(ir.messages[0].style, self.MessageStyle.SYNC)

    def test_async_dashed(self):
        ir = self.parse("@startuml\nAlice --> Bob: returns\n@enduml")
        self.assertEqual(ir.messages[0].style, self.MessageStyle.ASYNC)

    def test_apostrophe_in_text_not_treated_as_comment(self):
        # Inline apostrophe (e.g. `Bob's`) must not eat the rest of the line.
        ir = self.parse("@startuml\nAlice -> Bob: ask Bob's name\n@enduml")
        self.assertEqual(ir.messages[0].text, "ask Bob's name")

    def test_loop_block(self):
        ir = self.parse(
            "@startuml\n"
            "Alice -> Bob: m1\n"
            "loop forever\n"
            "  Alice -> Bob: m2\n"
            "end\n"
            "@enduml"
        )
        self.assertEqual(len(ir.blocks), 1)
        self.assertEqual(ir.blocks[0].kind, "loop")
        self.assertEqual(ir.blocks[0].label, "forever")

    def test_explicit_participant_label(self):
        ir = self.parse(
            '@startuml\n'
            'participant Alice as "Alice Smith"\n'
            'Alice -> Bob: hi\n'
            '@enduml'
        )
        labels = {p.id: p.label for p in ir.participants}
        self.assertEqual(labels["Alice"], "Alice Smith")


class TestPlantUMLClass(unittest.TestCase):
    """PlantUML class adapter."""

    def setUp(self):
        from innomd.diagrams.adapters.plantuml_class import parse
        from innomd.diagrams.ir_class import ClassEdgeKind
        self.parse = parse
        self.ClassEdgeKind = ClassEdgeKind

    def test_inheritance_parent_at_top(self):
        ir = self.parse("@startuml\nAnimal <|-- Dog\n@enduml")
        e = ir.edges[0]
        # Parent is src (top of layout); Animal is parent.
        self.assertEqual(e.src, "Animal")
        self.assertEqual(e.dst, "Dog")
        self.assertEqual(e.kind, self.ClassEdgeKind.INHERITANCE)

    def test_class_block_with_members(self):
        ir = self.parse(
            "@startuml\n"
            "class Animal {\n"
            "  +String name\n"
            "  +int age\n"
            "  +makeSound()\n"
            "}\n"
            "@enduml"
        )
        animal = next(n for n in ir.nodes if n.id == "Animal")
        self.assertEqual(len(animal.members), 3)
        self.assertEqual(animal.members[0].text, "+String name")

    def test_single_line_member(self):
        ir = self.parse(
            "@startuml\n"
            "Animal : +int age\n"
            "@enduml"
        )
        animal = next(n for n in ir.nodes if n.id == "Animal")
        self.assertEqual(animal.members[0].text, "+int age")

    def test_composition(self):
        ir = self.parse("@startuml\nCar *-- Engine\n@enduml")
        e = ir.edges[0]
        self.assertEqual(e.kind, self.ClassEdgeKind.COMPOSITION)
        self.assertEqual(e.src, "Car")    # whole
        self.assertEqual(e.dst, "Engine") # part


class TestPlantUMLGantt(unittest.TestCase):
    """PlantUML gantt adapter."""

    def setUp(self):
        from innomd.diagrams.adapters.plantuml_gantt import parse
        from innomd.diagrams.ir_gantt import TaskState
        self.parse = parse
        self.TaskState = TaskState

    def test_basic_task(self):
        ir = self.parse(
            "@startgantt\n"
            "project starts 2024-01-01\n"
            "[Setup] lasts 5 days\n"
            "@endgantt"
        )
        self.assertEqual(len(ir.tasks), 1)
        t = ir.tasks[0]
        self.assertEqual(t.name, "Setup")
        self.assertEqual((t.end - t.start).days, 5)

    def test_after_dependency(self):
        ir = self.parse(
            "@startgantt\n"
            "project starts 2024-01-01\n"
            "[A] lasts 5 days\n"
            "[B] lasts 3 days\n"
            "[B] starts at [A]'s end\n"
            "@endgantt"
        )
        a, b = ir.tasks
        self.assertEqual(b.start, a.end)

    def test_done_state(self):
        ir = self.parse(
            "@startgantt\n"
            "project starts 2024-01-01\n"
            "[X] lasts 1 day\n"
            "[X] is done\n"
            "@endgantt"
        )
        self.assertEqual(ir.tasks[0].state, self.TaskState.DONE)

    def test_percent_completed(self):
        ir = self.parse(
            "@startgantt\n"
            "project starts 2024-01-01\n"
            "[X] lasts 1 day\n"
            "[X] is 50% completed\n"
            "@endgantt"
        )
        self.assertEqual(ir.tasks[0].state, self.TaskState.ACTIVE)

    def test_section(self):
        ir = self.parse(
            "@startgantt\n"
            "project starts 2024-01-01\n"
            "-- Phase 1 --\n"
            "[X] lasts 1 day\n"
            "@endgantt"
        )
        self.assertEqual(ir.tasks[0].section, "Phase 1")


class TestPlantUMLDispatch(unittest.TestCase):
    """End-to-end dispatch: ```plantuml fences route to the right adapter."""

    def setUp(self):
        from innomd.diagrams import render_mermaid
        self.render = render_mermaid

    def test_dispatch_sequence(self):
        out = self.render(
            "@startuml\nAlice -> Bob: hi\n@enduml", width=80
        )
        self.assertIsNotNone(out)
        self.assertIn("Alice", "\n".join(out))
        self.assertIn("▶", "\n".join(out))

    def test_dispatch_class(self):
        out = self.render(
            "@startuml\nAnimal <|-- Dog\n@enduml", width=80
        )
        self.assertIsNotNone(out)
        joined = "\n".join(out)
        self.assertIn("Animal", joined)
        self.assertTrue(any(t in joined for t in "△▽◁▷"))

    def test_dispatch_gantt(self):
        out = self.render(
            "@startgantt\n"
            "project starts 2024-01-01\n"
            "[T] lasts 1 day\n"
            "@endgantt",
            width=80,
        )
        self.assertIsNotNone(out)
        self.assertIn("░", "\n".join(out))


if __name__ == "__main__":
    unittest.main()
