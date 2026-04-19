---
title: Lemonade Server Integration
description: Set up local LLM inference with Lemonade Server for VS Code extensions
---

# Lemonade Server Integration

Lemonade Server provides a local OpenAI-compatible API endpoint that VS Code extensions
(Kilo Code, Continue, Cline) can use for LLM inference. It runs as a systemd service
and supports GPU acceleration via ROCm, CUDA, or Vulkan.

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Host Machine                          │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Lemonade Server (:13305)                  │  │
│  │                                                       │  │
│  │   /v1/chat/completions  → OpenAI-compatible API      │  │
│  │   /api/v1/load          → Model management           │  │
│  │   /api/v1/models        → List available models      │  │
│  │                                                       │  │
│  │   ┌─────────────────────────────────────────────┐    │  │
│  │   │            llama.cpp backend                 │    │  │
│  │   │   (ROCm / CUDA / Vulkan / CPU)              │    │  │
│  │   └─────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────┘  │
│                              ▲                               │
│                              │ HTTP                          │
│  ┌───────────────────────────┴───────────────────────────┐  │
│  │                 VS Code Sandboxes                      │  │
│  │                                                        │  │
│  │   Kilo Code ──┐                                       │  │
│  │   Continue  ───┼──→ http://host:13305/v1/...         │  │
│  │   Cline     ───┘                                       │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Quick Setup

### One-Command Setup

```bash
bash examples/vscode-remote/setup-lemonade.sh \
    --groups groups.yaml \
    --generate-keys \
    --external-ip YOUR_IP
```

This command:
1. Installs Lemonade Server from PPA
2. Configures GPU backend (auto-detected)
3. Generates API keys
4. Downloads the default model
5. Creates `kilo.json` for Kilo Code

### Manual Setup

<details>
<summary>Click to expand manual setup steps</summary>

```bash
# 1. Install from PPA
sudo add-apt-repository -y ppa:lemonade-team/stable
sudo apt-get update
sudo apt-get install -y lemonade-server

# 2. Configure
lemonade config set host=0.0.0.0 port=13305

# 3. Generate API keys
API_KEY=$(openssl rand -base64 32 | tr -d '/+=\n' | head -c 32)
ADMIN_KEY=$(openssl rand -base64 32 | tr -d '/+=\n' | head -c 32)

sudo mkdir -p /etc/systemd/system/lemonade-server.service.d
sudo tee /etc/systemd/system/lemonade-server.service.d/override.conf <<EOF
[Service]
Environment="LEMONADE_API_KEY=${API_KEY}"
Environment="LEMONADE_ADMIN_API_KEY=${ADMIN_KEY}"
EOF
sudo systemctl daemon-reload

# 4. Start server
sudo systemctl restart lemonade-server

# 5. Pull model
lemonade pull unsloth/gemma-4-31B-it-GGUF:Q8_K_XL
```

</details>

## Service Management

```bash
# Check status
sudo systemctl status lemonade-server

# View logs
sudo journalctl -u lemonade-server -f

# Restart
sudo systemctl restart lemonade-server

# Stop
sudo systemctl stop lemonade-server
```

## Configuration

### Config File Location

```
/var/lib/lemonade/.cache/lemonade/
├── config.json           # Server settings
├── user_models.json      # User-registered models
├── server_models.json    # Server-suggested models
└── recipe_options.json   # Per-model runtime settings
```

### Server Configuration (config.json)

```json
{
  "port": 13305,
  "host": "0.0.0.0",
  "log_level": "info",
  "ctx_size": 262144,
  "llamacpp": {
    "backend": "auto",
    "prefer_system": true,
    "rocm_bin": "/usr/local/bin/llama-server",
    "vulkan_bin": "/usr/local/bin/llama-server",
    "cpu_bin": "/usr/local/bin/llama-server"
  }
}
```

### Backend Options

| Backend | Description | Use Case |
|---------|-------------|----------|
| `auto` | Auto-detect GPU | Recommended (default) |
| `vulkan` | Cross-platform GPU | AMD/NVIDIA without ROCm/CUDA |
| `cpu` | CPU-only | No GPU available |

::: warning
`rocm` is **not** a valid `llamacpp_backend` value. Use `auto` to enable ROCm
auto-detection.
:::

### Model Configuration (user_models.json)

```json
{
  "gemma-4-31b-it": {
    "model_name": "gemma-4-31b-it",
    "checkpoint": "unsloth/gemma-4-31B-it-GGUF:Q8_K_XL",
    "recipe": "llamacpp",
    "suggested": true,
    "labels": ["custom", "vision"],
    "mmproj": "mmproj-BF16.gguf"
  }
}
```

### Runtime Options (recipe_options.json)

```json
{
  "user.gemma-4-31b-it": {
    "ctx_size": 1572864,
    "llamacpp_backend": "auto",
    "llamacpp_args": "-b 8192 -ub 8192 -to 3600 -ctk q8_0 -ctv q8_0 --temp 1.0 --top-k 64 --top-p 0.95 --min-p 0.0 --repeat-penalty 1.0 --no-webui --threads-http -1 --threads -1 -np 6"
  }
}
```

