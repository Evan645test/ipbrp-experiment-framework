#!/bin/zsh
set -euo pipefail
entry_dir="${0:A:h}"
reader_dir="$entry_dir/論文逐段精讀器"
node_bin="$(command -v node || true)"
if [[ -z "$node_bin" ]]; then
  for candidate in "$HOME"/.nvm/versions/node/*/bin/node(NOn) /opt/homebrew/bin/node /usr/local/bin/node; do
    if [[ -x "$candidate" ]]; then
      node_bin="$candidate"
      break
    fi
  done
fi
if [[ -z "$node_bin" ]]; then
  print '找不到 Node.js。請先安裝 Node.js 22.13 以上版本，再重新開啟。'
  read 'reply?按 Enter 關閉。'
  exit 1
fi
if ! "$node_bin" "$reader_dir/scripts/open-reader.mjs"; then
  read 'reply?按 Enter 關閉。'
  exit 1
fi
