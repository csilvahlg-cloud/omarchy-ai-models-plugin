#!/usr/bin/env bash
# install.sh — installs the AI Models plugin for Omarchy Linux (Hyprland shell)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ID="user.ai-models"
PLUGIN_DIR="$HOME/.config/omarchy/plugins/$PLUGIN_ID"
BIN_DIR="$HOME/.local/bin"

echo "==> Installing AI Models Omarchy plugin"

mkdir -p "$PLUGIN_DIR" "$BIN_DIR"

cp "$SCRIPT_DIR/plugin/manifest.json" "$PLUGIN_DIR/manifest.json"
cp "$SCRIPT_DIR/plugin/Panel.qml" "$PLUGIN_DIR/Panel.qml"
cp "$SCRIPT_DIR/bin/ai-models-ctl" "$BIN_DIR/ai-models-ctl"
cp "$SCRIPT_DIR/bin/ai-models-lib.py" "$BIN_DIR/ai-models-lib.py"
chmod +x "$BIN_DIR/ai-models-ctl" "$BIN_DIR/ai-models-lib.py"

echo "==> Validating plugin manifest"
if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin validate "$PLUGIN_DIR" && echo "    validate: OK"
else
  echo "    'omarchy' CLI not found in PATH — skipping validation (fine if you're not on Omarchy yet)"
fi

echo "==> Registering bar widget in shell.json"
python3 - "$HOME/.config/omarchy/shell.json" "$PLUGIN_ID" <<'PYEOF'
import json, os, sys

path, plugin_id = sys.argv[1], sys.argv[2]
if not os.path.exists(path):
    print(f"    {path} not found yet — Omarchy will create it on first run.")
    print(f"    Add {{\"id\": \"{plugin_id}\"}} to bar.layout.right manually, or just run:")
    print(f"    omarchy plugin enable {plugin_id}")
    sys.exit(0)

with open(path) as f:
    data = json.load(f)

right = data.setdefault("bar", {}).setdefault("layout", {}).setdefault("right", [])
if not any(e.get("id") == plugin_id for e in right):
    idx = next((i for i, e in enumerate(right) if e.get("id") == "omarchy.agents"), len(right) - 1)
    right.insert(idx + 1, {"id": plugin_id})
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print("    added to bar.layout.right")
else:
    print("    already present in bar.layout.right")
PYEOF

echo "==> Rescanning plugins (if omarchy-shell is running)"
if command -v omarchy-shell >/dev/null 2>&1; then
  omarchy-shell shell rescanPlugins 2>/dev/null || echo "    omarchy-shell not running — it will pick up the plugin on next login"
fi

echo ""
echo "Done. If your Hyprland session was already running, log out/in (or run"
echo "  omarchy-shell shell rescanPlugins && omarchy plugin enable $PLUGIN_ID"
echo "inside the session) to see the icon in the bar."
