#!/usr/bin/env python3
"""
Phase D — Pattern Extractor
Processes downloaded transcripts and extracts Flame Python API patterns
using Claude API. Outputs to docs/flame_youtube_patterns.md

Run on Mac after fetch_transcripts.py:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    python scripts/extract_patterns.py

Or process a single transcript:
    python scripts/extract_patterns.py --id VJFgxnCqrE0
"""

import json
import os
import sys
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
TRANSCRIPTS_DIR = REPO_ROOT / "docs" / "transcripts"
OUTPUT_FILE = REPO_ROOT / "docs" / "flame_youtube_patterns.md"
SOURCES_FILE = SCRIPT_DIR / "youtube_sources.json"

EXTRACTION_PROMPT = """You are an expert Autodesk Flame Python developer analyzing a video transcript.

Extract all concrete Python API patterns, code snippets, and scripting techniques mentioned.
Focus on:
- flame.* API calls and class usage
- Python hook functions (app_initialized, batch_render_begin, etc.)
- Custom menu registration patterns
- Clip/library/workspace manipulation
- Batch group creation and management
- Export/render automation
- MediaHub integration
- Any specific code patterns or gotchas mentioned

For each pattern found, output a markdown section:

## Pattern: <short name>
**Source**: {video_title} ({video_id})
**Topics**: <comma-separated>

```python
# Description of what this does
<code or pseudo-code>
```

**Notes**: <any caveats, version requirements, or gotchas>

---

If no concrete Python patterns are found, output:
## No Python patterns found
**Reason**: <why>

Video metadata:
- Title: {title}
- Topics: {topics}
- Notes: {notes}

Transcript:
{transcript}
"""


def extract_patterns_from_transcript(
    video_id: str,
    title: str,
    topics: list,
    notes: str,
    transcript_text: str,
    client,
) -> str:
    """Call Claude API to extract patterns from a transcript."""
    # Truncate very long transcripts
    max_chars = 40000
    if len(transcript_text) > max_chars:
        transcript_text = transcript_text[:max_chars] + "\n\n[TRANSCRIPT TRUNCATED]"

    prompt = EXTRACTION_PROMPT.format(
        video_title=title,
        video_id=video_id,
        title=title,
        topics=", ".join(topics),
        notes=notes,
        transcript=transcript_text,
    )

    message = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def main():
    parser = argparse.ArgumentParser(description="Extract API patterns from transcripts")
    parser.add_argument("--id", help="Process only this video ID")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print transcript paths without calling API")
    parser.add_argument("--append", action="store_true", default=True,
                        help="Append to existing output file (default: True)")
    args = parser.parse_args()

    # Load sources
    with open(SOURCES_FILE) as f:
        sources = json.load(f)

    # Collect all episodes
    all_episodes = []
    for ch_key, ch_data in sources.items():
        if not isinstance(ch_data, dict) or "episodes" not in ch_data:
            continue
        for ep in ch_data["episodes"]:
            ep["_channel"] = ch_key
            all_episodes.append(ep)

    if args.id:
        all_episodes = [ep for ep in all_episodes if ep.get("id") == args.id]

    # Filter to episodes with downloaded transcripts
    to_process = []
    for ep in all_episodes:
        vid_id = ep.get("id", "")
        tp = TRANSCRIPTS_DIR / f"{vid_id}.txt"
        if tp.exists():
            to_process.append((ep, tp))
        else:
            print(f"  ⏭  {vid_id}: no transcript, skipping")

    if not to_process:
        print("No transcripts found. Run fetch_transcripts.py first.")
        sys.exit(0)

    if args.dry_run:
        print(f"Would process {len(to_process)} transcripts:")
        for ep, tp in to_process:
            print(f"  - {tp.name}: {ep.get('title','')[:60]}")
        return

    # Initialize Claude client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except ImportError:
        print("ERROR: anthropic not installed. Run: pip install anthropic")
        sys.exit(1)

    print(f"\n=== Extracting patterns from {len(to_process)} transcripts ===\n")

    # Write/append output
    mode = "a" if args.append and OUTPUT_FILE.exists() else "w"
    with open(OUTPUT_FILE, mode, encoding="utf-8") as out:
        if mode == "w":
            out.write("# Flame Python Patterns from YouTube\n\n")
            out.write("Auto-extracted by extract_patterns.py from video transcripts.\n\n")
            out.write("---\n\n")

        for ep, transcript_path in to_process:
            vid_id = ep.get("id", "")
            title = ep.get("title", "")
            topics = ep.get("topics", [])
            notes = ep.get("notes", "")

            print(f"Processing: {vid_id} — {title[:60]}")
            transcript_text = transcript_path.read_text(encoding="utf-8")

            try:
                patterns = extract_patterns_from_transcript(
                    vid_id, title, topics, notes, transcript_text, client
                )
                out.write(f"\n<!-- Source: {title} | {vid_id} -->\n\n")
                out.write(patterns)
                out.write("\n\n---\n\n")
                print(f"  ✅ patterns extracted")
            except Exception as e:
                print(f"  ❌ Error: {e}")
                out.write(f"\n<!-- FAILED: {vid_id} — {e} -->\n\n")

    print(f"\n✅ Output written to: {OUTPUT_FILE}")
    print("\nNext step:")
    print("  python rag/build_index.py   # rebuild RAG index to include new patterns")


if __name__ == "__main__":
    main()
