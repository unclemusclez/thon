# VS Code Remote Example AGENTS

Use this file for all work in `examples/vscode-remote/`. Reference template: `examples/vscode/`.
This is a hackathon-focused multi-instance VS Code remote development tool with nginx
reverse proxy (SSL via mkcert/openssl), groups support, persistent workspace bind mounts,
and optional local LLM inference via Lemonade Server.

## Scope

- `examples/vscode-remote/**` — all files in this directory
- Reference: `examples/vscode/main.py` — simple single-instance pattern

## Commands

```bash
# One-time prerequisite installation (python3, nginx, docker, mkcert, openssl)
bash examples/vscode-remote/setup.sh

# Lint
pip run ruff check .

# Format
pip run ruff format .

# Type check
pip run pyright

# Run: all groups from groups.yaml with nginx + SSL (default)
python examples/vscode-remote/main.py --groups groups.yaml --external-ip 165.245.138.159

# Run: single group
python examples/vscode-remote/main.py --groups groups.yaml --group alpha --external-ip 1.2.3.4

# Run: with secure per-user passwords
python examples/vscode-remote/main.py --groups groups.yaml --secure --external-ip 1.2.3.4

# Run: with persistent workspace bind mounts
python examples/vscode-remote/main.py --groups groups.yaml --workspace-dir /vs-code-remote

# Run: single instance without groups (like examples/vscode/main.py)
python examples/vscode-remote/main.py

# Run: direct HTTP without nginx
python examples/vscode-remote/main.py --no-nginx

# Cleanup all nginx configs
python examples/vscode-remote/main.py --cleanup

# Build Docker image
docker build -t opensandbox/vscode:latest examples/vscode-remote/

# Lemonade Server: full setup via shell (recommended — service manages its own lifecycle)
bash examples/vscode-remote/setup-lemonade.sh --groups groups.yaml --generate-keys --external-ip 1.2.3.4

# Lemonade Server: full setup via Python wrapper (alternative)
python examples/vscode-remote/lemonade_server.py run --groups groups.yaml --generate-keys --external-ip 1.2.3.4

# Lemonade Server: service management (it runs as systemd, no long-running process needed)
sudo systemctl status lemonade-server
sudo systemctl stop lemonade-server
sudo systemctl restart lemonade-server
sudo journalctl -u lemonade-server -f

# Lemonade Server: pull / configure via CLI
lemonade pull unsloth/gemma-4-31B-it-GGUF:Q8_K_XL
lemonade config set llamacpp.backend=auto host=0.0.0.0

# Run VS Code instances with Lemonade inference (injects kilo.json into each sandbox)
python examples/vscode-remote/main.py --groups groups.yaml --external-ip 1.2.3.4 --lemonade kilo.json
```

## Code Style

### Language & Formatting
- **Python 3.10+** (project minimum)
- **ruff** for lint and format; line-length = 88 (follows SDK convention)
- **pyright** with `typeCheckingMode = "standard"` for type checking
- **Apache 2.0 license header** required on every file

### Imports
Order: stdlib → third-party → local:
```python
import argparse
import asyncio
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import yaml

from opensandbox import Sandbox
from opensandbox.config import ConnectionConfig
from opensandbox.models.execd import RunCommandOpts
from opensandbox.models.sandboxes import Host, Volume

from nginx_config import NginxConfigGenerator
from ssl_cert import SSLCertificateGenerator
```

### Type Hints
Required on all function signatures. Use `Optional[T]`, `list[T]`, `tuple[str, ...]` syntax (Python 3.10+).

### Naming Conventions
- Functions/methods: `snake_case`
- Classes: `PascalCase`
- Constants / class attrs: `UPPER_SNAKE_CASE`
- Private internals: `_leading_underscore`
- CLI flags: `--kebab-case`

### Docstrings
Google-style on public classes/functions. Module docstring at top of every file.

### Error Handling
- Raise with descriptive messages; chain with `raise ... from e`
- Validate inputs early at function entry

### Async Patterns
- All sandbox operations are async — use `await`
- Use `asyncio.gather()` for concurrent instance creation
- Use `RunCommandOpts(background=True)` for long-running processes (code-server)
- Always use `try/finally` for cleanup (kill sandboxes, remove nginx configs)

### Logging (CLI Tools)
Use `print()` with prefixed labels: `[{group}/{username}]`, `[Nginx]`, `[SSL]`

