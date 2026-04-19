# Copyright 2025 Alibaba Group Holding Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Lemonade inference server service wrapper."""

import json
import logging
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from app.config import LemonadeConfig
from app.exceptions import LemonadeConnectionError, LemonadeNotInstalledError
from app.models import LemonadeStatus

logger = logging.getLogger(__name__)

LEMONADE_DEFAULT_MODEL = "unsloth/gemma-4-31B-it-GGUF:Q8_K_XL"
LEMONADE_DEFAULT_MODEL_NAME = "gemma-4-31b-it"


class LemonadeService:
    """Manages interaction with the local Lemonade inference server.

    Provides status monitoring, model management, and configuration
    introspection without requiring systemd privileges (read-only mode).
    """

    def __init__(self, config: LemonadeConfig) -> None:
        self._cfg = config

    @property
    def endpoint(self) -> str:
        host = "localhost" if self._cfg.host == "0.0.0.0" else self._cfg.host
        return f"http://{host}:{self._cfg.port}"

    def is_installed(self) -> bool:
        for cmd in ("lemonade-server", "lemonade"):
            try:
                result = subprocess.run(
                    ["which", cmd], capture_output=True, check=False
                )
                if result.returncode == 0:
                    return True
            except FileNotFoundError:
                continue
        return False

    def get_status(self) -> LemonadeStatus:
        """Return a snapshot of the Lemonade server status."""
        running = self._check_running()
        model = ""
        ctx_size = 0
        num_users = 0
        api_key_configured = bool(self._cfg.api_key or self._cfg.admin_api_key)

        if running:
            model_info = self._read_model_config()
            if model_info:
                model = model_info.get("model", LEMONADE_DEFAULT_MODEL_NAME)
                ctx_size = model_info.get("ctx_size", 0)
                num_users = model_info.get("num_users", 0)

        return LemonadeStatus(
            running=running,
            endpoint=self.endpoint,
            model=model,
            api_key_configured=api_key_configured,
            ctx_size=ctx_size,
            num_users=num_users,
        )

    def _check_running(self) -> bool:
        try:
            url = f"{self.endpoint}/v1/models"
            req = urllib.request.Request(url, method="GET")
            req.add_header("Content-Type", "application/json")
            key = self._cfg.admin_api_key or self._cfg.api_key
            if key:
                req.add_header("Authorization", f"Bearer {key}")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

    def _read_model_config(self) -> Optional[dict]:
        recipe_path = self._cfg.config_dir / "recipe_options.json"
        try:
            data = json.loads(recipe_path.read_text())
            for key, val in data.items():
                if key.startswith("user."):
                    llamacpp_args = val.get("llamacpp_args", "")
                    import re
                    np_match = re.search(r"-np\s+(\d+)", llamacpp_args)
                    return {
                        "model": key.removeprefix("user."),
                        "ctx_size": val.get("ctx_size", 0),
                        "num_users": int(np_match.group(1)) if np_match else 1,
                    }
        except (FileNotFoundError, json.JSONDecodeError, PermissionError):
            pass
        return None

    def list_models(self) -> list[dict]:
        """List available models from user_models.json."""
        models_path = self._cfg.config_dir / "user_models.json"
        try:
            data = json.loads(models_path.read_text())
            return [
                {"name": k, **v} for k, v in data.items()
            ]
        except (FileNotFoundError, json.JSONDecodeError, PermissionError):
            return []

    def get_api_info(self) -> dict:
        """Return API endpoint info for dashboard display."""
        return {
            "endpoint": self.endpoint,
            "openai_compatible": f"{self.endpoint}/v1",
            "has_api_key": bool(self._cfg.api_key),
            "has_admin_key": bool(self._cfg.admin_api_key),
            "installed": self.is_installed(),
        }
