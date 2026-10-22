# ForgeGuard Orchestration Backend

Cost-aware predictive maintenance command center backend coordinating Machine Learning inferences, Decision Engine evaluations, shift scheduling, hard safety gates, guarded emergency preemption, and real-time state management.

---

## 1. Architecture and Information Flow

```
+-------------------------------------------------------------+
|               Machine Readings / Replay Data                |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|              ML Service (Failure Prediction)                |
|       - Failure probability (0.0 - 1.0)                     |
|       - Predicted failure mode (TWF, HDF, PWF, OSF, RNF)    |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|             Decision Engine (Operational Policy)            |
|       - Cost-optimal threshold optimization                 |
|       - Alert eligibility & priority ranking                |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|           Equipment Safety Assessment (Hard Gate)           |
|       - Telemetry & signal verification                     |
|       - Outcome: SAFE_TO_INTERRUPT | UNSAFE | INDETERMINATE |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|          Shift Scheduling & Preemption Evaluation           |
|       - Shift capacity allocation (Technician slots)        |
|       - Emergency preemption evaluation (Read-only)         |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|         ForgeGuard Orchestration Backend (This Service)     |
|       - Canonical machine, job, and technician state        |
|       - Progress-preserving preemption execution            |
|       - Audit trail logging & deduplication                 |
|       - Resilient failure recovery & schema normalization   |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                      UI Command Center                      |
|       - Operations overview, Kanban boards, Gantt schedules |
|       - Safety-gated preemption dialogues                   |
|       - Economic cost comparisons                           |
+-------------------------------------------------------------+
```

---

## 2. Component Ownership Boundaries

| Component | Responsibility & Ownership | Prohibited Actions |
|---|---|---|
| **ML Service** | Machine failure predictions, failure probabilities, model versioning, feature transformations. | Never makes operational dispatch or cost decisions. |
| **Decision Engine** | Cost model calculations, alert thresholds, shift ranking/allocation, equipment safety assessment, preemption policy. | Never manages authoritative UI sessions or database state. |
| **Orchestration Backend** *(This Service)* | UI-facing REST API, calling ML & Engine HTTP endpoints, coordinating end-to-end pipeline, canonical machine/job/technician state, enforcing hard safety gate invariants, audit event history. | Never duplicates engine decision formulas locally or fabricates unsupported telemetry/costs. |
| **Frontend / UI** | Visual rendering, user controls, Gantt/Kanban timelines, displaying backend decisions and safety justifications. | Never implements authoritative scheduling, cost, priority, or safety formulas. |

---

## 3. Environment Setup

### Prerequisites
- Python 3.10+ (tested on Python 3.11.9)
- Virtual environment (`venv`)

### Installation
```bash
# Clone or navigate to the orchestration directory
cd D:\ForgeGuard-orchestration

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 4. Environment Variables (`.env.example`)

Create a `.env` file in the project root:

```env
# Orchestration Server Configuration
ORCHESTRATION_HOST=0.0.0.0
ORCHESTRATION_PORT=8000
ENVIRONMENT=development
LOG_LEVEL=INFO

# Upstream Decision Engine Service
ENGINE_BASE_URL=http://localhost:8001
ENGINE_TIMEOUT_SECONDS=10.0
ENGINE_RETRY_ATTEMPTS=2

# Upstream ML Service (if separate from Engine)
ML_BASE_URL=http://localhost:8002
ML_TIMEOUT_SECONDS=10.0

# CORS Allowed Origins (comma-separated or JSON list)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173

# Simulation Settings
DEFAULT_SIMULATION_SPEED=1.0
```

---

## 5. Running the Backend Service

```bash
# Using uvicorn directly
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Or via Python module
python -m app.main
```

Once running:
- **Interactive OpenAPI Documentation (Swagger UI)**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

---

## 6. Running Automated Tests

Run the complete test suite:
```bash
python -m pytest
```

Run focused test categories:
```bash
# Unit tests (configuration, state invariants, safety gate rules)
python -m pytest tests/unit -v

# Engine contract tests (covering all 13 Engine HTTP endpoints)
python -m pytest tests/contract -v

# API tests (verifying all UI endpoints, status codes, and error formatting)
python -m pytest tests/api -v