## Architecture

### Core Models
- **`UserInfo` dataclass**: group, username, workspace (`{group}/{username}`), label
- **`SandboxInstance` dataclass**: user, port, sandbox, endpoint, password (if secure)

### Key Classes
- **`NginxConfigGenerator`**: generates **per-port individual** nginx config files in
  `/etc/nginx/sites-available/`, symlinked to `/etc/nginx/sites-enabled/`, named
  `sandbox-vscode-remote-{port}`. Each config has its own server block.
  - `generate_port_config(port, cert_path, key_path, ca_cert_path)` — one file per port
  - `enable_config(config_path)` — symlink to sites-enabled
  - `cleanup_all()` — remove all `sandbox-vscode-remote-*` configs and reload
- **`SSLCertificateGenerator`**: generates SSL certs via **mkcert** (preferred, CA-trusted)
  with **openssl** fallback. Single shared cert for all instances. Filename includes hash
  of IP so changing `--external-ip` triggers regeneration.
  - `generate_server_cert(server_ip)` — returns (cert_path, key_path)
  - `get_mkcert_ca_root()` — returns mkcert CA root dir path (or None)

### Groups YAML

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

Each user gets: sandbox instance → workspace at `/workspace/{group}/{username}` → URL at `https://{ip}/{endpoint_path}/`

### Network Modes (auto-detected from endpoint format)

| Mode | Server Endpoint Format | Nginx proxy_pass | Detected By |
|------|----------------------|------------------|-------------|
| **Host** | `127.0.0.1:8443` | `http://127.0.0.1:{port}/` | No `/` after port |
| **Bridge** | `127.0.0.1:52322/proxy/8443` | `http://127.0.0.1:{port}/` | `/proxy/` in endpoint |

Bridge/host mode is **auto-detected** from the server-returned endpoint format — NOT a CLI flag.
The server's `~/.sandbox.toml` determines `docker.network_mode`.

**Critical**: `proxy_pass` must NOT include upstream path. `proxy_pass http://127.0.0.1:{port}/;`
is correct. The browser sends the full endpoint path (e.g., `/51111/proxy/8448/`), nginx strips
`/{endpoint_port}/`, and the remainder reaches execd correctly.

### Persistent Workspaces

With `--workspace-dir /vs-code-remote`, each user gets a host bind mount:
- Host path: `/vs-code-remote/{group}/{username}`
- Container mount: `/workspace/{group}/{username}`
- Implemented via SDK `Volume(name="workspace", host=Host(path=host_path), mount_path=workspace_path)`
- Host directories are created with `os.makedirs()` before sandbox creation
- Without `--workspace-dir`, workspace is created inside the container via `mkdir -p` (ephemeral)

### Security Modes

| Flag | code-server auth | Password |
|------|-----------------|----------|
| (default) | `--auth none` | None |
| `--secure` | `--auth password` | Auto-generated per-user (24-char token) |

### Certificate Flow

1. **mkcert** (preferred): Generates CA-trusted certs. Filename includes IP hash.
   - CA root must be installed on client browsers for trust
   - CA cert served at `https://{ip}/ca.crt` for download
2. **openssl** (fallback): Self-signed certs with IP in SAN
3. Single shared cert for all instances on port 443
4. code-server always runs **HTTP** inside containers; nginx terminates SSL externally

### Nginx Template Features (per-port config)
- Individual server block per port, `server_name _;`
- `listen 80;` and `listen 443 ssl;`
- TLSv1.2 + TLSv1.3, `HIGH:!aNULL:!MD5` ciphers
- WebSocket upgrade headers (`Upgrade`, `Connection "upgrade"`)
- `X-Forwarded-For`, `X-Forwarded-Proto https`, `proxy_redirect off`
- `add_header Service-Worker-Allowed /;` (fixes SW scope errors)
- `proxy_read/send_timeout 86400` (24h for long-lived WS connections)
- `proxy_buffering off; proxy_request_buffering off;` (real-time data)
- Conditional `location = /ca.crt` block (only when mkcert CA root exists)

### URL Display
- HTTPS URL includes full endpoint path: `https://{ip}/{endpoint_path}/`
  where endpoint_path strips `127.0.0.1:` prefix from the endpoint string
- Example: endpoint `127.0.0.1:51111/proxy/8448` → URL `https://165.245.131.172/51111/proxy/8448/`

