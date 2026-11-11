#!/usr/bin/env bash
set -euo pipefail

command -v hdfs >/dev/null 2>&1 || {
  echo "hdfs command not found; configure Hadoop on this host first." >&2
  exit 1
}
command -v yarn >/dev/null 2>&1 || {
  echo "yarn command not found; configure Hadoop/YARN on this host first." >&2
  exit 1
}

echo "=== HDFS live/dead DataNodes ==="
hdfs dfsadmin -report
echo
echo "=== YARN NodeManagers ==="
yarn node -list