# Integration tests (end-to-end pipeline and resilience under engine offline/timeouts)
python -m pytest tests/integration -v
```

---

## 7. UI-Facing API Route Table (Contract A)

All endpoints exposed to the frontend:

| Method | Endpoint | Description | Key Request / Response Elements |
|---|---|---|---|
| `GET` | `/health` | Lightweight service health check | Returns `{status: "healthy", service: "forgeguard-orchestration"}`. Never fails when upstream engine is down. |
| `GET` | `/api/status` | Detailed system & dependency connectivity | Reports orchestration status, simulation state, and upstream engine connection status. |
| `GET` | `/api/machines` | Fleet inventory with status and predictions | Returns array of machines with `failure_probability`, `predicted_failure_mode`, `safety_status`, and `active_job_id`. |
| `GET` | `/api/machines/{machine_id}` | Detailed machine telemetry and audit events | Returns machine detail, sensor readings, and recent audit trail events. |
| `POST` | `/api/machines/{machine_id}/predict` | Submit reading & evaluate decision | Ingests sensor reading, queries Engine `/predict` and `/decision/evaluate`, and updates state. |
| `GET` | `/api/jobs` | Maintenance jobs across all statuses | Filterable by `status` (`queued`, `assigned`, `in_progress`, `paused`, `completed`, `blocked`) and `machine_id`. |
| `GET` | `/api/jobs/{job_id}` | Detailed job view with timeline | Returns job progress, elapsed work time, assigned technician, and historical timeline. |
| `GET` | `/api/technicians` | Technician roster and availability | Filterable by status (`available`, `assigned`, `on_job`, `unavailable`). |
| `GET` | `/api/schedule` | Active shift maintenance schedule | Returns scheduled assignments, planned start times, priority scores, and capacity summary. |
| `POST` | `/api/schedule/replan` | Recompute schedule through Engine | Submits machine alerts to Engine `/schedule/plan`. Retains old schedule if engine fails. |
| `POST` | `/api/jobs/{job_id}/preemption/evaluate` | Evaluate emergency preemption | Strictly read-only evaluation. Evaluates equipment safety and engine policy. Safety is a hard gate. |
| `POST` | `/api/jobs/{job_id}/preemption/execute` | Execute approved preemption | Re-validates safety and freshness. Preserves interrupted job progress and reassigns technician. |
| `GET` | `/api/events` | Audit trail and simulation event log | Paginated event history filterable by `since`, `limit`, `machine_id`, `job_id`, and `severity`. |
| `GET` | `/api/cost-analysis` | Economic cost and threshold comparison | Normalized cost breakdown from engine. Marks missing metrics explicitly without fabricating numbers. |
| `GET` | `/api/simulation/state` | Current simulation clock & status | Returns simulation status (`running`, `paused`, `stopped`), mode, simulated wall clock, and step count. |
| `POST` | `/api/simulation/start` | Start replay or demo scenario | Request body: `{mode: "replay", speed: 1.0, scenario_id: "baseline"}`. |
| `POST` | `/api/simulation/pause` | Pause simulation progression | Pauses simulated time advancement. |
| `POST` | `/api/simulation/resume` | Resume paused simulation | Resumes clock progression. |
| `POST` | `/api/simulation/step` | Advance simulation by N steps | Request body: `{steps: 1}`. Advances simulated clock by N minutes. |
| `POST` | `/api/simulation/reset` | Reset state to canonical baseline | Clears simulation mutations and restores documented baseline. Calls engine reset if connected. |
| `POST` | `/api/simulation/inject-failure` | Inject scenario failure | Clearly-labeled demo control. Injects abnormal sensor readings and creates an urgent maintenance job. |

---

## 8. Engine-Facing API Route Inventory (Contract B)

Called by our backend HTTP adapter (`app/clients/engine_client.py`):

| Method | Engine Route | Purpose & Orchestration Usage |
|---|---|---|
| `GET` | `/health` | Connectivity and readiness probe for Decision Engine. |
| `POST` | `/predict` | Ingests single machine reading and returns ML prediction. |
| `POST` | `/predict/batch` | Ingests multiple machine readings for replay/shift batch processing while preserving machine IDs. |
| `POST` | `/decision/evaluate` | Evaluates predicted probability against configured threshold and cost model. |
| `GET` | `/decision/threshold` | Retrieves optimal threshold, confusion matrix, and cost comparison curves. |
| `POST` | `/decision/threshold` | Triggers threshold optimization using validation sets and false-positive/negative costs. |
| `POST` | `/schedule/plan` | Generates prioritized shift maintenance schedule based on alerted machines and technician capacity. |
| `POST` | `/safety/assess` | Equipment safety assessment determining whether an active job is safe to interrupt. |
| `POST` | `/schedule/preemption/evaluate` | Evaluates emergency preemption feasibility without mutating state or assignments. |
| `POST` | `/schedule/preemption/execute` | Applies approved preemption and reassigns technician (non-idempotent mutation: no blind retries). |
| `GET` | `/simulation/state` | Reads upstream simulation status and fleet counters if supported by engine. |
| `GET` | `/simulation/events` | Retrieves engine-side simulation events using `since` and `limit` cursors. |
| `POST` | `/simulation/reset` | Clears engine-side simulation state and event logs. |

---

## 9. Safety and Preemption Workflow

Equipment safety is enforced as an **uncompromised hard gate**:

```
+-------------------------------------------------------------+
|          Incoming Critical Job (e.g. M-03 Failure)          |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|               POST /safety/assess (Engine)                  |
+-------------------------------------------------------------+
                              |
       +----------------------+----------------------+
       |                                             |
       v (SAFE_TO_INTERRUPT)                         v (UNSAFE or INDETERMINATE)
