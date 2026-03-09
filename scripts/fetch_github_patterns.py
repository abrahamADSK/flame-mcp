#!/usr/bin/env python3
"""
Phase D — GitHub Pattern Fetcher
Fetches Python script docstrings + READMEs from Flame community repos.
Outputs to docs/flame_community_scripts.md (indexed by RAG on next build).

Run on Mac (or VM with outbound access):
    python scripts/fetch_github_patterns.py

Optional GitHub token (avoids rate limiting, not required for public repos):
    export GITHUB_TOKEN=ghp_...
    python scripts/fetch_github_patterns.py

Sources:
    - logik-portal/python  (community scripts, ~643K lines)
    - pyflame.com / pyflame library  (helper wrappers)
    - kmatchbox/PythonHooks  (hook examples)
    - fabiof17/flame-python-scripting  (curated examples)
"""

import json
import os
import sys
import time
import base64
import argparse
from pathlib import Path
import urllib.request
import urllib.error

REPO_ROOT = Path(__file__).parent.parent
OUTPUT_FILE = REPO_ROOT / "docs" / "flame_community_scripts.md"

GITHUB_API = "https://api.github.com"

REPOS = [
    {
        "repo": "logik-portal/python",
        "description": "Logik Portal community Python scripts for Autodesk Flame",
        "max_scripts": 40,          # cap to avoid bloat
        "fetch_mode": "docstrings", # fetch first N lines of each .py file
        "lines_per_file": 80,
    },
    {
        "repo": "kmatchbox/PythonHooks",
        "description": "Flame Python Hooks collection by kmatchbox",
        "max_scripts": 20,
        "fetch_mode": "full",
        "lines_per_file": 150,
    },
    {
        "repo": "fabiof17/flame-python-scripting",
        "description": "Curated Flame Python scripting examples by fabiof17",
        "max_scripts": 20,
        "fetch_mode": "full",
        "lines_per_file": 150,
    },
]


def gh_get(path: str, token: str | None = None) -> dict | list | None:
    """Make a GitHub API request."""
    url = f"{GITHUB_API}/{path.lstrip('/')}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "flame-mcp-pattern-fetcher/1.0")
    if token:
        req.add_header("Authorization", f"token {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"  Rate limited. Set GITHUB_TOKEN env var to increase limits.")
        elif e.code == 404:
            print(f"  Not found: {url}")
        else:
            print(f"  HTTP {e.code}: {url}")
        return None
    except Exception as e:
        print(f"  Error: {e} ({url})")
        return None


def get_file_content(repo: str, path: str, token: str | None) -> str | None:
    """Fetch a file's content from GitHub."""
    data = gh_get(f"repos/{repo}/contents/{path}", token)
    if not data or not isinstance(data, dict):
        return None
    encoded = data.get("content", "")
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded).decode("utf-8", errors="replace")
    except Exception:
        return None


def get_py_files(repo: str, path: str, token: str | None) -> list[str]:
    """Recursively list all .py files in a repo directory."""
    data = gh_get(f"repos/{repo}/contents/{path}", token)
    if not data or not isinstance(data, list):
        return []
    files = []
    for item in data:
        if item["type"] == "file" and item["name"].endswith(".py"):
            files.append(item["path"])
        elif item["type"] == "dir" and not item["name"].startswith("."):
            # recurse one level
            files.extend(get_py_files(repo, item["path"], token))
    return files


def extract_docstring_section(content: str, max_lines: int) -> str:
    """Return first max_lines of content, focusing on docstrings and key patterns."""
    lines = content.split("\n")
    return "\n".join(lines[:max_lines])


def process_repo(repo_cfg: dict, token: str | None, out_file) -> int:
    """Process one GitHub repo and write patterns to output file."""
    repo = repo_cfg["repo"]
    description = repo_cfg["description"]
    max_scripts = repo_cfg.get("max_scripts", 20)
    lines_per_file = repo_cfg.get("lines_per_file", 100)

    print(f"\n{'='*60}")
    print(f"Repo: {repo}")
    print(f"Description: {description}")

    # Fetch README
    readme = get_file_content(repo, "README.md", token)
    if not readme:
        readme = get_file_content(repo, "readme.md", token)

    out_file.write(f"\n## Source: {repo}\n\n")
    out_file.write(f"**Description**: {description}  \n")
    out_file.write(f"**URL**: https://github.com/{repo}\n\n")

    if readme:
        # Truncate README to first 100 lines
        readme_lines = readme.split("\n")[:100]
        out_file.write("### README\n\n")
        out_file.write("\n".join(readme_lines))
        out_file.write("\n\n")
        print(f"  README: {len(readme_lines)} lines")

    # Fetch Python files
    py_files = get_py_files(repo, "", token)
    # Sort by path, skip __init__.py and test files
    py_files = [f for f in py_files if not f.endswith("__init__.py")
                and "test" not in f.lower()]
    py_files = sorted(py_files)[:max_scripts]

    print(f"  Python files: {len(py_files)} (capped at {max_scripts})")

    written = 0
    for fpath in py_files:
        content = get_file_content(repo, fpath, token)
        if not content or len(content.strip()) < 50:
            continue

        snippet = extract_docstring_section(content, lines_per_file)
        fname = fpath.split("/")[-1]

        out_file.write(f"### {fname}\n\n")
        out_file.write(f"**Path**: `{fpath}`  \n")
        out_file.write(f"**URL**: https://github.com/{repo}/blob/main/{fpath}\n\n")
        out_file.write("```python\n")
        out_file.write(snippet)
        if len(content.split("\n")) > lines_per_file:
            out_file.write(f"\n# ... [{len(content.split(chr(10)))} total lines, truncated]\n")
        out_file.write("\n```\n\n")

        written += 1
        time.sleep(0.2)  # rate limit courtesy

    print(f"  Written: {written} scripts")
    return written


def main():
    parser = argparse.ArgumentParser(description="Fetch GitHub Python patterns for Flame")
    parser.add_argument("--repo", help="Process only this repo (e.g. logik-portal/python)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Note: No GITHUB_TOKEN set. Using unauthenticated (60 req/hour limit).")
        print("Set GITHUB_TOKEN env var for 5000 req/hour.\n")

    repos = REPOS
    if args.repo:
        repos = [r for r in repos if r["repo"] == args.repo]
        if not repos:
            print(f"Repo {args.repo} not in sources list")
            sys.exit(1)

    if args.dry_run:
        print("Dry run — would process:")
        for r in repos:
            print(f"  {r['repo']}")
        return

    total = 0
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("# Flame Community Python Scripts\n\n")
        out.write("Auto-extracted from GitHub by fetch_github_patterns.py.\n")
        out.write("Contains script docstrings and patterns from community repositories.\n\n")
        out.write("---\n")

        for repo_cfg in repos:
            count = process_repo(repo_cfg, token, out)
            total += count

    print(f"\n✅ Total scripts written: {total}")
    print(f"   Output: {OUTPUT_FILE}")
    print("\nNext step:")
    print("  python rag/build_index.py   # rebuild RAG to include community scripts")


if __name__ == "__main__":
    main()
