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
import sqlite3
import subprocess
import sys
import urllib.parse

STUDIO_DB = os.path.expanduser("~/.unsloth/studio/studio.db")
# Fallback used only when Unsloth Studio has no tuned value for a model
# (no studio.db, no matching entry). Verified safe on a 15GB-RAM machine
# for models up to ~21GB on disk — see the plugin README for numbers.
DEFAULT_CONTEXT = 124000
DEFAULT_KV_CACHE_DTYPE = "q8_0"


def _load_json_setting(cur, table, key):
    try:
        cur.execute(f"SELECT value_json FROM {table} WHERE key = ?", (key,))
        row = cur.fetchone()
        return json.loads(row[0]) if row else None
    except Exception:
        return None


def load_studio_tuning():
    """Read the user's own per-model context/KV-cache tuning straight out of
    Unsloth Studio's sqlite DB, so the bar plugin always mirrors whatever is
    dialed in there instead of drifting out of sync. Returns
    (variant_overrides, repo_default_ctx, ollama_overrides) — all possibly
    empty dicts if the DB is missing/unreadable (fresh install, Studio never
    run, etc.). ollama_overrides maps 'name:tag' (as shown by `ollama list`)
    -> {custom_context_length, kv_cache_dtype}."""
    variant_overrides, repo_default_ctx, ollama_overrides = {}, {}, {}
    if not os.path.exists(STUDIO_DB):
        return variant_overrides, repo_default_ctx, ollama_overrides
    try:
        con = sqlite3.connect(f"file:{STUDIO_DB}?mode=ro", uri=True, timeout=2)
        cur = con.cursor()
        # variant_overrides: "author/repo:VARIANT" -> {custom_context_length, kv_cache_dtype, ...}
        # ollama entries share the same setting, keyed "ollama-manifest:<urlencoded manifest path>[:tag]"
        overrides = _load_json_setting(cur, "app_settings", "openai_api_auto_switch_overrides") or {}
        for key, val in overrides.items():
            if not (isinstance(val, dict) and val.get("custom_context_length")):
                continue
            if key.startswith("ollama-manifest:"):
                name_tag = _ollama_name_tag_from_studio_key(key)
                if name_tag:
                    ollama_overrides[name_tag] = val
            else:
                variant_overrides[key] = val
        # repo_default_ctx: "author/repo" -> maxTokens (used when no variant-specific override exists)
        params_by_model = _load_json_setting(cur, "chat_settings", "inferenceParamsByModel") or {}
        for repo_key, val in params_by_model.items():
            if isinstance(val, dict) and val.get("maxTokens"):
                repo_default_ctx[repo_key] = val["maxTokens"]
        con.close()
    except Exception:
        return {}, {}, {}
    return variant_overrides, repo_default_ctx, ollama_overrides


def _repo_from_hf_cache_path(path):
    """'.../models--unsloth--gemma-4-26B-A4B-it-qat-GGUF/snapshots/...' -> 'unsloth/gemma-4-26B-A4B-it-qat-GGUF'"""
    for part in path.split(os.sep):
        if part.startswith("models--"):
            pieces = part[len("models--"):].split("--", 1)
            if len(pieces) == 2:
                return f"{pieces[0]}/{pieces[1]}"
    return None


def _ollama_name_tag_from_studio_key(key):
    """'ollama-manifest:%2fusr%2f.../library/qwen3.6/27b[:27b]' -> 'qwen3.6:27b'.
    Studio derives the manifest path from Ollama's own on-disk layout
    (.../manifests/registry.ollama.ai/library/<name>/<tag>); `ollama list`
    shows the same pair as 'name:tag', which is what we need to match against."""
    manifest_part = key[len("ollama-manifest:"):]
    manifest_part = manifest_part.split(":", 1)[0]  # drop an optional trailing ":tag" studio sometimes appends
    decoded = urllib.parse.unquote(manifest_part)
    marker = "/library/"
    idx = decoded.find(marker)
    if idx == -1:
        return None
    tail = decoded[idx + len(marker):].strip("/").split("/")
    if len(tail) < 2:
        return None
    return f"{tail[0]}:{tail[1]}"


def studio_extra_args_for_gguf(path, filename_stem, variant_overrides, repo_default_ctx):
    """Match this GGUF file against the user's Studio tuning. Variant-specific
    overrides win (matched by the variant token, e.g. 'UD-Q4_K_XL', appearing
    in the filename); otherwise fall back to the repo-level maxTokens; otherwise
    the plugin default. -fa on is mandatory whenever -ctk/-ctv are quantized."""
    repo = _repo_from_hf_cache_path(path)
    context = None
    kv_dtype = DEFAULT_KV_CACHE_DTYPE
    if repo:
        for key, val in variant_overrides.items():
            if not key.startswith(repo + ":"):
                continue
            variant = key.split(":", 1)[1]
            if variant and variant in filename_stem:
                context = int(val["custom_context_length"])
                kv_dtype = val.get("kv_cache_dtype", DEFAULT_KV_CACHE_DTYPE)
                break
        if context is None and repo in repo_default_ctx:
            context = int(repo_default_ctx[repo])
    if context is None:
        context = DEFAULT_CONTEXT
    return ["-c", str(context), "-fa", "on", "-ctk", kv_dtype, "-ctv", kv_dtype]


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
    variant_overrides, repo_default_ctx, ollama_overrides = load_studio_tuning()

    try:
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        for line in res.stdout.splitlines()[1:]:
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            eid = "ollama:" + name
            existing = prev.get(eid)
            if existing:
                entries.append(existing)
                continue
            entry = {
                "id": eid,
                "name": name,
                "kind": "ollama",
                "model": name,
            }
            tuned = ollama_overrides.get(name)
            if tuned:
                entry["numCtx"] = int(tuned["custom_context_length"])
            entries.append(entry)
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
            existing = prev.get(eid)
            if existing:
                entries.append(existing)
                continue
            entries.append({
                "id": eid,
                "name": label,
                "kind": "llama-server",
                "path": path,
                "port": port,
                "extraArgs": studio_extra_args_for_gguf(path, label, variant_overrides, repo_default_ctx),
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
