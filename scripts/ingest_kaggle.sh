#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -d "$1" ]]; then
  echo "Usage: $0 <directory-containing-Kaggle-extracted-files>" >&2
  exit 2
fi

command -v hdfs >/dev/null 2>&1 || {
  echo "hdfs command not found; configure Hadoop on this host first." >&2
  exit 1
}

source_dir=$(cd "$1" && pwd)
raw_dir=${HDFS_RAW_DIR:-/youtube/raw}
shopt -s nullglob
csv_files=("$source_dir"/*videos.csv)
category_files=("$source_dir"/*_category_id.json)

if [[ ${#csv_files[@]} -eq 0 ]]; then
  echo "No regional *videos.csv files found in $source_dir" >&2
  exit 1
fi
if [[ ${#category_files[@]} -eq 0 ]]; then
  echo "No regional *_category_id.json files found in $source_dir" >&2
  exit 1
fi

for file in "${csv_files[@]}"; do
  name=$(basename "$file")
  if [[ ! "$name" =~ ^(US|CA|GB|DE|FR|IN|JP|KR|MX|RU)videos\.csv$ || ! -s "$file" ]]; then
    echo "Unexpected or empty regional CSV: $file" >&2
    exit 1
  fi
  country=${name%videos.csv}
  if [[ ! -s "$source_dir/${country}_category_id.json" ]]; then
    echo "Missing or empty category metadata for region $country" >&2
    exit 1
  fi
done

hdfs dfs -mkdir -p "$raw_dir"
for file in "${csv_files[@]}" "${category_files[@]}"; do
  [[ -s "$file" ]] || {
    echo "Empty category metadata file: $file" >&2
    exit 1
  }
  hdfs dfs -put -f "$file" "$raw_dir/"
  echo "Uploaded $(basename "$file") to $raw_dir"
done

echo "Ingested ${#csv_files[@]} regional CSV file(s). Verify with: hdfs dfs -ls $raw_dir"
