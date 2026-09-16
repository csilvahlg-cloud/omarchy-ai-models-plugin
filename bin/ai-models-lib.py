#!/usr/bin/env python3
"""ai-models-lib.py — JSON/model logic for ai-models-ctl (called as subprocess).
Usage:
  ai-models-lib.py ensure-config <config_path> <llama_server_bin>
  ai-models-lib.py list <config_path> <running_ollama_names_newline_separated> <state_dir>
  ai-models-lib.py get-entry <config_path> <id>
"""
import glob
import json
import os
import subprocess
import sys


def ensure_config(cfg_path, llama_bin):
    # Always rescan so newly downloaded / deleted models show up in the panel
    # automatically. Existing entries are kept by id (preserves any manual
    # tweaks like extraArgs); missing ones are dropped, new ones added.
    prev = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path) as f:
                for e in json.load(f).get("models", []):
                    prev[e.get("id")] = e
        except Exception:
            prev = {}
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    entries = []

    try:
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        for line in res.stdout.splitlines()[1:]:
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            eid = "ollama:" + name
            entries.append(prev.get(eid) or {
                "id": eid,
                "name": name,
                "kind": "ollama",
                "model": name,
            })
    except Exception:
        pass

    skip_markers = ("ggml-vocab-", "mmproj-", "mtp-")
    seen_paths = set()
    search_globs = [
        os.path.expanduser("~/.cache/huggingface/hub/models--*/snapshots/*/*.gguf"),
        os.path.expanduser("~/.unsloth/studio/cache/ollama_links/*/*/*.gguf"),
    ]
    # Single shared port: only one raw GGUF model runs at a time; use llama.cpp's default.
    port = 8080
    for pattern in search_globs:
        for path in sorted(glob.glob(pattern)):
            base = os.path.basename(path)
            base_lower = base.lower()
            if any(m in base_lower for m in skip_markers) or "mmproj" in base_lower or "-mtp" in base_lower:
                continue
            real = os.path.realpath(path)
            if not os.path.exists(real):
                # Broken symlink (e.g. Unsloth Studio link to a deleted
                # Ollama blob) — not a usable model, skip it.
                continue
            if real in seen_paths:
                continue
            seen_paths.add(real)
            label = base.replace(".gguf", "")
            eid = "gguf:" + label
            entries.append(prev.get(eid) or {
                "id": eid,
                "name": label,
                "kind": "llama-server",
                "path": path,
                "port": port,
                "extraArgs": ["-c", "8192"],
            })

    if set(prev.keys()) != {e["id"] for e in entries} or not os.path.exists(cfg_path):
        with open(cfg_path, "w") as f:
            json.dump({"models": entries}, f, indent=2)
        print(f"Updated {cfg_path} with {len(entries)} model(s)", file=sys.stderr)


def safe_id(model_id):
    return model_id.replace("/", "_").replace(":", "_")


def gguf_running(model_id, state_dir):
    pidfile = os.path.join(state_dir, safe_id(model_id) + ".pid")
    if not os.path.exists(pidfile):
        return False
    try:
        pid = int(open(pidfile).read().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def cmd_list(cfg_path, running_raw, state_dir):
    running = set(l for l in running_raw.splitlines() if l)
    cfg = json.load(open(cfg_path))
    out = []
    for m in cfg.get("models", []):
        entry = dict(m)
        if m["kind"] == "ollama":
            entry["status"] = "running" if m["model"] in running else "stopped"
            entry["detail"] = "Ollama"
        else:
            entry["status"] = "running" if gguf_running(m["id"], state_dir) else "stopped"
            entry["detail"] = "GGUF - port " + str(m.get("port", ""))
        out.append(entry)
    print(json.dumps(out))


def cmd_get_entry(cfg_path, model_id):
    cfg = json.load(open(cfg_path))
    for m in cfg.get("models", []):
        if m["id"] == model_id:
            print(json.dumps(m))
            return
    print("")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit("missing subcommand")
    sub = args[0]
    if sub == "ensure-config":
        ensure_config(args[1], args[2])
    elif sub == "list":
        cmd_list(args[1], args[2], args[3])
    elif sub == "get-entry":
        cmd_get_entry(args[1], args[2])
    else:
        sys.exit(f"unknown subcommand {sub}")


if __name__ == "__main__":
    main()
