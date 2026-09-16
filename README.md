# AI Models — Omarchy bar plugin

A native [Omarchy](https://omarchy.org) shell (Quickshell/QML) bar-widget
plugin: one icon in the top bar, one dropdown panel listing every AI model
you have installed locally — **Ollama** models and raw **llama.cpp GGUF**
files — each with a live status dot and a Play/Stop button. Styled to match
the built-in Power/Bluetooth/Tailscale panels, not a separate web app.

![status](https://img.shields.io/badge/status-working-brightgreen)
![license](https://img.shields.io/badge/license-MIT-blue)

## What it does

- Auto-discovers models from:
  - `ollama list` (anything pulled/created with Ollama)
  - Raw `.gguf` files under `~/.cache/huggingface/hub/models--*/snapshots/*/*.gguf`
    and `~/.unsloth/studio/cache/ollama_links/*/*/*.gguf` (skips `mmproj-*`,
    `mtp-*`, `ggml-vocab-*` helper files)
- Play/Stop each model independently:
  - **Ollama models** are started via `POST /api/generate {keep_alive:-1}`
    (loads and keeps the model warm) and stopped via `ollama stop`.
  - **Raw GGUF models** are started by spawning
    `llama-server -m <path> --port <n> -c 124000 -fa on -ctk q8_0 -ctv q8_0`
    (124K context, flash attention, quantized KV cache to fit large contexts
    in limited RAM) and tracked by a pidfile; stop just kills that pid.
- Panel auto-refreshes on a timer (default 10s, configurable) so status
  dots reflect reality even if you start/stop a model from the terminal.

## Requirements

- [Omarchy](https://omarchy.org) (Quickshell-based Hyprland desktop), 4.x+
- `python3` (stdlib only, no extra packages)
- `curl`
- At least one of:
  - [Ollama](https://ollama.com) installed and running (`ollama serve`)
  - [llama.cpp](https://github.com/ggml-org/llama.cpp)'s `llama-server`
    binary (used for raw GGUF files)

## Install

```bash
git clone https://github.com/csilvahlg-cloud/omarchy-ai-models-plugin.git
cd omarchy-ai-models-plugin
./install.sh
```

This copies:
- `plugin/` → `~/.config/omarchy/plugins/user.ai-models/`
- `bin/ai-models-ctl` + `bin/ai-models-lib.py` → `~/.local/bin/`

and registers the widget in `~/.config/omarchy/shell.json`'s
`bar.layout.right`. If `omarchy-shell` is already running it rescans plugins
immediately; otherwise the icon appears on your next Hyprland login.

You can also install it the "official" Omarchy way once you fork/host it as
its own git repo with the manifest at the root:

```bash
omarchy plugin add https://github.com/csilvahlg-cloud/omarchy-ai-models-plugin.git --enable
```

(Note: this repo currently nests the manifest under `plugin/` alongside the
CLI backend, so `omarchy plugin add` won't find it directly — use
`install.sh`, or restructure into a manifest-at-root repo if you want native
`omarchy plugin add` support.)

## Configuration

The backend auto-generates `~/.config/omarchy/ai-models.json` on first run
by scanning Ollama + GGUF locations. To rescan (e.g. after downloading a new
model):

```bash
ai-models-ctl regen-config
```

Bar widget settings (via Omarchy's plugin settings UI, or editing the entry
in `shell.json`):

| key | default | description |
|---|---|---|
| `refreshIntervalSec` | `10` | how often the open panel polls status |

Environment variables the backend respects:

| var | default |
|---|---|
| `AI_MODELS_CONFIG` | `~/.config/omarchy/ai-models.json` |
| `AI_MODELS_STATE_DIR` | `~/.cache/ai-models-ctl` |
| `LLAMA_SERVER_BIN` | `~/.unsloth/llama.cpp/llama-server` |
| `OLLAMA_HOST` | `127.0.0.1:11434` |

## CLI usage (works standalone, no GUI needed)

```bash
ai-models-ctl list              # JSON array of {id, name, kind, status, detail}
ai-models-ctl start <id>        # e.g. ai-models-ctl start "ollama:qwen3.5:27b-q4_K_M"
ai-models-ctl stop <id>         # e.g. ai-models-ctl stop "gguf:Ling-3.0-tiny-Q8_0"
ai-models-ctl regen-config      # rescan for new models
```

## Known limitations

- Raw GGUF models share a single port (8080) since only one is meant to run
  at a time — starting a new GGUF model stops any other GGUF model already
  running. Ollama models are independent of this and can run alongside.
- No auth/TLS on the spawned `llama-server` instances (bound to
  `127.0.0.1` only).
- Loading large models (30B+) needs real RAM — a 15GB machine can OOM-kill
  Ollama trying to load a 27B model. Size your models to your hardware.
- At 124K context + `q8_0` KV cache quantization, tested on a 15GB-RAM
  machine: a ~14GB model (26B MoE) processed a real 40K-token prompt with
  ~1.4GB RAM headroom; a ~21GB model (35B MoE) did the same but with only
  ~560MB headroom and ~880MB pushed into swap — workable but tight. If you
  hit OOM kills, lower `-c` in `ai-models.json`'s `extraArgs` for that
  specific model (e.g. back to 65536 or 32768), or free RAM elsewhere first.
- `qmllint` reports a lot of false-positive warnings against Omarchy's
  virtual `qs.*` QML modules (only resolved by Quickshell's own loader) —
  don't use it as a pass/fail gate. `omarchy plugin validate` is the real one.

## License

MIT — see [LICENSE](LICENSE).
