#!/bin/zsh
# flame-mcp — OCR Frame Extraction Script
# cd ~/Projects/flame-mcp && ./scripts/extract_ocr_frames.sh

setopt NULL_GLOB  # evita error cuando *.jpg no tiene matches

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/docs/ocr_frames"
TEMP_DIR="/tmp/flame_mcp_ocr"

mkdir -p "$OUTPUT_DIR"
mkdir -p "$TEMP_DIR"

echo "=== flame-mcp OCR Frame Extractor ==="
echo "Output: $OUTPUT_DIR"
echo ""

extract_video() {
    local VID_ID="$1"
    local TIMESTAMPS="$2"

    echo "--- $VID_ID ---"
    local VID_DIR="$OUTPUT_DIR/$VID_ID"
    mkdir -p "$VID_DIR"

    local TEMP_BASE="$TEMP_DIR/${VID_ID}"
    local TEMP_VIDEO
    TEMP_VIDEO=$(ls "${TEMP_BASE}".*(N) 2>/dev/null | head -1)

    if [[ -z "$TEMP_VIDEO" ]]; then
        echo "  Downloading $VID_ID (480p)..."
        yt-dlp \
            -f "best[height<=480]/bestvideo[height<=480]+bestaudio/best" \
            --merge-output-format mp4 \
            --no-playlist \
            -o "${TEMP_BASE}.%(ext)s" \
            "https://www.youtube.com/watch?v=$VID_ID"
        TEMP_VIDEO=$(ls "${TEMP_BASE}".*(N) 2>/dev/null | head -1)
    else
        echo "  Ya descargado: $TEMP_VIDEO"
    fi

    if [[ -z "$TEMP_VIDEO" ]]; then
        echo "  ERROR: descarga fallida para $VID_ID"
        return
    fi

    echo "  Video: $TEMP_VIDEO"
    echo "  Extrayendo frames..."

    # ${=TIMESTAMPS} fuerza word-split en zsh
    for TS in ${=TIMESTAMPS}; do
        local OUT_FRAME="$VID_DIR/frame_${TS}s.jpg"
        if [[ ! -f "$OUT_FRAME" ]]; then
            ffmpeg -ss "$TS" -i "$TEMP_VIDEO" \
                -frames:v 1 -q:v 1 \
                "$OUT_FRAME" -y 2>/dev/null \
                && echo "    frame_${TS}s.jpg ok" \
                || echo "    frame_${TS}s.jpg FAILED"
        else
            echo "    frame_${TS}s.jpg ya existe"
        fi
    done

    local COUNT=${#${:-$VID_DIR/*.jpg}[@]}
    COUNT=$(ls "$VID_DIR"/*.jpg 2>/dev/null | wc -l | tr -d ' ')
    echo "  Done: $COUNT frames → $VID_DIR"
    echo ""
}

extract_video "jfxJYUnWIjY" "1034 2186 2856 3413 3795 3860 5373 5460"
extract_video "wTRwYyXTosk" "434 526 591 773 2143 2369 2934 3121"
extract_video "GA0ipgNXhnI" "721 982 1400 1882 1991 2526 3852 4256"
extract_video "0SpDr3tMdPI" "591 1069 1139 1252 1347 1439 2117 3882"
extract_video "e2ob2gNoea8" "39 113 178 243 326 391 469 530"
extract_video "ewKoYXkqEXA" "21 86 360"

echo "=== Todo listo ==="
TOTAL=$(ls "$OUTPUT_DIR"/**/*.jpg(N) 2>/dev/null | wc -l | tr -d ' ')
echo "Total frames: $TOTAL"
echo "Carpeta: $OUTPUT_DIR"
