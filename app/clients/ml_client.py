"""Optional client for communicating with a standalone ML Service if deployed separately."""
import logging
from typing import Any, Dict, List, Optional
import httpx
from app.config import Settings, get_settings
from app.clients.engine_client import EngineClientError, EngineConnectionError, EngineTimeoutError

logger = logging.getLogger(__name__)


class MLClient:
    """Async client for standalone ML model prediction service."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        settings: Settings = get_settings()
        self.base_url = (base_url or settings.ml_base_url).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.ml_timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def predict_single(self, reading: Dict[str, Any]) -> Dict[str, Any]:
        """Submit single sensor reading directly to standalone ML service."""
        client = await self.get_client()
        try:
            res = await client.post("/predict", json=reading)
            res.raise_for_status()
            return res.json()
        except httpx.ConnectError as exc:
            raise EngineConnectionError(f"Cannot reach ML service at {self.base_url}: {exc}")
        except httpx.TimeoutException as exc:
            raise EngineTimeoutError(f"ML service timed out: {exc}")
        except httpx.HTTPStatusError as exc:
            raise EngineClientError(f"ML service HTTP error: {exc.response.status_code}")

    async def predict_batch(self, readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Submit batch sensor readings directly to standalone ML service."""
        client = await self.get_client()
        try:
            res = await client.post("/predict/batch", json={"readings": readings})
            res.raise_for_status()
            return res.json()
        except httpx.ConnectError as exc:
            raise EngineConnectionError(f"Cannot reach ML service at {self.base_url}: {exc}")
        except httpx.TimeoutException as exc:
            raise EngineTimeoutError(f"ML service timed out: {exc}")
        except httpx.HTTPStatusError as exc:
            raise EngineClientError(f"ML service HTTP error: {exc.response.status_code}")
