# THON - The Hackathon Organizer Node

> Migrated to https://github.com/WaterPistolAI/thon.git

Run multiple VS Code sandbox instances concurrently with nginx SSL reverse proxy,
groups-based user management, persistent workspaces, and optional local LLM inference
via Lemonade Server.

## Video Guide

https://youtu.be/YptAQQf_4dg

## Quick Start

### 1. One-time Setup

```bash
bash ./setup.sh
```

Installs python3, nginx, docker.io, mkcert, and openssl.

### 2. Build the Docker Image

```bash
docker build -t waterpistol/thon:latest ./
```

### 3. Define Groups

Create `groups.yaml`:

```yaml
groups:
  alpha:
    users:
      - alice
      - bob
  beta:
    users:
      - dave
```

### 4. Run

```bash
python ./main.py --groups groups.yaml --external-ip 1.2.3.4
```

Each user gets their own VS Code sandbox at `https://<ip>/<endpoint_path>/`.

## Architecture

| Component | Role |
|-----------|------|
| **main.py** | Orchestrates sandbox creation, nginx configs, workspace setup |
| **nginx** | SSL termination + WebSocket proxy (per-port server blocks) |
| **code-server** | VS Code in the browser, runs HTTP inside each sandbox |
| **Lemonade Server** | Optional local LLM inference (OpenAI-compatible API) |

### Network Modes (auto-detected)

| Mode | Endpoint Format | Detection |
|------|----------------|-----------|
| **Host** | `127.0.0.1:8443` | No `/` after port |
| **Bridge** | `127.0.0.1:52322/proxy/8443` | `/proxy/` in endpoint |

Auto-detected from the server-returned endpoint — not a CLI flag.

### SSL/TLS

- **mkcert** (preferred): CA-trusted certs, filename includes IP hash
- **openssl** (fallback): Self-signed certs with IP in SAN
- Single shared cert for all instances on port 443
- CA cert served at `https://<ip>/ca.crt` for remote clients

### Persistent Workspaces

With `--workspace-dir /vs-code-remote`, each user gets a host bind mount:

- Host path: `/vs-code-remote/{group}/{username}`
- Container mount: `/workspace/{group}/{username}`
- Without it, workspace is ephemeral (inside container only)

## CLI Reference

```
python main.py [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--groups FILE` | Path to groups.yaml | (none, single instance) |
| `--group GROUP` | Run only this group from groups.yaml | (all groups) |
| `--port PORT` | Starting port for code-server | `8443` |
| `--timeout MIN` | Sandbox timeout in minutes | `0` (no timeout) |
| `--domain DOMAIN` | Sandbox server domain | `localhost:8080` |
| `--api-key KEY` | Sandbox API key | (none) |
| `--image IMAGE` | Docker image | `waterpistol/thon:latest` |
| `--python-version VER` | Python version in sandbox | `3.11` |
| `--secure` | Enable per-user passwords | `false` |
| `--external-ip IP` | External IP for SSL and URLs | auto-detected |
| `--ssl-dir DIR` | SSL cert storage directory | `/etc/nginx/ssl` |
| `--no-nginx` | Disable nginx, use direct HTTP | `false` |
| `--workspace-dir DIR` | Host dir for persistent bind mounts | (none) |
| `--lemonade KILO_JSON` | kilo.json path for LLM config injection | (none) |
| `--vscode-settings JSON` | VS Code settings file to inject | (none) |
| `--cleanup` | Remove all nginx configs and exit | `false` |

### Examples

