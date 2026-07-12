#!/usr/bin/env bash
set -euo pipefail

echo "Preparing local data folders..."
mkdir -p data/raw data/processed data/manifests data/sample_images

cat <<'EOF'
Data folders are ready.

Place public, synthetic, or anonymized documents in:
  data/raw/

After preprocessing, write cleaned files to:
  data/processed/

Create JSONL manifests in:
  data/manifests/

Large datasets and private documents must not be committed to Git.
See the root README.md for manifest format and split policy.
EOF
