"""Static topology exporters for AutoCetacean state graphs."""

from __future__ import annotations

import ast
import html
import inspect
import re
import textwrap
from dataclasses import dataclass
from typing import Callable, Optional

from autocetacean.graph import GraphNode, StateGraph


@dataclass(frozen=True)
class _ConditionalRoute:
    """A statically recovered conditional route."""

    target: str
    label: str


class GraphVisualizer:
    """Render a :class:`StateGraph` as Mermaid or a standalone HTML document."""

    _MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"

    @classmethod
    def to_mermaid(cls, graph: StateGraph) -> str:
        """Return a deterministic Mermaid flowchart for ``graph``.

        ``StateGraph`` intentionally keeps conditional routers as callables. For
        static output we recover string targets from the router's return
        expression/code constants. This covers the normal ``return 'a' if ...
        else 'b'`` form while retaining a visible fallback for dynamic routers.
        """
        cls._validate_graph(graph)
        node_ids = {name: f"node_{index}" for index, name in enumerate(graph.nodes, 1)}
        lines = ["flowchart TD"]

        for name, node in graph.nodes.items():
            label = cls._node_label(graph, node)
            node_id = node_ids[name]
            if node.is_gate:
                lines.append(f'    {node_id}{{{{"{label}"}}}}')
            else:
                lines.append(f'    {node_id}["{label}"]')

        for source, target in graph.edges.items():
            if source in node_ids and target in node_ids:
                lines.append(f"    {node_ids[source]} --> {node_ids[target]}")

        for source, router in graph.conditional_edges.items():
            routes = cls._conditional_routes(router, set(graph.nodes))
            if routes:
                for route in routes:
                    lines.append(
                        f"    {node_ids[source]} -.->|{cls._mermaid_text(route.label)}| "
                        f"{node_ids[route.target]}"
                    )
            else:
                route_id = f"route_{node_ids.get(source, 'unknown')}"
                router_label = cls._router_name(router)
                lines.append(f'    {route_id}["conditional route: {cls._mermaid_text(router_label)}"]')
                lines.append(
                    f"    {node_ids.get(source, source)} -.->|conditional| {route_id}"
                )

        lines.extend(
            [
                "    classDef entry fill:#123d5a,stroke:#67d6ff,color:#f2fbff,stroke-width:2px",
                "    classDef finish fill:#123f3a,stroke:#5ee6b4,color:#f2fff9,stroke-width:2px",
                "    classDef gate fill:#5b4315,stroke:#ffd166,color:#fff8de,stroke-width:2px",
                "    classDef layer fill:#102539,stroke:#3d6a88,color:#d9edf8",
            ]
        )
        if graph.entry_point in node_ids:
            lines.append(f"    class {node_ids[graph.entry_point]} entry")
        finish_ids = [node_ids[name] for name in graph.nodes if name in graph.finish_points]
        if finish_ids:
            lines.append(f"    class {','.join(finish_ids)} finish")
        gate_ids = [node_ids[name] for name, node in graph.nodes.items() if node.is_gate]
        if gate_ids:
            lines.append(f"    class {','.join(gate_ids)} gate")

        return "\n".join(lines) + "\n"

    @classmethod
    def to_html(cls, graph: StateGraph, title: str = "AutoCetacean Workflow") -> str:
        """Return a self-contained HTML page embedding the Mermaid source."""
        mermaid = cls.to_mermaid(graph)
        safe_title = html.escape(title, quote=True)
        mermaid_block = html.escape(mermaid)
        return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>{safe_title}</title>
  <style>
    :root {{
      color-scheme: dark;
      --ocean-950: #071521;
      --ocean-900: #0a2032;
      --ocean-800: #0f2d45;
      --ocean-700: #174968;
      --ink: #e7f5fb;
      --muted: #94b2c3;
      --cyan: #67d6ff;
      --mint: #5ee6b4;
      --gold: #ffd166;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ min-height: 100%; }}
    body {{
      margin: 0;
      background: var(--ocean-950);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
        "Noto Sans SC", "Microsoft YaHei", sans-serif;
      line-height: 1.6;
    }}
    .shell {{ max-width: 1440px; margin: 0 auto; padding: 48px 28px 64px; }}
    header {{ display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 24px; }}
    h1 {{ margin: 0; font-size: clamp(1.8rem, 3vw, 3rem); line-height: 1.15; letter-spacing: -0.02em; }}
    .subtitle {{ max-width: 58ch; margin: 10px 0 0; color: var(--muted); font-size: 0.98rem; }}
    .mark {{ color: var(--cyan); font-size: 0.85rem; font-weight: 650; letter-spacing: 0.06em; }}
    .graph-card {{
      min-height: 560px;
      overflow: auto;
      padding: 28px;
      background: var(--ocean-900);
      border: 1px solid var(--ocean-700);
      border-radius: 16px;
    }}
    .mermaid {{ min-width: 760px; text-align: center; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 16px 24px; margin-top: 18px; color: var(--muted); font-size: 0.9rem; }}
    .legend span {{ display: inline-flex; align-items: center; gap: 8px; }}
    .swatch {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
    .entry {{ background: var(--cyan); }} .finish {{ background: var(--mint); }} .gate {{ background: var(--gold); }}
    @media (max-width: 700px) {{ .shell {{ padding: 28px 16px 40px; }} header {{ display: block; }} .graph-card {{ padding: 14px; }} }}
    @media (prefers-reduced-motion: reduce) {{ * {{ scroll-behavior: auto !important; }} }}
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <div class="mark">AUTOCETACEAN / TOPOLOGY</div>
        <h1>{safe_title}</h1>
        <p class="subtitle">A static view of state transitions, conditional routing, layers, and human approval gates.</p>
      </div>
    </header>
    <section class="graph-card" aria-label="Workflow graph">
      <pre class="mermaid">{mermaid_block}</pre>
    </section>
    <div class="legend" aria-label="Graph legend">
      <span><i class="swatch entry"></i>Entry point</span>
      <span><i class="swatch finish"></i>Finish point</span>
      <span><i class="swatch gate"></i>Human gate</span>
    </div>
  </main>
  <script src="{cls._MERMAID_CDN}"></script>
  <script>
    mermaid.initialize({{ startOnLoad: true, securityLevel: "strict", theme: "base", themeVariables: {{ darkMode: true, background: "#0a2032", primaryColor: "#102539", primaryTextColor: "#e7f5fb", primaryBorderColor: "#3d6a88", lineColor: "#67d6ff", secondaryColor: "#123f3a", tertiaryColor: "#5b4315" }} }});
  </script>
</body>
</html>
'''

    @staticmethod
    def _validate_graph(graph: StateGraph) -> None:
        if not isinstance(graph, StateGraph):
            raise TypeError(f"expected StateGraph, got {type(graph).__name__}")

    @staticmethod
    def _node_label(graph: StateGraph, node: GraphNode) -> str:
        markers = []
        if node.name == graph.entry_point:
            markers.append("ENTRY")
        if node.name in graph.finish_points:
            markers.append("FINISH")
        marker = f"; {' / '.join(markers)}" if markers else ""
        layer = getattr(node.layer, "value", str(node.layer))
        return f"{GraphVisualizer._mermaid_text(node.name)} [{GraphVisualizer._mermaid_text(layer)}{marker}]"

    @staticmethod
    def _router_name(router: Callable[..., object]) -> str:
        return getattr(router, "__name__", router.__class__.__name__) or "router"

    @classmethod
    def _conditional_routes(cls, router: Callable[..., object], node_names: set[str]) -> list[_ConditionalRoute]:
        labels: dict[str, str] = {}
        source = cls._router_source(router)
        if source:
            try:
                tree = ast.parse(source)
                for item in ast.walk(tree):
                    if isinstance(item, ast.Return):
                        value = item.value
                        if isinstance(value, ast.IfExp):
                            test = cls._ast_text(value.test)
                            for target_node, branch in ((value.body, f"if {test}"), (value.orelse, "else")):
                                target = cls._literal_string(target_node)
                                if target in node_names:
                                    labels[target] = branch
                        else:
                            target = cls._literal_string(value)
                            if target in node_names:
                                labels.setdefault(target, "route")
                    elif isinstance(item, ast.If):
                        test = cls._ast_text(item.test)
                        body_target = cls._first_return_literal(item.body)
                        if body_target in node_names:
                            labels[body_target] = f"if {test}"
                        else_target = cls._first_return_literal(item.orelse)
                        if else_target in node_names:
                            labels[else_target] = "else"
            except (SyntaxError, ValueError):
                pass

        code = getattr(router, "__code__", None)
        if code is not None:
            for constant in code.co_consts:
                if isinstance(constant, str) and constant in node_names:
                    labels.setdefault(constant, f"route via {cls._router_name(router)}")

        if any(label.startswith("if ") for label in labels.values()):
            for target, label in list(labels.items()):
                if label.startswith("route"):
                    labels[target] = "else"

        return [_ConditionalRoute(target, labels[target]) for target in node_names if target in labels]

    @staticmethod
    def _router_source(router: Callable[..., object]) -> Optional[str]:
        try:
            source = inspect.getsource(router)
        except (OSError, TypeError):
            return None
        return textwrap.dedent(source)

    @staticmethod
    def _first_return_literal(statements: list[ast.stmt]) -> Optional[str]:
        for statement in statements:
            if isinstance(statement, ast.Return):
                return GraphVisualizer._literal_string(statement.value)
        return None

    @staticmethod
    def _literal_string(node: Optional[ast.AST]) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    @staticmethod
    def _ast_text(node: ast.AST) -> str:
        try:
            text = ast.unparse(node)
        except (AttributeError, ValueError):
            text = "condition"
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _mermaid_text(value: object) -> str:
        text = str(value).replace("|", "/").replace('"', "'").replace("\n", " ")
        text = re.sub(r"[()[\]{}'`]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()


__all__ = ["GraphVisualizer"]
