#!/usr/bin/env python3
"""
Phase D — YouTube Transcript Fetcher
Reads youtube_sources.json, downloads transcripts for all pending episodes,
and saves them to docs/transcripts/<video_id>.txt

Run this on your Mac (not in the MCP VM):
    pip install youtube-transcript-api
    python scripts/fetch_transcripts.py

Optional — also fetch full channel video lists:
    pip install yt-dlp
    python scripts/fetch_transcripts.py --inventory
"""

import json
import os
import sys
import time
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
SOURCES_FILE = SCRIPT_DIR / "youtube_sources.json"
TRANSCRIPTS_DIR = REPO_ROOT / "docs" / "transcripts"


def fetch_transcript(video_id: str, title: str) -> str | None:
    """Download transcript for a single video. Returns text or None."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        # v0.6.0+ requires instantiation; list() replaced list_transcripts()
        ytt = YouTubeTranscriptApi()
        transcript_list = ytt.list(video_id)

        # Prefer manual English transcript, fall back to auto-generated
        try:
            transcript = transcript_list.find_manually_created_transcript(["en"])
        except Exception:
            try:
                transcript = transcript_list.find_generated_transcript(["en"])
            except Exception:
                # Try any available language
                transcript = list(transcript_list)[0]

        fetched = transcript.fetch()
        # Each snippet has a .text attribute in v0.6.0+
        text = " ".join(
            snippet.text if hasattr(snippet, "text") else snippet["text"]
            for snippet in fetched
        )
        print(f"  ✅ {video_id}: {title[:60]}")
        return text

    except ImportError:
        print("ERROR: youtube-transcript-api not installed.")
        print("Run: pip install youtube-transcript-api")
        sys.exit(1)
    except Exception as e:
        print(f"  ⚠️  {video_id}: {title[:50][:60]} — {e}")
        return None


def fetch_channel_inventory(channel_handle: str, channel_id: str) -> list[dict]:
    """Use yt-dlp to fetch all video metadata from a channel (flat, no download)."""
    try:
        import subprocess
        import json as _json

        url = f"https://www.youtube.com/{channel_handle}/videos"
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--dump-json",
            "--no-warnings",
            "--playlist-end", "500",
            url,
        ]
        print(f"Fetching inventory for {channel_handle}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                item = _json.loads(line)
                videos.append({
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "url": f"https://www.youtube.com/watch?v={item.get('id','')}",
                    "upload_date": item.get("upload_date", ""),
                    "duration": item.get("duration", 0),
                    "view_count": item.get("view_count", 0),
                })
            except Exception:
                continue

        print(f"  Found {len(videos)} videos")
        return videos

    except FileNotFoundError:
        print("ERROR: yt-dlp not found. Install with: pip install yt-dlp")
        return []
    except Exception as e:
        print(f"  Error fetching inventory: {e}")
        return []


def filter_python_relevant(videos: list[dict]) -> list[dict]:
    """Heuristically filter videos likely to contain Python/scripting content."""
    import re
    keywords = re.compile(
        r"python|script|automat|hook|batch.*render|render.*naming|"
        r"mediahub|watch.folder|openclip|custom.menu|api|pyflame|"
        r"workflow.*tool|tool.*workflow",
        re.IGNORECASE,
    )
    return [v for v in videos if keywords.search(v.get("title", ""))]


def main():
    parser = argparse.ArgumentParser(description="Fetch Flame Python video transcripts")
    parser.add_argument("--inventory", action="store_true",
                        help="Also fetch full channel inventory via yt-dlp")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be fetched without downloading")
    parser.add_argument("--id", help="Fetch transcript for a single video ID only")
    args = parser.parse_args()

    # Load sources
    with open(SOURCES_FILE) as f:
        sources = json.load(f)

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Optionally fetch full channel inventories ──────────────────────────
    if args.inventory:
        print("\n=== Fetching full channel inventories ===")
        for ch_key, ch_data in sources.items():
            if not isinstance(ch_data, dict) or "episodes" not in ch_data:
                continue
            handle = ch_data.get("channel_handle") or ch_data.get("channel_id")
            if not handle:
                continue
            videos = fetch_channel_inventory(handle, ch_data.get("channel_id", ""))
            relevant = filter_python_relevant(videos)
            inv_path = SCRIPT_DIR / f"inventory_{ch_key}.json"
            with open(inv_path, "w") as f:
                json.dump({"all": videos, "python_relevant": relevant}, f, indent=2)
            print(f"  Saved {len(videos)} videos ({len(relevant)} python-relevant) → {inv_path.name}")

    # ── Collect all episodes to process ───────────────────────────────────
    all_episodes = []
    for ch_key, ch_data in sources.items():
        if not isinstance(ch_data, dict) or "episodes" not in ch_data:
            continue
        for ep in ch_data["episodes"]:
            ep["_channel"] = ch_key
            all_episodes.append(ep)

    # Filter by single ID if requested
    if args.id:
        all_episodes = [ep for ep in all_episodes if ep.get("id") == args.id]
        if not all_episodes:
            print(f"No episode found with id={args.id}")
            sys.exit(1)

    print(f"\n=== Fetching transcripts for {len(all_episodes)} episodes ===")

    updated = 0
    for ep in all_episodes:
        vid_id = ep.get("id", "")
        title = ep.get("title", "")
        out_path = TRANSCRIPTS_DIR / f"{vid_id}.txt"

        # Skip already downloaded
        if out_path.exists():
            print(f"  ⏭  {vid_id}: already downloaded")
            ep["transcript_status"] = "done"
            continue

        if args.dry_run:
            print(f"  [dry-run] Would fetch: {vid_id} — {title[:60]}")
            continue

        text = fetch_transcript(vid_id, title)
        if text:
            # Write with metadata header
            header = (
                f"# {title}\n"
                f"# Video ID: {vid_id}\n"
                f"# Channel: {ep.get('_channel','')}\n"
                f"# URL: https://www.youtube.com/watch?v={vid_id}\n"
                f"# Topics: {', '.join(ep.get('topics', []))}\n"
                f"# Relevance: {ep.get('relevance','')}\n"
                f"# Notes: {ep.get('notes','')}\n"
                f"{'='*80}\n\n"
            )
            out_path.write_text(header + text, encoding="utf-8")
            ep["transcript_status"] = "done"
            updated += 1
        else:
            ep["transcript_status"] = "failed"

        time.sleep(0.5)  # be polite

    # ── Save updated sources.json ──────────────────────────────────────────
    if updated > 0 and not args.dry_run:
        with open(SOURCES_FILE, "w") as f:
            json.dump(sources, f, indent=2, ensure_ascii=False)
        print(f"\n✅ {updated} transcripts downloaded → docs/transcripts/")
        print(f"   Updated {SOURCES_FILE.name}")
    elif not args.dry_run:
        print("\n No new transcripts (all already done or failed)")

    print("\nNext step:")
    print("  python scripts/extract_patterns.py   # extract API patterns from transcripts")


if __name__ == "__main__":
    main()
