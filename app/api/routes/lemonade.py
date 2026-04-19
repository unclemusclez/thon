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

"""REST API routes for Lemonade server monitoring."""

from fastapi import APIRouter, HTTPException

from app.models import LemonadeStatus
from app.services.lemonade_service import LemonadeService

router = APIRouter(prefix="/api/lemonade", tags=["lemonade"])


def _get_service() -> LemonadeService:
    from app.main import get_lemonade_service
    return get_lemonade_service()


@router.get("/status", response_model=LemonadeStatus)
async def lemonade_status() -> LemonadeStatus:
    """Get current Lemonade server status snapshot."""
    svc = _get_service()
    return svc.get_status()


@router.get("/models")
async def lemonade_models() -> dict:
    """List available Lemonade models."""
    svc = _get_service()
    return {"models": svc.list_models()}


@router.get("/api-info")
async def lemonade_api_info() -> dict:
    """Get Lemonade API endpoint information."""
    svc = _get_service()
    return svc.get_api_info()
