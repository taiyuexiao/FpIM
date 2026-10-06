#!/usr/bin/env bash
# 把当前工作区发布到 GitHub（Public 仓库只允许单条干净提交）。
# ⚠️ 本地完整历史含旧环境口令，禁止直接 `git push` 本地分支——会覆盖远端并泄露历史。
# 用法：./scripts/publish-github.sh ["提交信息"]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d /tmp/fpim-publish.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

git clone --no-hardlinks -q "$ROOT" "$TMP/repo"
cd "$TMP/repo"
git checkout --orphan release -q
git add -A
git commit -q -m "${1:-chore: 发布快照 $(date +%F)}"
git branch -M main
git remote set-url origin https://github.com/taiyuexiao/FpIM.git
git push -f origin main
echo "已发布：https://github.com/taiyuexiao/FpIM （单提交快照）"
