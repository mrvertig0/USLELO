#!/bin/bash
# Run the USL2 Elo data pipeline locally and push the results to GitHub.
#
# This exists because Sofascore's API blocks GitHub Actions' IP ranges,
# so the fetch has to happen from a normal residential connection --
# i.e. this computer -- instead of in the cloud. Run this manually
# whenever you want fresh ratings, or schedule it with cron (see
# README.md) to run automatically once a day.
#
# Usage (from anywhere):
#   ./scripts/run_update.sh

set -euo pipefail

# Move to the repo root (parent of this script's folder), regardless of
# where this was launched from -- important for cron, which runs with a
# minimal environment and an unpredictable working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

echo "== USL2 Elo update: $(date) =="

echo "-- Pulling latest repo state --"
git pull --ff-only

echo "-- Fetching match data --"
python3 scripts/fetch_data.py

echo "-- Computing Elo ratings --"
python3 scripts/compute_elo.py

echo "-- Checking for changes --"
git add data docs/data

if git diff --cached --quiet -- data docs/data; then
    echo "No changes -- ratings are already up to date."
else
    git commit -m "Update ratings [local]"
    echo "-- Pushing to GitHub --"
    git push
    echo "Done -- GitHub Pages will republish automatically."
fi
