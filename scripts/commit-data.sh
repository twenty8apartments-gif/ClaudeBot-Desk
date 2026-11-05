#!/usr/bin/env bash
# Commit changed data/ files and push, retrying if another bot pushed first.
set -euo pipefail
msg="${1:-Update data}"
git config user.name "claudebot-desk[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add data/
if git diff --cached --quiet; then echo "No data changes."; exit 0; fi
git commit -q -m "$msg"
for i in 1 2 3 4 5; do
  if git push -q; then echo "Pushed."; exit 0; fi
  echo "Push rejected, rebasing (attempt $i)"; sleep $((i * 3))
  git pull -q --rebase -X theirs origin main || { git rebase --abort; git pull -q --no-rebase -X ours origin main; }
done
echo "Could not push after 5 attempts" >&2; exit 1
