#!/usr/bin/env python3
"""dag_visualize — Generate DAG graph visualizations from Workflow_Configuration YAML.

Parses a workflow YAML and produces visual representations of the task
dependency graph in multiple formats: Mermaid (markdown-embeddable),
DOT (Graphviz), or plain text.

Usage:
    dag_visualize --config dev/parm/workflow/gcafs.yaml [--format mermaid|dot|text] [--output FILE]

Examples:
    # Print Mermaid diagram to stdout
    dag_visualize --config ../../dev/parm/workflow/gcafs.yaml

    # Generate Graphviz DOT file
    dag_visualize --config ../../dev/parm/workflow/gcafs.yaml --format dot --output gcafs_dag.dot

    # Render to PNG (requires graphviz installed)
    dag_visualize --config ../../dev/parm/workflow/gcafs.yaml --format dot --output gcafs_dag.dot
    dot -Tpng gcafs_dag.dot -o gcafs_dag.png

    # Plain text summary
    dag_visualize --config ../../dev/parm/workflow/gcafs.yaml --format text
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from deployment.workflow_config import DAG, Edge, TaskNode, parse


def dag_to_mermaid(dag: DAG, direction: str = "TD") -> str:
    """Convert a DAG to a Mermaid flowchart diagram.

    Args:
        dag: Parsed workflow DAG.
        direction: Graph direction - TD (top-down), LR (left-right).

    Returns:
        Mermaid diagram string.
    """
    lines: list[str] = []
    lines.append(f"```mermaid")
    lines.append(f"flowchart {direction}")

    # Group nodes by top-level family (cycle) for subgraph rendering
    families: dict[str, list[TaskNode]] = {}
    for node in dag.nodes.values():
        top_family = node.family_path.split("/")[0]
        families.setdefault(top_family, []).append(node)

    # Emit subgraphs for each top-level family
    for family_name, nodes in sorted(families.items()):
        lines.append(f"    subgraph {family_name}[\"{family_name.upper()}\"]")
        for node in sorted(nodes, key=lambda n: n.full_path):
            # Create a short display label
            short_label = f"{node.family_path.split('/')[-1]}/{node.name}"
            node_id = _mermaid_id(node.full_path)
            lines.append(f"        {node_id}[\"{short_label}\"]")
        lines.append(f"    end")

    # Emit edges
    for edge in dag.edges:
        src_id = _mermaid_id(edge.source)
        tgt_id = _mermaid_id(edge.target)
        if edge.kind == "meter":
            # Meter-based triggers get a label
            lines.append(f"    {src_id} -->|\"{edge.expression}\"| {tgt_id}")
        else:
            lines.append(f"    {src_id} --> {tgt_id}")

    lines.append("```")
    return "\n".join(lines)


def dag_to_dot(dag: DAG) -> str:
    """Convert a DAG to Graphviz DOT format.

    Args:
        dag: Parsed workflow DAG.

    Returns:
        DOT language string suitable for graphviz rendering.
    """
    lines: list[str] = []
    lines.append(f'digraph "{dag.suite_name}" {{')
    lines.append('    rankdir=TB;')
    lines.append('    node [shape=box, style=filled, fillcolor=lightyellow, fontsize=10];')
    lines.append('    edge [fontsize=8];')
    lines.append("")

    # Group into subgraphs by top-level family
    families: dict[str, list[TaskNode]] = {}
    for node in dag.nodes.values():
        top_family = node.family_path.split("/")[0]
        families.setdefault(top_family, []).append(node)

    # Color palette for families
    colors = ["#e8f4fd", "#fde8e8", "#e8fde8", "#fdf8e8", "#f0e8fd", "#e8fdfd"]

    for i, (family_name, nodes) in enumerate(sorted(families.items())):
        color = colors[i % len(colors)]
        lines.append(f'    subgraph cluster_{family_name} {{')
        lines.append(f'        label="{family_name.upper()}";')
        lines.append(f'        style=filled;')
        lines.append(f'        color="{color}";')
        for node in sorted(nodes, key=lambda n: n.full_path):
            node_id = _dot_id(node.full_path)
            short_label = f"{node.family_path.split('/')[-1]}/{node.name}"
            jjob_label = node.jjob.replace("_", "\\n") if len(node.jjob) > 20 else node.jjob
            lines.append(f'        {node_id} [label="{short_label}\\n({node.jjob})"];')
        lines.append("    }")
        lines.append("")

    # Edges
    for edge in dag.edges:
        src_id = _dot_id(edge.source)
        tgt_id = _dot_id(edge.target)
        attrs = ""
        if edge.kind == "meter":
            attrs = f' [label="{edge.expression}", style=dashed]'
        lines.append(f'    {src_id} -> {tgt_id}{attrs};')

    lines.append("}")
    return "\n".join(lines)


def dag_to_text(dag: DAG) -> str:
    """Convert a DAG to a plain text summary.

    Args:
        dag: Parsed workflow DAG.

    Returns:
        Human-readable text summary of the DAG structure.
    """
    lines: list[str] = []
    lines.append(f"DAG: {dag.suite_name}")
    lines.append(f"Tasks: {len(dag.nodes)}")
    lines.append(f"Edges: {len(dag.edges)}")
    lines.append("")

    # Group by family path
    families: dict[str, list[TaskNode]] = {}
    for node in dag.nodes.values():
        families.setdefault(node.family_path, []).append(node)

    for family_path, nodes in sorted(families.items()):
        lines.append(f"  {family_path}/")
        for node in sorted(nodes, key=lambda n: n.name):
            trigger_info = ""
            if node.trigger:
                trigger_info = f"  ← {node.trigger[:60]}"
            lines.append(f"    {node.name:<25} jjob={node.jjob}{trigger_info}")
        lines.append("")

    # Dependency summary
    lines.append("Dependency Edges:")
    for edge in sorted(dag.edges, key=lambda e: (e.source, e.target)):
        kind_marker = "→" if edge.kind == "trigger" else "⇢"
        lines.append(f"  {edge.source} {kind_marker} {edge.target}")

    return "\n".join(lines)


def _mermaid_id(path: str) -> str:
    """Convert a task path to a valid Mermaid node ID."""
    return path.replace("/", "_").replace("-", "_")


def _dot_id(path: str) -> str:
    """Convert a task path to a valid DOT node ID."""
    return '"' + path + '"'


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="dag_visualize",
        description="Generate DAG graph visualizations from Workflow_Configuration YAML.",
    )
    parser.add_argument(
        "--config", required=True,
        help="Path to the Workflow_Configuration YAML file.",
    )
    parser.add_argument(
        "--format", choices=["mermaid", "dot", "text"], default="mermaid",
        help="Output format (default: mermaid).",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output file path (default: stdout).",
    )
    parser.add_argument(
        "--direction", choices=["TD", "LR", "BT", "RL"], default="TD",
        help="Graph direction for mermaid (default: TD = top-down).",
    )
    parser.add_argument(
        "--deep", action="store_true", default=False,
        help="Include full execution chain: ecFlow → J-Jobs → ex-scripts → ush scripts.",
    )

    args = parser.parse_args(argv)

    # Resolve config path
    config_path = Path(args.config).resolve()
    if not config_path.is_file():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        return 1

    # Parse the workflow YAML into a DAG
    dag = parse(str(config_path))
    dag.validate_acyclic()

    # If deep mode, trace the full execution chain
    execution_chain = None
    if args.deep:
        execution_chain = _trace_execution_chain(dag, config_path)

    # Generate the requested format
    if args.format == "mermaid":
        if execution_chain:
            output = _deep_mermaid(dag, execution_chain, direction=args.direction)
        else:
            output = dag_to_mermaid(dag, direction=args.direction)
    elif args.format == "dot":
        if execution_chain:
            output = _deep_dot(dag, execution_chain)
        else:
            output = dag_to_dot(dag)
    elif args.format == "text":
        if execution_chain:
            output = _deep_text(dag, execution_chain)
        else:
            output = dag_to_text(dag)
    else:
        print(f"ERROR: Unknown format '{args.format}'", file=sys.stderr)
        return 1

    # Write output
    if args.output:
        Path(args.output).write_text(output + "\n")
        print(f"DAG visualization written to: {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


# ---------------------------------------------------------------------------
# Deep execution chain tracing
# ---------------------------------------------------------------------------

@dataclass
class ExecutionChain:
    """Full execution chain data for a workflow.

    Maps each task to its J-Job, and each J-Job to its ex-scripts and ush scripts.
    """
    # task_path → (app_jjob_name, source_jjob_name)
    task_to_jjob: dict[str, tuple[str, str]]
    # source_jjob_name → set of ex-scripts
    jjob_to_ex_scripts: dict[str, set[str]]
    # ex-script → set of ush scripts
    ex_to_ush: dict[str, set[str]]


def _trace_execution_chain(dag: DAG, config_path: Path) -> ExecutionChain:
    """Trace the full execution chain using the DAG filter's analysis.

    Uses the DAGFilter and NameResolver to map:
    ecFlow task → J-Job (application name) → source J-Job → ex-scripts → ush scripts
    """
    import re
    import yaml
    from deployment.dag_filter import DAGFilter, _EX_SCRIPT_PATTERNS, _USH_SOURCE_PATTERNS
    from deployment.name_resolver import NameResolver, PrefixRegistry

    # Determine dev_root from the config path
    # config is under dev/parm/workflow/ → dev_root = config_path.parent.parent.parent
    dev_root = config_path.parent.parent.parent

    # Load workflow YAML
    with open(config_path) as f:
        workflow_yaml = yaml.safe_load(f) or {}

    # Build the task → jjob mapping from the DAG nodes
    task_to_jjob: dict[str, tuple[str, str]] = {}

    # Set up name resolver
    registry = PrefixRegistry.default()
    resolver = NameResolver(dev_root, registry)

    for task_path, node in dag.nodes.items():
        app_name = node.jjob
        try:
            resolved = resolver.resolve(app_name)
            source_name = resolved.source_name
        except Exception:
            source_name = app_name  # fallback
        task_to_jjob[task_path] = (app_name, source_name)

    # Extract ex-scripts per source J-Job
    jjob_to_ex: dict[str, set[str]] = {}
    unique_sources = {src for _, src in task_to_jjob.values()}

    for source_name in sorted(unique_sources):
        jjob_path = dev_root / "jobs" / source_name
        ex_scripts: set[str] = set()
        if jjob_path.is_file():
            content = jjob_path.read_text(errors="replace")
            for pattern in _EX_SCRIPT_PATTERNS:
                for match in pattern.finditer(content):
                    ex_scripts.add(match.group("script"))
        jjob_to_ex[source_name] = ex_scripts

    # Extract ush scripts per ex-script
    ex_to_ush: dict[str, set[str]] = {}
    all_ex_scripts = set()
    for scripts in jjob_to_ex.values():
        all_ex_scripts.update(scripts)

    for ex_script in sorted(all_ex_scripts):
        ex_path = dev_root / "scripts" / ex_script
        ush_scripts: set[str] = set()
        if ex_path.is_file():
            content = ex_path.read_text(errors="replace")
            for line in content.splitlines():
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                for pattern in _USH_SOURCE_PATTERNS:
                    match = pattern.search(line)
                    if match:
                        ush_scripts.add(match.group("script"))
        ex_to_ush[ex_script] = ush_scripts

    return ExecutionChain(
        task_to_jjob=task_to_jjob,
        jjob_to_ex_scripts=jjob_to_ex,
        ex_to_ush=ex_to_ush,
    )


def _deep_text(dag: DAG, chain: ExecutionChain) -> str:
    """Generate deep text output showing the full execution chain."""
    lines: list[str] = []
    lines.append(f"DAG: {dag.suite_name} (Deep Execution Chain)")
    lines.append(f"Tasks: {len(dag.nodes)}")
    lines.append(f"Unique J-Jobs (source): {len(chain.jjob_to_ex_scripts)}")
    lines.append(f"Ex-Scripts: {sum(len(v) for v in chain.jjob_to_ex_scripts.values())}")
    lines.append(f"Ush Scripts: {sum(len(v) for v in chain.ex_to_ush.values())}")
    lines.append("")
    lines.append("=" * 80)

    # Group tasks by family
    families: dict[str, list[TaskNode]] = {}
    for node in dag.nodes.values():
        families.setdefault(node.family_path, []).append(node)

    for family_path, nodes in sorted(families.items()):
        lines.append(f"\n  {family_path}/")
        lines.append(f"  {'─' * 60}")
        for node in sorted(nodes, key=lambda n: n.name):
            app_name, source_name = chain.task_to_jjob.get(
                node.full_path, (node.jjob, node.jjob)
            )
            rename_note = ""
            if app_name != source_name:
                rename_note = f" (source: {source_name})"

            lines.append(f"    ecf: {node.full_path}.ecf")
            lines.append(f"      → jjob: {app_name}{rename_note}")

            # Ex-scripts for this J-Job
            ex_scripts = chain.jjob_to_ex_scripts.get(source_name, set())
            if ex_scripts:
                for ex in sorted(ex_scripts):
                    lines.append(f"          → script: {ex}")
                    # Ush scripts for this ex-script
                    ush_scripts = chain.ex_to_ush.get(ex, set())
                    if ush_scripts:
                        for ush in sorted(ush_scripts):
                            lines.append(f"                → ush: {ush}")
            else:
                lines.append(f"          → (no ex-scripts found)")
            lines.append("")

    return "\n".join(lines)


def _deep_mermaid(dag: DAG, chain: ExecutionChain, direction: str = "LR") -> str:
    """Generate a Mermaid diagram showing the full execution chain."""
    lines: list[str] = []
    lines.append("```mermaid")
    lines.append(f"flowchart {direction}")

    # Subgraph for each top-level cycle
    families: dict[str, list[TaskNode]] = {}
    for node in dag.nodes.values():
        top_family = node.family_path.split("/")[0]
        families.setdefault(top_family, []).append(node)

    # Track unique artifacts to avoid duplicate declarations
    declared_jjobs: set[str] = set()
    declared_ex: set[str] = set()
    declared_ush: set[str] = set()

    # Emit task nodes grouped by cycle
    for family_name, nodes in sorted(families.items()):
        lines.append(f"    subgraph {family_name}[\"{family_name.upper()} Tasks\"]")
        for node in sorted(nodes, key=lambda n: n.full_path):
            short_label = f"{node.family_path.split('/')[-1]}/{node.name}"
            node_id = _mermaid_id(node.full_path)
            lines.append(f"        {node_id}[[\"{short_label}\"]]")
        lines.append("    end")

    # Emit J-Job nodes
    lines.append(f"    subgraph jjobs[\"J-Jobs\"]")
    for source_name in sorted(chain.jjob_to_ex_scripts.keys()):
        jid = _mermaid_id(f"jjob_{source_name}")
        lines.append(f"        {jid}[\"{source_name}\"]")
        declared_jjobs.add(source_name)
    lines.append("    end")

    # Emit ex-script nodes
    all_ex = set()
    for scripts in chain.jjob_to_ex_scripts.values():
        all_ex.update(scripts)
    if all_ex:
        lines.append(f"    subgraph scripts[\"Ex-Scripts\"]")
        for ex in sorted(all_ex):
            eid = _mermaid_id(f"ex_{ex}")
            lines.append(f"        {eid}([\"{ex}\"])")
            declared_ex.add(ex)
        lines.append("    end")

    # Emit ush script nodes
    all_ush = set()
    for ush_set in chain.ex_to_ush.values():
        all_ush.update(ush_set)
    if all_ush:
        lines.append(f"    subgraph ush_scripts[\"Ush Scripts\"]")
        for ush in sorted(all_ush):
            uid = _mermaid_id(f"ush_{ush}")
            lines.append(f"        {uid}[\"{ush}\"]")
            declared_ush.add(ush)
        lines.append("    end")

    # Cross-cycle and intra-cycle task dependency edges (the DAG structure)
    lines.append("")
    lines.append("    %% Task dependency edges")
    for edge in dag.edges:
        src_id = _mermaid_id(edge.source)
        tgt_id = _mermaid_id(edge.target)
        # Highlight cross-cycle edges
        src_cycle = edge.source.split("/")[0]
        tgt_cycle = edge.target.split("/")[0]
        if src_cycle != tgt_cycle:
            lines.append(f"    {src_id} ==>|\"cross-cycle\"| {tgt_id}")
        else:
            lines.append(f"    {src_id} --> {tgt_id}")

    # Edges: task → jjob (deduplicated by source)
    lines.append("")
    lines.append("    %% Execution chain edges")
    emitted_task_jjob: set[str] = set()
    for task_path, (app_name, source_name) in chain.task_to_jjob.items():
        edge_key = f"{task_path}→{source_name}"
        if edge_key not in emitted_task_jjob:
            tid = _mermaid_id(task_path)
            jid = _mermaid_id(f"jjob_{source_name}")
            lines.append(f"    {tid} -.-> {jid}")
            emitted_task_jjob.add(edge_key)

    # Edges: jjob → ex-script
    for source_name, ex_scripts in chain.jjob_to_ex_scripts.items():
        jid = _mermaid_id(f"jjob_{source_name}")
        for ex in sorted(ex_scripts):
            eid = _mermaid_id(f"ex_{ex}")
            lines.append(f"    {jid} -.-> {eid}")

    # Edges: ex-script → ush
    for ex, ush_scripts in chain.ex_to_ush.items():
        eid = _mermaid_id(f"ex_{ex}")
        for ush in sorted(ush_scripts):
            uid = _mermaid_id(f"ush_{ush}")
            lines.append(f"    {eid} -.-> {uid}")

    lines.append("```")
    return "\n".join(lines)


def _deep_dot(dag: DAG, chain: ExecutionChain) -> str:
    """Generate a Graphviz DOT diagram showing the full execution chain."""
    lines: list[str] = []
    lines.append(f'digraph "{dag.suite_name}_deep" {{')
    lines.append('    rankdir=LR;')
    lines.append('    compound=true;')
    lines.append('    node [fontsize=9];')
    lines.append('')

    # Task nodes (by cycle)
    families: dict[str, list[TaskNode]] = {}
    for node in dag.nodes.values():
        top_family = node.family_path.split("/")[0]
        families.setdefault(top_family, []).append(node)

    for family_name, nodes in sorted(families.items()):
        lines.append(f'    subgraph cluster_tasks_{family_name} {{')
        lines.append(f'        label="{family_name.upper()} Tasks";')
        lines.append(f'        style=filled; color="#e8f4fd";')
        lines.append(f'        node [shape=box, style=filled, fillcolor=white];')
        for node in sorted(nodes, key=lambda n: n.full_path):
            nid = _dot_id(node.full_path)
            short = f"{node.family_path.split('/')[-1]}/{node.name}"
            lines.append(f'        {nid} [label="{short}"];')
        lines.append('    }')

    # J-Job nodes
    lines.append(f'    subgraph cluster_jjobs {{')
    lines.append(f'        label="J-Jobs (dev/jobs/)";')
    lines.append(f'        style=filled; color="#fde8e8";')
    lines.append(f'        node [shape=box, style="filled,bold", fillcolor="#fff0f0"];')
    for source_name in sorted(chain.jjob_to_ex_scripts.keys()):
        jid = _dot_id(f"jjob:{source_name}")
        lines.append(f'        {jid} [label="{source_name}"];')
    lines.append('    }')

    # Ex-script nodes
    all_ex = set()
    for scripts in chain.jjob_to_ex_scripts.values():
        all_ex.update(scripts)
    lines.append(f'    subgraph cluster_scripts {{')
    lines.append(f'        label="Ex-Scripts (dev/scripts/)";')
    lines.append(f'        style=filled; color="#e8fde8";')
    lines.append(f'        node [shape=ellipse, style=filled, fillcolor="#f0fff0"];')
    for ex in sorted(all_ex):
        eid = _dot_id(f"ex:{ex}")
        lines.append(f'        {eid} [label="{ex}"];')
    lines.append('    }')

    # Ush script nodes
    all_ush = set()
    for ush_set in chain.ex_to_ush.values():
        all_ush.update(ush_set)
    if all_ush:
        lines.append(f'    subgraph cluster_ush {{')
        lines.append(f'        label="Ush Scripts (dev/ush/)";')
        lines.append(f'        style=filled; color="#fdf8e8";')
        lines.append(f'        node [shape=parallelogram, style=filled, fillcolor="#fffff0"];')
        for ush in sorted(all_ush):
            uid = _dot_id(f"ush:{ush}")
            lines.append(f'        {uid} [label="{ush}"];')
        lines.append('    }')

    # Edges: task dependencies (the DAG structure — shows cross-cycle links)
    lines.append('')
    lines.append('    // Task dependency edges')
    for edge in dag.edges:
        tid_src = _dot_id(edge.source)
        tid_tgt = _dot_id(edge.target)
        src_cycle = edge.source.split("/")[0]
        tgt_cycle = edge.target.split("/")[0]
        if src_cycle != tgt_cycle:
            lines.append(f'    {tid_src} -> {tid_tgt} [color=red, penwidth=2, label="cross-cycle"];')
        else:
            lines.append(f'    {tid_src} -> {tid_tgt} [color=gray60, style=solid];')

    lines.append('')
    lines.append('    // Execution chain edges')

    # Edges: task → jjob
    emitted: set[str] = set()
    for task_path, (app_name, source_name) in chain.task_to_jjob.items():
        key = f"{task_path}→{source_name}"
        if key not in emitted:
            tid = _dot_id(task_path)
            jid = _dot_id(f"jjob:{source_name}")
            lines.append(f'    {tid} -> {jid} [color=blue, style=dashed];')
            emitted.add(key)

    # Edges: jjob → ex-script
    for source_name, ex_scripts in chain.jjob_to_ex_scripts.items():
        jid = _dot_id(f"jjob:{source_name}")
        for ex in sorted(ex_scripts):
            eid = _dot_id(f"ex:{ex}")
            lines.append(f'    {jid} -> {eid} [color=green, style=dashed];')

    # Edges: ex → ush
    for ex, ush_scripts in chain.ex_to_ush.items():
        eid = _dot_id(f"ex:{ex}")
        for ush in sorted(ush_scripts):
            uid = _dot_id(f"ush:{ush}")
            lines.append(f'    {eid} -> {uid} [color=orange, style=dashed];')

    lines.append('}')
    return "\n".join(lines)

    args = parser.parse_args(argv)

    # Resolve config path
    config_path = Path(args.config).resolve()
    if not config_path.is_file():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        return 1

    # Parse the workflow YAML into a DAG
    dag = parse(str(config_path))
    dag.validate_acyclic()

    # Generate the requested format
    if args.format == "mermaid":
        output = dag_to_mermaid(dag, direction=args.direction)
    elif args.format == "dot":
        output = dag_to_dot(dag)
    elif args.format == "text":
        output = dag_to_text(dag)
    else:
        print(f"ERROR: Unknown format '{args.format}'", file=sys.stderr)
        return 1

    # Write output
    if args.output:
        Path(args.output).write_text(output + "\n")
        print(f"DAG visualization written to: {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
