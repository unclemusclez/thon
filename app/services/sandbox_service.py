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

"""Sandbox service wrapping OpenSandbox SDK SandboxManager for fleet operations."""

import asyncio
import logging
import os
import secrets
from datetime import timedelta
from typing import Optional

from opensandbox import Sandbox, SandboxManager
from opensandbox.config import ConnectionConfig
from opensandbox.models.execd import RunCommandOpts
from opensandbox.models.sandboxes import Host, Volume, SandboxFilter

from app.config import AppConfig, SandboxConfig
from app.exceptions import (
    SandboxCreateError,
    SandboxNotFoundError,
    SandboxOperationError,
)
from app.models import InstanceInfo, InstanceState, UserInfo

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8443


class SandboxService:
    """High-level service for managing VS Code sandbox instances.

    Wraps the OpenSandbox SDK's ``SandboxManager`` for fleet-level operations
    (list, kill, pause, resume) and ``Sandbox`` for single-instance interaction
    (create, run commands, get endpoints).
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._sandbox_cfg: SandboxConfig = config.sandbox
        self._manager: Optional[SandboxManager] = None

    async def _get_manager(self) -> SandboxManager:
        """Lazy-initialize and return the shared SandboxManager."""
        if self._manager is None or self._manager._closed:
            conn = ConnectionConfig(
                domain=self._sandbox_cfg.domain,
                api_key=self._sandbox_cfg.api_key,
                request_timeout=timedelta(seconds=self._sandbox_cfg.request_timeout_seconds),
            )
            self._manager = await SandboxManager.create(conn)
        return self._manager

    async def close(self) -> None:
        """Release the manager transport."""
        if self._manager and not self._manager._closed:
            await self._manager.close()
            self._manager = None

    # ── Fleet Operations ──────────────────────────────────────────────

    async def list_instances(
        self,
        states: Optional[list[InstanceState]] = None,
        metadata_filter: Optional[dict[str, str]] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[InstanceInfo], int]:
        """List sandbox instances with optional filtering and pagination.

        Returns:
            Tuple of (instances, total_items).
        """
        mgr = await self._get_manager()
        state_strs = [s.value for s in states] if states else None
        f = SandboxFilter(states=state_strs, metadata=metadata_filter, page=page, page_size=page_size)
        result = await mgr.list_sandbox_infos(f)

        instances = []
        for info in result.sandbox_infos:
            meta = info.metadata or {}
            instances.append(
                InstanceInfo(
                    id=info.id,
                    user=UserInfo(
                        group=meta.get("group", "default"),
                        username=meta.get("username", "workspace"),
                    ),
                    state=InstanceState(info.status.state),
                    port=int(meta.get("port", DEFAULT_PORT)),
                    endpoint=None,
                    image=info.image,
                    created_at=info.created_at,
                    expires_at=info.expires_at,
                    metadata=meta,
                )
            )
        return instances, result.pagination.total_items if result.pagination else len(instances)

    async def get_instance(self, sandbox_id: str) -> InstanceInfo:
        """Fetch details for a single sandbox instance."""
        mgr = await self._get_manager()
        info = await mgr.get_sandbox_info(sandbox_id)
        meta = info.metadata or {}
        return InstanceInfo(
            id=info.id,
            user=UserInfo(
                group=meta.get("group", "default"),
                username=meta.get("username", "workspace"),
            ),
            state=InstanceState(info.status.state),
            port=int(meta.get("port", DEFAULT_PORT)),
            image=info.image,
            created_at=info.created_at,
            expires_at=info.expires_at,
            metadata=meta,
        )

    async def pause_instance(self, sandbox_id: str) -> None:
        """Pause a running sandbox (retains state)."""
        mgr = await self._get_manager()
        try:
            await mgr.pause_sandbox(sandbox_id)
        except Exception as e:
            raise SandboxOperationError(f"Failed to pause {sandbox_id}: {e}") from e

    async def resume_instance(self, sandbox_id: str) -> InstanceInfo:
        """Resume a paused sandbox and return updated info."""
        mgr = await self._get_manager()
        try:
            await mgr.resume_sandbox(sandbox_id)
        except Exception as e:
            raise SandboxOperationError(f"Failed to resume {sandbox_id}: {e}") from e
        return await self.get_instance(sandbox_id)

    async def kill_instance(self, sandbox_id: str) -> None:
        """Terminate a sandbox instance permanently."""
        mgr = await self._get_manager()
        try:
            await mgr.kill_sandbox(sandbox_id)
        except Exception as e:
            raise SandboxOperationError(f"Failed to kill {sandbox_id}: {e}") from e

    async def renew_instance(self, sandbox_id: str, timeout_minutes: int = 60) -> None:
        """Extend a sandbox's TTL."""
        mgr = await self._get_manager()
        try:
            await mgr.renew_sandbox(sandbox_id, timedelta(minutes=timeout_minutes))
        except Exception as e:
            raise SandboxOperationError(f"Failed to renew {sandbox_id}: {e}") from e

    # ── Instance Creation ────────────────────────────────────────────

    async def create_instance(
        self,
        user: UserInfo,
        port: int = DEFAULT_PORT,
        secure: bool = False,
        workspace_dir: Optional[str] = None,
        timeout: Optional[timedelta] = None,
    ) -> InstanceInfo:
        """Create a new VS Code sandbox instance and start code-server.

        Args:
            user: Group/username for this instance.
            port: Port for code-server inside the container.
            secure: Enable password authentication.
            workspace_dir: Host path for persistent bind mount.
            timeout: Sandbox lifetime (None = indefinite).

        Returns:
            InstanceInfo with endpoint and state.
        """
        env = {"PYTHON_VERSION": "3.12"}
        volumes: list[Volume] | None = None

        if workspace_dir:
            host_path = os.path.join(workspace_dir, user.workspace)
            os.makedirs(host_path, exist_ok=True)
            volumes = [
                Volume(
                    name=f"workspace-{user.group}-{user.username}",
                    host=Host(path=host_path),
                    mount_path="/workspace",
                )
            ]

        metadata = {
            "group": user.group,
            "username": user.username,
            "port": str(port),
            "managed-by": "vscode-remote-client",
        }

        sandbox = await Sandbox.create(
            self._sandbox_cfg.image,
            connection_config=ConnectionConfig(
                domain=self._sandbox_cfg.domain,
                api_key=self._sandbox_cfg.api_key,
                request_timeout=timedelta(seconds=self._sandbox_cfg.request_timeout_seconds),
            ),
            env=env,
            timeout=timeout,
            volumes=volumes,
            metadata=metadata,
        )

        endpoint = await sandbox.get_endpoint(port)
        endpoint_str = endpoint.endpoint
        endpoint_port = self._parse_endpoint_port(endpoint_str)

        password = None
        if secure:
            password = secrets.token_urlsafe(24)

        if not volumes:
            await sandbox.commands.run("mkdir -p /workspace")
            await sandbox.commands.run("chown -R vscode:vscode /workspace")

        auth_flag = "--auth password" if secure else "--auth none"
        code_server_cmd = (
            f"code-server --bind-addr 0.0.0.0:{port} "
            f"{auth_flag} --disable-telemetry /workspace"
        )

        if secure and password:
            config_dir = "/home/vscode/.config/code-server"
            config_content = (
                f"bind-addr: 0.0.0.0:{port}\n"
                f"auth: password\n"
                f"password: {password}\n"
                f"cert: false\n"
            )
            await sandbox.commands.run(f"mkdir -p {config_dir}")
            write_cmd = (
                f"cat > {config_dir}/config.yaml << 'CONFIGEOF'\n"
                f"{config_content}CONFIGEOF"
            )
            await sandbox.commands.run(write_cmd)

        await sandbox.commands.run(
            code_server_cmd,
            opts=RunCommandOpts(background=True),
        )

        return InstanceInfo(
            id=sandbox.id if hasattr(sandbox, "id") else "",
            user=user,
            state=InstanceState.RUNNING,
            port=endpoint_port,
            endpoint=endpoint_str,
            password=password,
            image=self._sandbox_cfg.image,
            metadata=metadata,
        )

    async def create_instances_for_group(
        self,
        users: list[UserInfo],
        start_port: int = DEFAULT_PORT,
        secure: bool = False,
        workspace_dir: Optional[str] = None,
        timeout: Optional[timedelta] = None,
    ) -> list[InstanceInfo]:
        """Create multiple instances concurrently for a list of users."""
        tasks = []
        for i, user in enumerate(users):
            tasks.append(
                self.create_instance(
                    user=user,
                    port=start_port + i,
                    secure=secure,
                    workspace_dir=workspace_dir,
                    timeout=timeout,
                )
            )
        return list(await asyncio.gather(*tasks))

    # ── Bulk Operations ───────────────────────────────────────────────

    async def kill_all(self, metadata_filter: Optional[dict[str, str]] = None) -> int:
        """Kill all instances matching filter. Returns count killed."""
        instances, total = await self.list_instances(metadata_filter=metadata_filter)
        count = 0
        for inst in instances:
            if inst.state in (InstanceState.RUNNING, InstanceState.PAUSED):
                try:
                    await self.kill_instance(inst.id)
                    count += 1
                except SandboxOperationError as exc:
                    logger.warning("Failed to kill %s: %s", inst.id, exc)
        return count

    # ── Internal Helpers ─────────────────────────────────────────────

    @staticmethod
    def _parse_endpoint_port(endpoint_str: str) -> int:
        host_port_part = endpoint_str.split("/", 1)[0]
        if ":" in host_port_part:
            return int(host_port_part.rsplit(":", 1)[1])
        return 80
