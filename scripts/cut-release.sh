#!/usr/bin/env bash
#
# cut-release.sh — orchestrate a SemVer release for this repo.
#
# Usage:
#     ./scripts/cut-release.sh vX.Y.Z [--dry-run]
#
# What it does (in order):
#     1. Validate semver argument and dirty tree.
#     2. Validate CHANGELOG [Unreleased] has non-whitespace content.
#     3. Edit CHANGELOG: [Unreleased] → [X.Y.Z] — YYYY-MM-DD + fresh [Unreleased].
#     4. Edit version anchor (pyproject.toml or VERSION, whichever exists).
#     5. Stage + commit with CUT_RELEASE_VERSION=X.Y.Z so the
#        changelog_tag_sync invariant tolerates the transient drift at
#        pre-commit time.
#     6. Create annotated tag vX.Y.Z.
#     7. Push main + tag.
#     8. Create a GitHub Release with notes extracted from that CHANGELOG
#        section.
#
# --dry-run: run steps 1–4 in a fresh tmp worktree, show the diff, and
# exit without touching the real repo. Useful for validating format.
#
# The ecosystem convention is to keep this script byte-identical across
# fpt-mcp / maya-mcp / flame-mcp / vision3d. Canonical source:
# ~/Projects/cut-release-canonical.sh. Propagate on change.
#
set -euo pipefail

# --------------------------------------------------------------------------- #
# Usage / arg parsing
# --------------------------------------------------------------------------- #

usage() {
    cat <<EOF
Usage: $(basename "$0") vX.Y.Z [--dry-run]

Cut a SemVer release. Edits CHANGELOG + version anchor, commits, tags,
pushes, and creates a GitHub Release.

Options:
    --dry-run    Show what would change but do not commit/tag/push.
    -h, --help   This message.
EOF
}

DRY_RUN=0
VERSION_ARG=""

for arg in "$@"; do
    case "$arg" in
        -h|--help) usage; exit 0 ;;
        --dry-run) DRY_RUN=1 ;;
        v[0-9]*.[0-9]*.[0-9]*) VERSION_ARG="$arg" ;;
        [0-9]*.[0-9]*.[0-9]*)  VERSION_ARG="v$arg" ;;
        *) echo "error: unknown argument: $arg" >&2; usage; exit 2 ;;
    esac
done

if [[ -z "$VERSION_ARG" ]]; then
    echo "error: missing vX.Y.Z argument" >&2
    usage
    exit 2
fi

TAG="$VERSION_ARG"
VERSION="${TAG#v}"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "error: version must match vX.Y.Z (got: $TAG)" >&2
    exit 2
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
    echo "error: not inside a git repository" >&2
    exit 2
fi
cd "$REPO_ROOT"

# --------------------------------------------------------------------------- #
# Pre-flight checks
# --------------------------------------------------------------------------- #

# Tree must be clean (dry-run still requires this so the preview is honest).
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "error: working tree has uncommitted changes — commit or stash first" >&2
    exit 1
fi

# Tag must not already exist.
if git rev-parse --verify "refs/tags/$TAG" >/dev/null 2>&1; then
    echo "error: tag $TAG already exists" >&2
    exit 1
fi

# CHANGELOG must exist with an [Unreleased] section carrying real content.
CHANGELOG="CHANGELOG.md"
if [[ ! -f "$CHANGELOG" ]]; then
    echo "error: $CHANGELOG not found at repo root" >&2
    exit 1
fi

# Extract the Unreleased block (lines after "## [Unreleased]" up to next "## [").
UNREL_BODY="$(awk '
    /^## \[Unreleased\]/ { inblock=1; next }
    inblock && /^## \[/ { exit }
    inblock { print }
' "$CHANGELOG" | sed '/^[[:space:]]*$/d' || true)"

if [[ -z "$UNREL_BODY" ]]; then
    echo "error: [Unreleased] section in $CHANGELOG is empty — nothing to release" >&2
    exit 1
fi