```bash
# All groups with nginx SSL (default)
python main.py --groups groups.yaml --external-ip 1.2.3.4

# Single group
python main.py --groups groups.yaml --group alpha --external-ip 1.2.3.4

# Per-user passwords
python main.py --groups groups.yaml --secure --external-ip 1.2.3.4

# Persistent workspaces
python main.py --groups groups.yaml --workspace-dir /vs-code-remote --external-ip 1.2.3.4

# Direct HTTP (no nginx)
python main.py --groups groups.yaml --no-nginx

# Single instance (no groups)
python main.py

# With Lemonade LLM inference
python main.py --groups groups.yaml --external-ip 1.2.3.4 --lemonade kilo.json

# With custom VS Code settings
python main.py --groups groups.yaml --external-ip 1.2.3.4 --vscode-settings vscode-settings.jsonc

# Cleanup nginx configs
python main.py --cleanup
```

## Lemonade Server (Local LLM Inference)

Provides an OpenAI-compatible API endpoint for VS Code extensions (Kilo Code, Continue, Cline)
inside sandbox containers. Runs as a **systemd service** on the host.

### Setup

```bash
# Full setup (install + configure + API keys + pull model + kilo.json)
bash ./setup-lemonade.sh \
    --groups groups.yaml --generate-keys --external-ip 1.2.3.4
```

Or use the Python wrapper:

```bash
python ./lemonade_server.py run \
    --groups groups.yaml --generate-keys --external-ip 1.2.3.4
```

### Service Management

```bash
sudo systemctl status lemonade-server
sudo systemctl stop lemonade-server
sudo systemctl restart lemonade-server
sudo journalctl -u lemonade-server -f
```

### Configuration

| File | Location | Purpose |
|------|----------|---------|
| config.json | `/var/lib/lemonade/.cache/lemonade/config.json` | Server settings (port, host, backend) |
| user_models.json | Same directory | User-registered custom models |
| server_models.json | Same directory | Server-suggested models |
| recipe_options.json | Same directory | Per-model runtime settings (ctx_size, backend, args) |
| API keys | `/etc/systemd/system/lemonade-server.service.d/override.conf` | LEMONADE_API_KEY, LEMONADE_ADMIN_API_KEY |

### Default Model

| Field | Value |
|-------|-------|
| Checkpoint | `unsloth/gemma-4-31B-it-GGUF:Q8_K_XL` |
| Short name | `gemma-4-31b-it` (API name: `user.gemma-4-31b-it`) |
| Recipe | `llamacpp` with auto-detected backend |
| mmproj | `mmproj-BF16.gguf` (vision model) |

### Per-User Scaling

When `--groups groups.yaml` is passed, context size and parallel slots scale automatically:

| Parameter | Value |
|-----------|-------|
| `ctx_size` | `262144 × num_users` (total context) |
| `-np` | `num_users` (parallel slots) |

Lemonade-managed args (reserved, must NOT appear in `llamacpp_args`):
`--ctx-size`, `-c`, `-ngl`, `--gpu-layers`, `--n-gpu-layers`, `--jinja`, `--no-jinja`,
`--model`, `-m`, `--port`, `--embedding`, `--embeddings`, `--mmproj*`, `--rerank*`

### setup-lemonade.sh Options

| Option | Description | Default |
|--------|-------------|---------|
| `--groups FILE` | groups.yaml for user count | (none) |
| `--group GROUP` | Filter to single group | (all) |
| `--num-users N` | Override parallel user count | `1` |
| `--port PORT` | Server port | `13305` |
| `--host HOST` | Bind address | `0.0.0.0` |
| `--backend BACKEND` | llama.cpp backend: auto, vulkan, cpu | `auto` |
| `--ctx-size SIZE` | Per-user context size | `262144` |
| `--model MODEL` | HuggingFace checkpoint | `unsloth/gemma-4-31B-it-GGUF:Q8_K_XL` |
| `--model-name NAME` | Short model name | `gemma-4-31b-it` |
| `--mmproj FILE` | Vision mmproj filename | `mmproj-BF16.gguf` |
| `--external-ip IP` | External IP for kilo.json | (auto-detect) |
| `--generate-keys` | Generate API keys | `false` |
| `--no-prefer-system` | Use bundled llama.cpp | (system preferred) |
| `--llamacpp-bin PATH` | Path to system llama-server | `/usr/local/bin/llama-server` |
| `--kilo-config PATH` | Output path for kilo.json | `./kilo.json` |