+-------------------------------+             +-------------------------------+
|  POST /schedule/preemption/   |             |  Preemption DENIED            |
|  evaluate                     |             |  - safe_to_interrupt = False  |
|  - safe_to_interrupt = True   |             |  - decision = DENY            |
|  - decision = ALLOW or        |             |  - Execution BLOCKED          |
|    NEEDS_REVIEW               |             |  - Suggests: finish current   |
|  - Generates evaluation_id    |             |    job or defer incoming job  |
+-------------------------------+             +-------------------------------+
       |
       v
+-------------------------------------------------------------+
|         Human Approval Granted (if review required)         |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|               POST /schedule/preemption/execute             |
|       1. Verify evaluation_id exists and unexpired          |
|       2. Re-validate current job is still in progress       |
|       3. Call Engine /schedule/preemption/execute           |
|       4. Atomically pause current job (PROGRESS PRESERVED)  |
|       5. Dispatch technician to urgent incoming job         |
|       6. Atomically update schedule & record audit event    |
+-------------------------------------------------------------+
```

### Safety Invariants Enforced
1. **Never override safety with urgency or cost**: Even if an incoming job is marked `CRITICAL` or promises large savings, an `UNSAFE` or `INDETERMINATE` assessment strictly results in `DENY`.
2. **Missing, stale, or conflicting telemetry is never safe**: Any missing telemetry sensor automatically fails closed to `INDETERMINATE`.
3. **Progress preservation**: When an active job (e.g., `JOB-101`) is preempted, its `elapsed_minutes` (e.g., 25 min) and `progress_percent` (e.g., 41%) are preserved and stored under a `paused` status with an explicit `pause_reason`.
4. **Evaluation is strictly read-only**: Calling `/evaluate` will never mutate job assignments or change technician status.

---

## 10. State Persistence & Process Lifecycle

- The current implementation maintains canonical operational state **in-memory** within `app/services/state_service.py` protected by an `asyncio.Lock` for atomic operations.
- State is process-local and resets to the canonical baseline upon server restart or when `POST /api/simulation/reset` is invoked.
- Stable alphanumeric IDs (`M-01` through `M-06`, `TECH-01` through `TECH-03`, `JOB-101`, `JOB-102`) ensure idempotency and UI consistency.

---

## 11. Known Gaps, Unsupported Capabilities & Status

1. **Standalone Engine HTTP Server**:
   - The Decision Engine logic is currently present as a Python library in `origin/feature/decision-engine` (`engine/cost_model.py`, `engine/threshold.py`, `engine/scheduler.py`, etc.).
   - Our integration adapter is fully written against the engine specification in `ForgeGuard_HTTP_Endpoints_Reference.txt`. Contract tests and integration tests use a verified mock client and HTTP mock transport.
   - When the standalone engine FastAPI service is deployed, configure `ENGINE_BASE_URL` in `.env`.
2. **No Invented Metrics**:
   - Remaining Useful Life (`remaining_useful_life_hours`) is returned as `null` because the baseline classification model outputs failure probability, not continuous RUL.
   - Cost estimates: If `/decision/threshold` does not supply cost breakdown data, `/api/cost-analysis` explicitly sets `cost_data_available: false` rather than inventing financial numbers.

---

## 12. Example cURL Requests

### Check Service Health
```bash
curl -X GET http://localhost:8000/health
```

### Check System & Engine Connectivity
```bash
curl -X GET http://localhost:8000/api/status
```

### List Monitored Machines
```bash
curl -X GET http://localhost:8000/api/machines
```

### Ingest Sensor Reading (Workflow A)
```bash
curl -X POST http://localhost:8000/api/machines/M-01/predict \
  -H "Content-Type: application/json" \
  -d '{
    "air_temperature": 298.5,
    "process_temperature": 308.9,
    "rotational_speed": 1500,
    "torque": 40.0,
    "tool_wear": 220,
    "machine_type": "M"
  }'
```

### Replan Shift Schedule (Workflow C)
```bash
curl -X POST http://localhost:8000/api/schedule/replan \
  -H "Content-Type: application/json" \
  -d '{"reason": "shift_start"}'
```

### Evaluate Preemption (Workflow D)
```bash
curl -X POST http://localhost:8000/api/jobs/JOB-101/preemption/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "incoming_job_id": "JOB-102",
    "technician_id": "TECH-01"
  }'
```

### Execute Preemption (Workflow E)
```bash
curl -X POST http://localhost:8000/api/jobs/JOB-101/preemption/execute \
  -H "Content-Type: application/json" \
  -d '{
    "evaluation_id": "eval-12345678",
    "incoming_job_id": "JOB-102",
    "approval_granted": true
  }'
```

### Inject Demo Failure Scenario
```bash
curl -X POST http://localhost:8000/api/simulation/inject-failure \
  -H "Content-Type: application/json" \
  -d '{
    "machine_id": "M-03",
    "scenario": "power_failure"
  }'
```
