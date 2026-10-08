#!/usr/bin/env bash
# Render build: install slim deps, fetch the large datasets, then build the
# SQLite database, the embedding model cache and the vector index.
set -euo pipefail

pip install -r requirements-render.txt

fetch() {
  local url="$1" dest="$2"
  if [ -f "$dest" ]; then return; fi
  if [ -z "$url" ]; then
    echo "ERROR: $dest is missing and no download URL was set." >&2
    echo "Set INSTITUTION_CSV_URL / FIELD_CSV_URL in the Render environment." >&2
    exit 1
  fi
  curl -fL --retry 3 -o "$dest" "$url"
}

fetch "${INSTITUTION_CSV_URL:-}" dataset/Most-Recent-Cohorts-Institution.csv
fetch "${FIELD_CSV_URL:-}" dataset/Most-Recent-Cohorts-Field-of-Study.csv

python -m src.database_setup
python -m src.vector_store

# The big CSVs are only needed to build the database; drop them from the image.
rm -f dataset/Most-Recent-Cohorts-Institution.csv \
      dataset/Most-Recent-Cohorts-Field-of-Study.csv
