"""HTTP client and integration adapter for ForgeGuard Decision Engine."""
import logging
from typing import Any, Dict, List, Optional
import httpx
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EngineClientError(Exception):
    """Base exception for Engine HTTP client errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


class EngineConnectionError(EngineClientError):
    """Engine service is unreachable or network connection failed."""
    pass


class EngineTimeoutError(EngineClientError):
    """Engine request timed out."""
    pass


class EngineResponseError(EngineClientError):
    """Engine returned non-2xx response or malformed payload."""
    pass


class EngineClient:
    """Async HTTP client communicating with the Decision Engine service."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None, retry_attempts: Optional[int] = None):
        settings: Settings = get_settings()
        self.base_url = (base_url or settings.engine_base_url).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.engine_timeout_seconds
        self.retry_attempts = retry_attempts if retry_attempts is not None else settings.engine_retry_attempts
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        """Returns or instantiates the shared httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={"Accept": "application/json", "User-Agent": "ForgeGuard-Orchestrator/1.0"},
            )
        return self._client

    async def close(self) -> None:
        """Closes the underlying client connection pool."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        allow_retries: bool = False,
    ) -> Dict[str, Any]:
        """Internal request executor with structured error mapping and controlled retries."""
        client = await self.get_client()
        attempts = self.retry_attempts + 1 if allow_retries else 1

        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                response = await client.request(
                    method=method,
                    url=path,
                    json=json_data,
                    params=params,
                )
                # Successful response
                if 200 <= response.status_code < 300:
                    try:
                        return response.json()
                    except Exception:
                        return {"status": "ok", "text": response.text}

                # Non-2xx response from upstream
                error_body: Any = None
                try:
                    error_body = response.json()
                except Exception:
                    error_body = response.text

                logger.warning(
                    f"Engine returned HTTP {response.status_code} for {method} {path}: {error_body}"
                )
                raise EngineResponseError(
                    message=f"Engine returned HTTP {response.status_code}",
                    status_code=response.status_code,
                    details=error_body,
                )

            except (httpx.ConnectError, httpx.NetworkError) as exc:
                last_error = EngineConnectionError(f"Failed to connect to Decision Engine at {self.base_url}: {exc}")
                logger.warning(f"Engine connection failure (attempt {attempt}/{attempts}): {exc}")
            except httpx.TimeoutException as exc:
                last_error = EngineTimeoutError(f"Decision Engine request timed out after {self.timeout}s: {exc}")
                logger.warning(f"Engine timeout (attempt {attempt}/{attempts}): {exc}")
            except EngineResponseError:
                # Do not retry HTTP 4xx or 5xx unless specifically idempotent/desired
                raise

        if last_error:
            raise last_error
        raise EngineClientError(f"Request {method} {path} failed without explicit exception")

    # =========================================================================
    # Contract B: All 13 Engine Endpoints
    # =========================================================================

    # 1) GET /health
    async def get_health(self) -> Dict[str, Any]:
        """Check engine connectivity and readiness."""
        return await self._request("GET", "/health", allow_retries=True)

    # 2) POST /predict
    async def predict(self, reading: Dict[str, Any]) -> Dict[str, Any]:
        """Submit one machine reading and consume its prediction."""
        return await self._request("POST", "/predict", json_data=reading, allow_retries=True)

    # 3) POST /predict/batch
    async def predict_batch(self, readings: List[Dict[str, Any]]) -> Any:
        """Submit a batch of machine readings for replay/shift processing."""
        # Support sending as list or under 'machines'/'readings'
        payload = {"machines": readings} if isinstance(readings, list) else readings
        return await self._request("POST", "/predict/batch", json_data=payload, allow_retries=True)

    # 4) POST /decision/evaluate
    async def evaluate_decision(self, prediction_or_machine: Dict[str, Any]) -> Dict[str, Any]:
        """Convert prediction outputs into engine-authoritative operational alert decisions."""
        return await self._request("POST", "/decision/evaluate", json_data=prediction_or_machine, allow_retries=True)

    # 5) GET /decision/threshold
    async def get_threshold(self) -> Dict[str, Any]:
        """Retrieve available threshold optimization results."""
        return await self._request("GET", "/decision/threshold", allow_retries=True)

    # 6) POST /decision/threshold
    async def optimize_threshold(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Request threshold optimization or refresh with validation labels and costs."""
        return await self._request("POST", "/decision/threshold", json_data=payload, allow_retries=False)

    # 7) POST /schedule/plan
    async def plan_schedule(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Ask the engine to build a shift schedule from predictions/alerts and technician capacity."""
        return await self._request("POST", "/schedule/plan", json_data=payload, allow_retries=False)

    # 8) POST /safety/assess
    async def assess_safety(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Obtain equipment safety assessment before interrupting an active maintenance job."""
        return await self._request("POST", "/safety/assess", json_data=payload, allow_retries=True)

    # 9) POST /schedule/preemption/evaluate
    async def evaluate_preemption(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate emergency preemption without mutating assignments."""
        return await self._request("POST", "/schedule/preemption/evaluate", json_data=payload, allow_retries=True)

    # 10) POST /schedule/preemption/execute
    async def execute_preemption(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an allowed/approved preemption and apply assignment changes (NON-IDEMPOTENT mutation: NO blind retries)."""
        return await self._request("POST", "/schedule/preemption/execute", json_data=payload, allow_retries=False)

    # 11) GET /simulation/state
    async def get_simulation_state(self) -> Dict[str, Any]:
        """Retrieve engine simulation fleet, assignment, queue, or state information."""
        return await self._request("GET", "/simulation/state", allow_retries=True)

    # 12) GET /simulation/events
    async def get_simulation_events(self, since: Any = 0, limit: int = 50) -> Dict[str, Any]:
        """Retrieve engine events using supported since and limit parameters."""
        params = {"since": since, "limit": limit}
        return await self._request("GET", "/simulation/events", params=params, allow_retries=True)

    # 13) POST /simulation/reset
    async def reset_simulation(self) -> Dict[str, Any]:
        """Reset the engine's simulation state and event log when supported."""
        return await self._request("POST", "/simulation/reset", allow_retries=False)
