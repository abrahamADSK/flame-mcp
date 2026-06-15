#!/usr/bin/env python
"""AST-only graphify build for a single source tree.

Regenerates a code-structure knowledge graph (no semantic/doc nodes, no LLM)
for the given src path, writing into <src>/graphify-out/:
  graph.json, GRAPH_REPORT.md (placeholder community labels), .graphify_analysis.json

Also writes .graphify_isolated.json: every degree-0 node with its attributes so
the caller can map it to a module / MCP server and judge whether it is expected.

Usage: graphify_ast_build.py <src_dir>
"""
import sys
import json
from pathlib import Path

from graphify.detect import detect
from graphify.extract import collect_files, extract
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json


def main() -> int:
    src = Path(sys.argv[1]).resolve()
    out = src / "graphify-out"
    out.mkdir(exist_ok=True)
    # clear stale generated artifacts (keep cache/)
    for stale in ("graph.html", "graph.json", "GRAPH_REPORT.md"):
        p = out / stale
        if p.exists():
            p.unlink()
    for stale in out.glob("*-callflow.html"):
        stale.unlink()
    (out / ".graphify_python").write_text(sys.executable, encoding="utf-8")
    (out / ".graphify_root").write_text(str(src), encoding="utf-8")

    det = detect(src)
    (out / ".graphify_detect.json").write_text(json.dumps(det, ensure_ascii=False), encoding="utf-8")

    code_files = []
    for f in det.get("files", {}).get("code", []):
        p = Path(f)
        code_files.extend(collect_files(p) if p.is_dir() else [p])
    if code_files:
        ast = extract(code_files, cache_root=src)
    else:
        ast = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}

    extraction = {
        "nodes": ast["nodes"],
        "edges": ast["edges"],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    (out / ".graphify_extract.json").write_text(json.dumps(extraction, ensure_ascii=False), encoding="utf-8")

    G = build_from_json(extraction)
    if G.number_of_nodes() == 0:
        print("ERROR: empty graph (no AST nodes extracted)")
        return 1
    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: "Community " + str(cid) for cid in communities}
    questions = suggest_questions(G, communities, labels)
    report = generate(G, communities, cohesion, labels, gods, surprises, det,
                      {"input": 0, "output": 0}, str(src), suggested_questions=questions)
    (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    to_json(G, communities, str(out / "graph.json"))

    analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {str(k): v for k, v in cohesion.items()},
        "gods": gods,
        "surprises": surprises,
        "questions": questions,
    }
    (out / ".graphify_analysis.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")

    # isolated (degree-0) nodes with full attributes for the audit
    isolated = []
    for n, data in G.nodes(data=True):
        if G.degree(n) == 0:
            rec = {"id": n}
            rec.update({k: v for k, v in data.items()})
            isolated.append(rec)
    (out / ".graphify_isolated.json").write_text(json.dumps(isolated, indent=2, ensure_ascii=False), encoding="utf-8")

    print("NODES", G.number_of_nodes(), "EDGES", G.number_of_edges(),
          "COMMUNITIES", len(communities), "ISOLATED", len(isolated))
    # sample attribute keys so the caller knows what's available for mapping
    sample = next(iter(G.nodes(data=True)), (None, {}))[1]
    print("NODE_ATTR_KEYS", sorted(sample.keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
