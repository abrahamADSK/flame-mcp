#!/usr/bin/env python
"""Deterministic, LLM-free community names. No API key -> works in CI/online.

Naming rule per community:
  1. mostly package __init__.py     -> "<parent dir> package"
  2. one source file dominates AND  -> that file's stem  (e.g. "shotgrid")
     no other community shares it
  3. otherwise (a file spans many   -> the most-connected node's symbol
     communities, e.g. client.py)      (e.g. "sg_create"), which is distinctive

Writes .graphify_labels.json + regenerates GRAPH_REPORT.md so the names show up
in graph.html after `graphify export html`.

Usage: graphify_autolabel.py <src_dir>
"""
import sys
import json
from pathlib import Path
from collections import Counter, defaultdict

from graphify.build import build_from_json
from graphify.analyze import suggest_questions
from graphify.report import generate

src = Path(sys.argv[1]).resolve()
out = src / "graphify-out"
g = json.loads((out / "graph.json").read_text(encoding="utf-8"))

bycom = defaultdict(list)
for n in g["nodes"]:
    bycom[n.get("community")].append(n)


def clean(label):
    return str(label).split("(")[0].strip().removesuffix(".py")


def dominant_file(members):
    files = [m.get("source_file", "") for m in members if m.get("source_file")]
    if not files:
        return None, 0, 0
    top, n = Counter(files).most_common(1)[0]
    return top, n, len(files)


# pass 1: dominant file per community + how many communities share each
dom = {}
for cid, members in bycom.items():
    dom[cid] = dominant_file(members)
file_share = Counter(d[0] for d in dom.values() if d[0])


def name_for(cid, members):
    top, n, total = dom[cid]
    if top is None:
        return f"Community {cid}"
    # 1. package __init__ community
    init_share = sum(1 for m in members if Path(m.get("source_file", "")).name == "__init__.py")
    if init_share >= max(1, 0.5 * len(members)):
        parent = "/".join(top.split("/")[:-1]).split("/")[-1] or top
        return f"{parent} package"
    # 2. a single file uniquely dominates this community
    if n >= max(2, 0.5 * total) and file_share[top] == 1:
        return Path(top).stem
    # 3. collision / spread -> the community's most-connected node
    rep = max(members, key=lambda m: m.get("degree", 0))
    return clean(rep.get("label") or rep.get("id") or f"Community {cid}")


labels = {}
used = Counter()
for cid, members in bycom.items():
    nm = name_for(cid, members)
    used[nm] += 1
    if used[nm] > 1:
        nm = f"{nm} #{used[nm]}"
    labels[int(cid)] = nm

extraction = json.loads((out / ".graphify_extract.json").read_text(encoding="utf-8"))
detection = json.loads((out / ".graphify_detect.json").read_text(encoding="utf-8"))
analysis = json.loads((out / ".graphify_analysis.json").read_text(encoding="utf-8"))
G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis["communities"].items()}
cohesion = {int(k): v for k, v in analysis["cohesion"].items()}
for cid in communities:
    labels.setdefault(cid, f"Community {cid}")

questions = suggest_questions(G, communities, labels)
report = generate(G, communities, cohesion, labels, analysis["gods"], analysis["surprises"],
                  detection, {"input": 0, "output": 0}, str(src), suggested_questions=questions)
(out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
(out / ".graphify_labels.json").write_text(
    json.dumps({str(k): v for k, v in labels.items()}, ensure_ascii=False), encoding="utf-8")

print(f"autolabeled {len(labels)} communities (file/symbol-based, no LLM)")
for cid in sorted(labels):
    print(f"  {cid}: {labels[cid]}")