### Building llama.cpp from Source (AMD MI300X)

```bash
bash ./build-amd-mi300x-llama-server.sh
```

Builds llama.cpp with ROCm/HIP for `gfx942` and installs to `/usr/local`. The Lemonade
config uses `prefer_system: true` with `rocm_bin: /usr/local/bin/llama-server` by default.

### Kilo Code Integration

1. `setup-lemonade.sh --generate-keys` creates API keys and writes `kilo.json`
2. `kilo.json` contains: provider (`lemonade`), base URL, API key, model ID (`user.gemma-4-31b-it`)
3. Base URL resolution: `--external-ip` > Docker bridge gateway > `localhost`
4. `main.py --lemonade kilo.json` injects config into each sandbox at `/home/vscode/.config/kilo/config.json`
5. Kilo Code reads the config and connects to the Lemonade server

### Full Workflow

```bash
# Terminal 1: Set up Lemonade server with groups-based scaling
bash setup-lemonade.sh --groups groups.yaml --generate-keys --external-ip 1.2.3.4

# Terminal 2: Start VS Code sandboxes with Lemonade inference
python main.py --groups groups.yaml --external-ip 1.2.3.4 --lemonade kilo.json
```

## Security

| Flag | code-server auth | Password |
|------|-----------------|----------|
| (default) | `--auth none` | None |
| `--secure` | `--auth password` | Auto-generated per-user (24-char token) |

## Troubleshooting

### Service Worker SSL Error

```
SecurityError: Failed to register a ServiceWorker — An SSL certificate error occurred
```

**Fix**: Use mkcert CA-trusted certs. Remote clients must download and import the
CA root from `https://<ip>/ca.crt`.

### Bad Gateway (502)

Caused by `--base-path` on code-server or including upstream path in `proxy_pass`.
Do NOT use `--base-path` and ensure `proxy_pass` ends with `/` only.

### Model Not Found (404)

The `user.` prefix is required for user-registered models. Kilo Code should send
`user.gemma-4-31b-it` as the model name, not `gemma-4-31b-it`.

### Reserved llama.cpp Arguments

Lemonade manages these arguments internally and rejects them in `llamacpp_args`:
`-ngl`, `--jinja`, `--ctx-size`, `-c`, `-m`, `--port`, `--mmproj*`, `--rerank*`

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SANDBOX_DOMAIN` | Sandbox server address | `localhost:8080` |
| `SANDBOX_API_KEY` | Sandbox API key | (none) |
| `SANDBOX_IMAGE` | Docker image | `waterpistol/thon:latest` |
| `PYTHON_VERSION` | Python version in sandbox | `3.11` |
| `LEMONADE_API_KEY` | Lemonade API key (regular) | (none) |
| `LEMONADE_ADMIN_API_KEY` | Lemonade admin key (elevated) | (none) |

## File Map

| File | Purpose |
|------|---------|
| `main.py` | Entry point; CLI; groups; sandbox orchestration; kilo.json injection |
| `groups.yaml` | Groups and users configuration |
| `setup.sh` | One-time host prerequisite installation |
| `nginx_config.py` | Per-port nginx config generation |
| `ssl_cert.py` | SSL certificate generation (mkcert/openssl) |
| `lemonade_server.py` | Lemonade server manager (Python CLI) |
| `setup-lemonade.sh` | All-in-one Lemonade setup (shell, recommended) |
| `build-amd-mi300x-llama-server.sh` | Build llama.cpp for AMD MI300X (gfx942) |
| `kilo.json` | Kilo Code config template |
| `vscode-settings.jsonc` | VS Code settings template |
| `Dockerfile` | Sandbox image: python:3.12-slim + code-server |
