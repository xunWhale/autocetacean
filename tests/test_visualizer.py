from pathlib import Path

import pytest

from autocetacean.cli import main
from autocetacean.graph import StateGraph
from autocetacean.types import LayerKind
from autocetacean.visualizer import GraphVisualizer


def test_mermaid_linear_graph_marks_entry_finish_and_layers():
    graph = StateGraph()
    graph.add_node("load", lambda ctx: None, layer=LayerKind.LAYER_2_CONTEXT)
    graph.add_node("save", lambda ctx: None, layer=LayerKind.LAYER_5_GRAPH)
    graph.add_edge("load", "save")
    graph.set_entry_point("load")
    graph.add_finish_point("save")

    source = GraphVisualizer.to_mermaid(graph)

    assert source.startswith("flowchart TD")
    assert "load [CONTEXT; ENTRY]" in source
    assert "save [GRAPH; FINISH]" in source
    assert "-->" in source
    assert "class node_1 entry" in source
    assert "class node_2 finish" in source


def test_mermaid_conditional_routes_include_logic_and_retry_cycle():
    graph = StateGraph()
    graph.add_node("check", lambda ctx: None)
    graph.add_node("retry", lambda ctx: None, layer=LayerKind.LAYER_4_LOOP)
    graph.add_node("done", lambda ctx: None)

    def route(ctx):
        return "done" if ctx.state.get("ready") else "retry"

    graph.add_conditional_edge("check", route)
    graph.add_edge("retry", "check")
    graph.set_entry_point("check")
    graph.add_finish_point("done")

    source = GraphVisualizer.to_mermaid(graph)

    assert "retry" in source and "done" in source
    assert "if ctx.state.get ready" in source
    assert "else" in source
    assert "-.->|" in source
    assert "node_2 --> node_1" in source


def test_mermaid_gate_uses_hexagon_shape_and_gate_class():
    graph = StateGraph()
    graph.add_node("approval", lambda ctx: None, is_gate=True)
    graph.set_entry_point("approval")
    graph.add_finish_point("approval")

    source = GraphVisualizer.to_mermaid(graph)

    assert 'node_1{{"approval [GRAPH; ENTRY / FINISH]"}}' in source
    assert "class node_1 gate" in source


def test_html_export_contains_document_structure_and_mermaid_block():
    graph = StateGraph()
    graph.add_node("start", lambda ctx: None)
    graph.set_entry_point("start")

    document = GraphVisualizer.to_html(graph, title="Deep Sea Workflow")

    assert document.startswith("<!doctype html>")
    assert '<meta charset="utf-8">' in document
    assert "<title>Deep Sea Workflow</title>" in document
    assert '<pre class="mermaid">' in document
    assert "flowchart TD" in document
    assert "mermaid.min.js" in document
    assert "--ocean-950" in document


def test_cli_graph_prints_mermaid_for_module_target(capsys):
    ret = main(["graph", "examples.self_healing_agent:graph"])

    captured = capsys.readouterr()
    assert ret == 0
    assert captured.err == ""
    assert captured.out.startswith("flowchart TD")
    assert "analyze" in captured.out
    assert "harness" in captured.out


def test_cli_graph_writes_html_or_mermaid_file(tmp_path: Path):
    html_path = tmp_path / "workflow.html"
    mermaid_path = tmp_path / "workflow.mmd"

    assert main(["graph", "examples.self_healing_agent:graph", "--format", "html", "--output", str(html_path)]) == 0
    assert main(["graph", "examples.self_healing_agent:graph", "--format", "mermaid", "--output", str(mermaid_path)]) == 0
    assert "<!doctype html>" in html_path.read_text(encoding="utf-8")
    assert mermaid_path.read_text(encoding="utf-8").startswith("flowchart TD")


def test_cli_graph_accepts_python_file_target(tmp_path: Path):
    graph_file = tmp_path / "workflow.py"
    graph_file.write_text(
        "from autocetacean import StateGraph\n"
        "graph = StateGraph()\n"
        "graph.add_node('only', lambda ctx: None)\n"
        "graph.set_entry_point('only')\n",
        encoding="utf-8",
    )
    output = tmp_path / "workflow.mmd"

    assert main(["graph", f"{graph_file}:graph", "--output", str(output)]) == 0
    assert "only" in output.read_text(encoding="utf-8")


def test_cli_graph_invalid_target_is_reported(capsys):
    ret = main(["graph", "missing.module:graph"])

    captured = capsys.readouterr()
    assert ret == 2
    assert "unable to export graph" in captured.err
    assert "module not found" in captured.err


def test_cli_graph_rejects_non_graph_and_missing_target(capsys):
    ret = main(["graph", "autocetacean.cli:main"])
    captured = capsys.readouterr()
    assert ret == 2
    assert "expected StateGraph" in captured.err

    with pytest.raises(SystemExit) as exc:
        main(["graph"])
    assert exc.value.code == 2