# Determine version anchor: pyproject.toml first, then VERSION file.
ANCHOR_FILE=""
ANCHOR_KIND=""
if [[ -f "pyproject.toml" ]] && grep -qE '^version\s*=\s*"[^"]+"' pyproject.toml; then
    ANCHOR_FILE="pyproject.toml"
    ANCHOR_KIND="pyproject"
elif [[ -f "VERSION" ]]; then
    ANCHOR_FILE="VERSION"
    ANCHOR_KIND="version_file"
else
    echo "warn: no version anchor (pyproject.toml or VERSION) found — skipping anchor bump" >&2
fi

TODAY="$(date +%Y-%m-%d)"

echo "cut-release: $TAG (anchor=${ANCHOR_FILE:-none}, dry-run=$DRY_RUN)"

# --------------------------------------------------------------------------- #
# Edits (done to the working tree; reverted if dry-run)
# --------------------------------------------------------------------------- #

TMP_CHANGELOG="$(mktemp)"
trap 'rm -f "$TMP_CHANGELOG"' EXIT

# Replace `## [Unreleased]` with:
#   ## [Unreleased]
#
#   ## [X.Y.Z] — YYYY-MM-DD
# Portable across BSD/GNU awk.
awk -v ver="$VERSION" -v today="$TODAY" '
    /^## \[Unreleased\]/ && !seen {
        print
        print ""
        print "## [" ver "] — " today
        seen=1
        next
    }
    { print }
' "$CHANGELOG" > "$TMP_CHANGELOG"

cp "$TMP_CHANGELOG" "$CHANGELOG"

# Bump anchor
if [[ "$ANCHOR_KIND" == "pyproject" ]]; then
    # Portable in-place sed: BSD requires `-i ''`, GNU accepts `-i`.
    if sed --version >/dev/null 2>&1; then
        sed -i "s/^version = \"[^\"]*\"/version = \"$VERSION\"/" pyproject.toml
    else
        sed -i '' "s/^version = \"[^\"]*\"/version = \"$VERSION\"/" pyproject.toml
    fi
elif [[ "$ANCHOR_KIND" == "version_file" ]]; then
    echo "$VERSION" > VERSION
fi

# Show diff
echo
echo "--- pending changes ---"
git --no-pager diff --stat
echo
git --no-pager diff "$CHANGELOG" "${ANCHOR_FILE:-/dev/null}" | head -80
echo "--- end diff ---"
echo

if (( DRY_RUN )); then
    echo "[dry-run] reverting working tree changes"
    git checkout -- "$CHANGELOG" ${ANCHOR_FILE:+"$ANCHOR_FILE"}
    echo "[dry-run] done — nothing committed or pushed"
    exit 0
fi

# --------------------------------------------------------------------------- #
# Commit + tag + push + release
# --------------------------------------------------------------------------- #

# Stage
git add "$CHANGELOG"
[[ -n "$ANCHOR_FILE" ]] && git add "$ANCHOR_FILE"

# Commit with CUT_RELEASE_VERSION so the changelog_tag_sync invariant
# tolerates the transient "CHANGELOG ahead of tag" state.
CUT_RELEASE_VERSION="$VERSION" git commit -m "chore(release): cut $TAG"

# Tag the new commit.
git tag -a "$TAG" -m "Release $TAG"

# Push main + tag. Parent branch is whatever HEAD is on (assumed `main`).
BRANCH="$(git branch --show-current)"
git push origin "$BRANCH"
git push origin "$TAG"

# GitHub release notes = the CHANGELOG section for this version.
NOTES_FILE="$(mktemp)"
trap 'rm -f "$TMP_CHANGELOG" "$NOTES_FILE"' EXIT

awk -v ver="$VERSION" '
    $0 ~ ("^## \\[" ver "\\]") { inblock=1; next }
    inblock && /^## \[/ { exit }
    inblock { print }
' "$CHANGELOG" > "$NOTES_FILE"

if [[ -s "$NOTES_FILE" ]]; then
    gh release create "$TAG" --title "$TAG" --notes-file "$NOTES_FILE"
else
    gh release create "$TAG" --title "$TAG" --notes "Release $TAG"
fi

echo "cut-release: $TAG committed, tagged, pushed, and released."