### Lemonade Server (Local LLM Inference)

A local Lemonade inference server provides OpenAI-compatible LLM endpoints that VS Code
extensions (Kilo Code, Continue, Cline) inside sandbox containers can connect to. The
server runs as a **systemd service** and manages its own lifecycle — no long-running
Python process needed.

**Two ways to set up:**
1. **`setup-lemonade.sh`** (recommended) — Shell script that uses the `lemonade` CLI
   and `systemctl` directly. One command does everything: install, configure, generate
   API keys, pull model, generate kilo.json.
2. **`lemonade_server.py`** — Python wrapper with `LemonadeServerManager` class.
   Provides subcommands (`install`, `configure`, `start`, `stop`, `pull`, `run`, etc.)
   and programmatic access to the same operations. Useful for scripted automation.

**Service management (once installed):**
```bash
sudo systemctl start|stop|restart lemonade-server
sudo systemctl status lemonade-server
sudo journalctl -u lemonade-server -f
lemonade config set key=value
lemonade pull <model>
```

**Configuration:**
- Config file: `/var/lib/lemonade/.cache/lemonade/config.json`
- API keys stored in `/etc/systemd/system/lemonade-server.service.d/override.conf`
- Default port: `13305`, default host: `0.0.0.0`
- Default backend: `auto` (Lemonade auto-detects GPU; can be overridden with `--llamacpp-backend`)
- Custom models: `user_models.json`, `server_models.json`, and `recipe_options.json` in the cache directory

**Default Model:**
- Checkpoint: `unsloth/gemma-4-31B-it-GGUF:Q8_K_XL`
- Short name: `gemma-4-31b-it` (registered as `user.gemma-4-31b-it`; the `user.` prefix is required in API requests)
- Recipe: `llamacpp` with auto-detected backend

**Per-User Scaling:**
When `--groups groups.yaml` is passed, the number of users is counted automatically and
scales the llama.cpp args in `recipe_options.json`:

| Parameter | Value |
|-----------|-------|
| `ctx_size` | `262144` (per-slot, set in recipe_options) |
| `-np` | `num_users` |
| Per-slot `ctx_size` | `262144` |

Lemonade-managed args (reserved, must NOT be in `llamacpp_args`):
`--ctx-size`, `-c`, `-ngl`, `--gpu-layers`, `--n-gpu-layers`, `--jinja`, `--no-jinja`,
`--model`, `-m`, `--port`, `--embedding`, `--embeddings`, `--mmproj*`, `--rerank*`

Custom llama.cpp args (safe to override):
```
-b 8192 -ub 8192 -to 3600 -ctk q8_0 -ctv q8_0
--temp 1.0 --top-k 64 --top-p 0.95 --min-p 0.0
--repeat-penalty 1.0 --no-webui --threads-http -1 --threads -1
-np <num_users>
```

**user_models.json example:**
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

**recipe_options.json example (4 users):**
```json
{
    "user.gemma-4-31b-it": {
        "ctx_size": 262144,
        "llamacpp_backend": "auto",
        "llamacpp_args": "-b 8192 -ub 8192 -to 3600 -ctk q8_0 -ctv q8_0 --temp 1.0 --top-k 64 --top-p 0.95 --min-p 0.0 --repeat-penalty 1.0 --no-webui --threads-http -1 --threads -1 -np 4"
    }
}
```

**API Key Security:**
| Env Variable | Access Level |
|---|---|
| `LEMONADE_API_KEY` | Regular endpoints (`/api/*`, `/v0/*`, `/v1/*`) |
| `LEMONADE_ADMIN_API_KEY` | All endpoints including `/internal/*` |

When both are set, either key is accepted for regular endpoints; admin key is required for internal.

**Kilo Code Integration:**
1. `setup-lemonade.sh --groups groups.yaml --generate-keys` generates API keys and writes `kilo.json`
2. `kilo.json` contains: provider name (`lemonade`), base URL (auto-detected), API key, model ID (`user.gemma-4-31b-it`)
3. Base URL resolution order: `--external-ip` > Docker bridge gateway > `localhost`
4. `main.py --lemonade kilo.json` injects the config into each sandbox at `/workspace/.kilo/kilo.json`
5. Kilo Code extension in the sandbox reads the config and connects to the Lemonade server

