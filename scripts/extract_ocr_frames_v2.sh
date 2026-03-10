#!/bin/zsh
# extract_ocr_frames_v2.sh
# Segunda ronda de extracción OCR — 3 videos HIGH priority + 1 MEDIUM
# Ejecutar desde Mac con: zsh scripts/extract_ocr_frames_v2.sh
#
# Videos objetivo:
#   hPa1OVEY_78  — Python Scripting: OpenClip and Watch Folders  (~11 min)
#   ZDHntCBBRXM  — Python Scripting: Batch Iteration and Render Naming  (~16 min)
#   lMRidruJDqA  — Adding Custom Menu Actions  (~10 min)
#   VJFgxnCqrE0  — Working with Python Scripting  (~16 min)
#
# Requisitos: yt-dlp, ffmpeg instalados en Mac

setopt NULL_GLOB

SCRIPT_DIR="${0:A:h}"
PROJECT_DIR="${SCRIPT_DIR}/.."
OCR_DIR="${PROJECT_DIR}/docs/ocr_frames"
TEMP_DIR="/tmp/flame_ocr_v2"

mkdir -p "$TEMP_DIR"
mkdir -p "$OCR_DIR"

echo "=== Flame OCR Frame Extraction v2 ==="
echo "Output dir: $OCR_DIR"
echo ""

extract_video() {
    local VID_ID="$1"
    local TIMESTAMPS="$2"
    local OUT_DIR="${OCR_DIR}/${VID_ID}"

    echo "--- Processing: ${VID_ID} ---"

    # Skip if all frames already exist
    local existing_count=$(ls "${OUT_DIR}"/frame_*.jpg 2>/dev/null | wc -l | tr -d ' ')
    if [[ $existing_count -gt 0 ]]; then
        echo "  Already has ${existing_count} frames — skipping download (delete dir to re-extract)"
        return
    fi

    mkdir -p "$OUT_DIR"

    local TEMP_BASE="${TEMP_DIR}/${VID_ID}"
    local VIDEO_URL="https://www.youtube.com/watch?v=${VID_ID}"

    echo "  Downloading: ${VIDEO_URL}"
    yt-dlp \
        --format "bestvideo[height<=480]+bestaudio/best[height<=480]" \
        --merge-output-format mp4 \
        --output "${TEMP_BASE}.%(ext)s" \
        --no-playlist \
        "$VIDEO_URL" 2>&1 | tail -3

    # Detect downloaded file (yt-dlp may choose .mp4, .mkv, .webm)
    local TEMP_VIDEO
    TEMP_VIDEO=$(ls "${TEMP_BASE}".*[^t](N) 2>/dev/null | head -1)

    if [[ -z "$TEMP_VIDEO" ]]; then
        # Try with .part suffix removed
        TEMP_VIDEO=$(ls "${TEMP_BASE}".*(N) 2>/dev/null | head -1)
    fi

    if [[ -z "$TEMP_VIDEO" ]]; then
        echo "  ERROR: Download failed for ${VID_ID}"
        return 1
    fi

    echo "  Video: $TEMP_VIDEO"
    echo "  Extracting frames at: $TIMESTAMPS"

    local extracted=0
    for TS in ${=TIMESTAMPS}; do
        local OUT_FRAME="${OUT_DIR}/frame_${TS}s.jpg"
        ffmpeg -ss "$TS" -i "$TEMP_VIDEO" \
               -frames:v 1 -q:v 2 \
               "$OUT_FRAME" -y -loglevel error
        if [[ -f "$OUT_FRAME" ]]; then
            (( extracted++ ))
        else
            echo "  WARN: No frame at ${TS}s (beyond video length?)"
        fi
    done

    echo "  Extracted: ${extracted} frames"

    # Clean up temp video to save disk space
    rm -f "$TEMP_VIDEO"
    echo "  Temp video removed."
    echo ""
}

# -----------------------------------------------------------------------
# hPa1OVEY_78 — OpenClip and Watch Folders
# Key moments: terminal commands (mkdir, cd, python husky.py), watch folder
# monitoring, OpenClip creation in Flame, version update workflow
# -----------------------------------------------------------------------
extract_video "hPa1OVEY_78" "51 115 161 238 315 407 455 548 618"

# -----------------------------------------------------------------------
# ZDHntCBBRXM — Batch Iteration and Render Naming
# Key moments: batch_hook.py listing, naming_conventions.py script,
# DL_PYTHON_HOOK_PATH setup, batch iteration name hook, render node
# name hook, verifying naming in Flame UI
# -----------------------------------------------------------------------
extract_video "ZDHntCBBRXM" "72 142 257 340 388 435 537 604 707 755 832 921"

# -----------------------------------------------------------------------
# lMRidruJDqA — Adding Custom Menu Actions
# Key moments: /opt/Autodesk/shared/python directory, script structure
# (3 sections), hook definitions, scope/execute pattern, DL_PYTHON_HOOK_PATH,
# Python hook path options per-version/per-project/per-user
# -----------------------------------------------------------------------
extract_video "lMRidruJDqA" "25 78 124 190 247 298 345 391 464 530 604"

# -----------------------------------------------------------------------
# VJFgxnCqrE0 — Working with Python Scripting (Flame 2018 overview)
# Key moments: hook API overview, new hooks in 2018.2, code examples
# -----------------------------------------------------------------------
extract_video "VJFgxnCqrE0" "28 75 121 168 257 381 434 512 558 674 925 972"

# -----------------------------------------------------------------------
echo "=== Done ==="
echo ""
echo "Total frames:"
ls "${OCR_DIR}"/**/*.jpg 2>/dev/null | wc -l

echo ""
echo "Per video:"
for vid in hPa1OVEY_78 ZDHntCBBRXM lMRidruJDqA VJFgxnCqrE0; do
    count=$(ls "${OCR_DIR}/${vid}"/frame_*.jpg 2>/dev/null | wc -l | tr -d ' ')
    echo "  ${vid}: ${count} frames"
done
