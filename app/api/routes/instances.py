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

"""REST API routes for sandbox instance management."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import AppConfig
from app.exceptions import (
    SandboxCreateError,
    SandboxNotFoundError,
    SandboxOperationError,
)
from app.models import InstanceInfo, InstanceState, UserInfo
from app.services.sandbox_service import SandboxService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/instances", tags=["instances"])


class CreateInstanceRequest(BaseModel):
    group: str = "default"
    username: str = "workspace"
    port: int = 8443
    secure: bool = False


class BulkActionRequest(BaseModel):
    instance_ids: list[str]


class RenewRequest(BaseModel):
    timeout_minutes: int = 60


class InstancesListResponse(BaseModel):
    instances: list[InstanceInfo]
    total: int
    page: int
    page_size: int


def _get_service() -> SandboxService:
    from app.main import get_sandbox_service
    return get_sandbox_service()


@router.get("", response_model=InstancesListResponse)
async def list_instances(
    state: Optional[list[InstanceState]] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> InstancesListResponse:
    """List all managed sandbox instances."""
    svc = _get_service()
    instances, total = await svc.list_instances(
        states=state,
        metadata_filter={"managed-by": "thon-client"},
        page=page,
        page_size=page_size,
    )
    return InstancesListResponse(
        instances=instances,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{instance_id}", response_model=InstanceInfo)
async def get_instance(instance_id: str) -> InstanceInfo:
    """Get details for a single instance."""
    svc = _get_service()
    try:
        return await svc.get_instance(instance_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found: {e}")


@router.post("", response_model=InstanceInfo, status_code=201)
async def create_instance(req: CreateInstanceRequest) -> InstanceInfo:
    """Create a new VS Code sandbox instance."""
    svc = _get_service()
    user =UserInfo(group=req.group, username=req.username)
    try:
        return await svc.create_instance(
            user=user,
            port=req.port,
            secure=req.secure,
        )
    except SandboxCreateError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create instance: {e}")


@router.post("/{instance_id}/pause")
async def pause_instance(instance_id: str) -> dict:
    """Pause a running instance."""
    svc = _get_service()
    try:
        await svc.pause_instance(instance_id)
        return {"status": "paused", "id": instance_id}
    except SandboxOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{instance_id}/resume")
async def resume_instance(instance_id: str) -> InstanceInfo:
    """Resume a paused instance."""
    svc = _get_service()
    try:
        return await svc.resume_instance(instance_id)
    except SandboxOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{instance_id}")
async def kill_instance(instance_id: str) -> dict:
    """Terminate an instance permanently."""
    svc = _get_service()
    try:
        await svc.kill_instance(instance_id)
        return {"status": "terminated", "id": instance_id}
    except SandboxOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{instance_id}/renew")
async def renew_instance(instance_id: str, req: RenewRequest = RenewRequest()) -> dict:
    """Extend an instance's TTL."""
    svc = _get_service()
    try:
        await svc.renew_instance(instance_id, timeout_minutes=req.timeout_minutes)
        return {"status": "renewed", "id": instance_id, "timeout_minutes": req.timeout_minutes}
    except SandboxOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bulk/pause")
async def bulk_pause(req: BulkActionRequest) -> dict:
    """Pause multiple instances at once."""
    svc = _get_service()
    results = []
    for sid in req.instance_ids:
        try:
            await svc.pause_instance(sid)
            results.append({"id": sid, "status": "paused"})
        except SandboxOperationError as e:
            results.append({"id": sid, "status": "error", "error": str(e)})
    return {"results": results}


@router.post("/bulk/resume")
async def bulk_resume(req: BulkActionRequest) -> dict:
    """Resume multiple instances at once."""
    svc = _get_service()
    results = []
    for sid in req.instance_ids:
        try:
            info = await svc.resume_instance(sid)
            results.append({"id": sid, "status": "resumed", "state": info.state.value})
        except SandboxOperationError as e:
            results.append({"id": sid, "status": "error", "error": str(e)})
    return {"results": results}


@router.post("/bulk/kill")
async def bulk_kill(req: BulkActionRequest) -> dict:
    """Terminate multiple instances at once."""
    svc = _get_service()
    results = []
    for sid in req.instance_ids:
        try:
            await svc.kill_instance(sid)
            results.append({"id": sid, "status": "terminated"})
        except SandboxOperationError as e:
            results.append({"id": sid, "status": "error", "error": str(e)})
    return {"results": results}