**Full Workflow:**
```bash
# Terminal 1: Start Lemonade server with groups-based user count (generates kilo.json)
python lemonade_server.py run --groups groups.yaml --generate-keys --external-ip 1.2.3.4

# Terminal 2: Start VS Code sandboxes with Lemonade inference
python main.py --groups groups.yaml --external-ip 1.2.3.4 --lemonade kilo.json
```

## Guardrails

### Must Always
- Generate SSL certs on the **host** via mkcert/openssl, never inside containers
- Clean up nginx configs + kill sandboxes in `finally` blocks
- Include Apache 2.0 header on every new file
- Use `--external-ip` when accessing via IP address (prevents SW SSL errors)
- Auto-detect network mode from endpoint format, NOT from a CLI flag
- Use `pip install` (not `uv`) — user's intentional choice
- Use repo URL `https://github.com/unclemusclez/OpenSandbox.git` in setup.sh

### Must Never
- Commit secrets, API keys, or `.key` files to the repository
- Generate certs inside sandbox containers
- Mix unrelated changes in one PR
- Use `--base-path` on code-server — it breaks the proxy chain (causes bad gateway)
- Include upstream path in `proxy_pass` (causes path doubling)
- Use `uv` for package management

### Known Gotchas

**Service Worker SSL Error**:
```
SecurityError: Failed to register a ServiceWorker for scope ('https://{ip}/{path}/.../pre/')
An SSL certificate error occurred when fetching the script.
```
- **Root cause**: Self-signed certs cause SW registration to fail
- **Fix**: mkcert CA-trusted certs fix this on the host. Remote clients must download
  and import the CA root from `https://{ip}/ca.crt`

**proxy_pass path doubling**: `proxy_pass http://127.0.0.1:45960/proxy/8447/;` causes
nginx to strip the location prefix then prepend the proxy_pass URI, doubling the path.
Correct: `proxy_pass http://127.0.0.1:45960/;`

**--base-path breaks proxy chain**: In bridge mode, execd strips `/proxy/{port}` before
forwarding to code-server. If code-server has `--base-path /{port}/`, it expects `/8443/`
but receives `/`, causing bad gateway. Do NOT use `--base-path`.

**listen 80 default_server conflicts**: nginx's default site uses `default_server`.
Must remove default site and use `listen 80;` without `default_server`.

**GitHub cookie warnings**: `_gh_sess`, `_octo`, `logged_in` cookies are from VS Code
extensions making cross-site requests to github.com — cannot be fixed server-side.

**Environment Variables**:
- `SANDBOX_DOMAIN` — server address (default: `localhost:8080`)
- `SANDBOX_API_KEY` — optional API key
- `SANDBOX_IMAGE` — Docker image (default: `opensandbox/vscode:latest`)
- `PYTHON_VERSION` — Python version in sandbox (default: `3.11`)
- `LEMONADE_API_KEY` — Lemonade server API key for regular endpoints
- `LEMONADE_ADMIN_API_KEY` — Lemonade server admin key (elevated access)

## File Map

| File | Purpose |
|------|---------|
| `main.py` | Entry point; argparse CLI; groups loading; instance orchestration; persistent workspaces; Lemonade kilo.json injection |
| `groups.yaml` | Groups and users configuration |
| `setup.sh` | One-time install: python3, nginx, docker.io, mkcert, openssl |
| `nginx_config.py` | `NginxConfigGenerator`; per-port individual configs in sites-available |
| `ssl_cert.py` | `SSLCertificateGenerator`; mkcert primary with openssl fallback |
| `generate-certs.py` | Legacy mkcert helper (preserved for local dev) |
| `lemonade_server.py` | `LemonadeServerManager`; Python wrapper for install, configure, start/stop, pull/load models, generate kilo.json |
| `setup-lemonade.sh` | All-in-one shell script: install, configure, generate API keys, pull model, generate kilo.json (recommended) |
| `build-amd-mi300x-llama-server.sh` | Build llama.cpp from source for AMD MI300X (gfx942) with ROCm; installed to `/usr/local` |
| `kilo.json` | Kilo Code config template for Lemonade OpenAI-compatible provider |
| `vscode-settings.jsonc` | VS Code settings template injected into each sandbox's code-server |
| `Dockerfile` | Sandbox image: python:3.12-slim + code-server + non-root vscode user |
| `template.portnumber.available.md` | Nginx template reference showing port-based location blocks |
| `../vscode/main.py` | Reference template: single-instance, minimal |