## Per-User Scaling

When using `--groups groups.yaml`, context and parallelism scale automatically:

| Parameter | Calculation | Example (6 users) |
|-----------|-------------|-------------------|
| `ctx_size` | `262144 × num_users` | 1,572,864 |
| `-np` | `num_users` | 6 |

Each user gets a full 262,144 token context window.

## Reserved Arguments

These arguments are **managed by Lemonade** and cannot be in `llamacpp_args`:

```
--ctx-size, -c, -ngl, --gpu-layers, --n-gpu-layers, --jinja, --no-jinja,
--model, -m, --port, --embedding, --embeddings, --mmproj*, --rerank*
```

## API Keys

| Variable | Scope | Location |
|----------|-------|----------|
| `LEMONADE_API_KEY` | Regular endpoints (`/api/*`, `/v1/*`) | systemd override |
| `LEMONADE_ADMIN_API_KEY` | All endpoints including `/internal/*` | systemd override |

### Using API Keys

```bash
# CLI
LEMONADE_API_KEY=your_key lemonade pull model-name

# HTTP
curl -H "Authorization: Bearer your_key" http://localhost:13305/v1/chat/completions
```

## Custom llama.cpp Build

### AMD MI300X (gfx942)

```bash
bash examples/vscode-remote/build-amd-mi300x-llama-server.sh
```

This builds llama.cpp with:
- ROCm/HIP backend
- `gfx942` target (MI300X)
- Installs to `/usr/local/bin/llama-server`

The default Lemonade config uses `prefer_system: true` with this binary.

### Other GPUs

Modify `build-amd-mi300x-llama-server.sh` for your architecture:

```bash
# Change AMDGPU_TARGETS for your GPU
-DAMDGPU_TARGETS=gfx1100  # RX 7900 series
-DAMDGPU_TARGETS=gfx1030  # RX 6000/7000 series
```

## Kilo Code Integration

### Generate Config

```bash
bash examples/vscode-remote/setup-lemonade.sh \
    --groups groups.yaml \
    --generate-keys \
    --external-ip YOUR_IP
```

Creates `kilo.json`:

```json
{
  "provider": {
    "lemonade": {
      "models": {
        "user.gemma-4-31b-it": {
          "name": "unsloth/gemma-4-31B-it-GGUF:Q8_K_XL",
          "limit": {
            "context": 262144,
            "output": 4096
          }
        }
      },
      "options": {
        "apiKey": "your-api-key",
        "baseURL": "http://YOUR_IP:13305/v1"
      }
    }
  },
  "model": "lemonade/user.gemma-4-31b-it"
}
```

### Inject into Sandboxes

```bash
python examples/vscode-remote/main.py \
    --groups groups.yaml \
    --external-ip YOUR_IP \
    --lemonade kilo.json
```

Injects config to `/home/vscode/.config/kilo/config.json` in each sandbox.

## CLI Reference

### setup-lemonade.sh Options

| Option | Default | Description |
|--------|---------|-------------|
| `--groups FILE` | (none) | groups.yaml for user count |
| `--group GROUP` | (all) | Filter to single group |
| `--num-users N` | 1 | Override parallel user count |
| `--port PORT` | 13305 | Server port |
| `--host HOST` | 0.0.0.0 | Bind address |
| `--backend BACKEND` | auto | llama.cpp backend |
| `--ctx-size SIZE` | 262144 | Per-user context size |
| `--model MODEL` | unsloth/gemma-4-31B-it-GGUF:Q8_K_XL | HuggingFace checkpoint |
| `--model-name NAME` | gemma-4-31b-it | Short model name |
| `--mmproj FILE` | mmproj-BF16.gguf | Vision mmproj filename |
| `--external-ip IP` | (auto) | External IP for kilo.json |
| `--generate-keys` | false | Generate API keys |
| `--no-prefer-system` | (system) | Use bundled llama.cpp |
| `--llamacpp-bin PATH` | /usr/local/bin/llama-server | System binary path |
| `--kilo-config PATH` | ./kilo.json | Output path for kilo.json |

### lemonade CLI Commands

```bash
# Pull model
lemonade pull org/repo:variant

# List models
lemonade list

# Configure
lemonade config set key=value

# Run inference
lemonade run user.model-name
```

## Troubleshooting

### Model Not Found (404)

Ensure model name includes `user.` prefix in API requests:
- ✅ `user.gemma-4-31b-it`
- ❌ `gemma-4-31b-it`

### Reserved Argument Error

Remove reserved args from `llamacpp_args`. Lemonade manages:
- GPU layers (`-ngl`)
- Context size (`--ctx-size`)
- Jinja formatting (`--jinja`)
- Model path (`--model`)

### Backend Not Detected

```bash
# Check GPU
rocminfo  # AMD
nvidia-smi  # NVIDIA

# Force backend
lemonade config set llamacpp.backend=vulkan
sudo systemctl restart lemonade-server
```

### Memory Issues

Reduce context size or use smaller quantization:
```bash
# Smaller context
lemonade config set ctx_size=131072

# Smaller model
lemonade pull unsloth/gemma-4-31B-it-GGUF:Q4_K_M
```
