"""FastAPI dependency providers for injection and test mocking."""
from fastapi import Depends
from app.clients.engine_client import EngineClient
from app.services.cost_analysis_service import CostAnalysisService
from app.services.prediction_service import PredictionService
from app.services.preemption_service import PreemptionService
from app.services.safety_service import SafetyService
from app.services.scheduling_service import SchedulingService
from app.services.simulation_service import SimulationService
from app.services.state_service import StateService, get_state_service


def get_engine_client() -> EngineClient:
    """Provides EngineClient instance."""
    return EngineClient()


def get_safety_service(
    engine_client: EngineClient = Depends(get_engine_client),
    state_service: StateService = Depends(get_state_service),
) -> SafetyService:
    return SafetyService(engine_client=engine_client, state_service=state_service)


def get_prediction_service(
    engine_client: EngineClient = Depends(get_engine_client),
    state_service: StateService = Depends(get_state_service),
) -> PredictionService:
    return PredictionService(engine_client=engine_client, state_service=state_service)


def get_scheduling_service(
    engine_client: EngineClient = Depends(get_engine_client),
    state_service: StateService = Depends(get_state_service),
) -> SchedulingService:
    return SchedulingService(engine_client=engine_client, state_service=state_service)


def get_preemption_service(
    engine_client: EngineClient = Depends(get_engine_client),
    state_service: StateService = Depends(get_state_service),
    safety_service: SafetyService = Depends(get_safety_service),
) -> PreemptionService:
    return PreemptionService(
        engine_client=engine_client,
        state_service=state_service,
        safety_service=safety_service,
    )


def get_simulation_service(
    engine_client: EngineClient = Depends(get_engine_client),
    state_service: StateService = Depends(get_state_service),
) -> SimulationService:
    return SimulationService(engine_client=engine_client, state_service=state_service)


def get_cost_analysis_service(
    engine_client: EngineClient = Depends(get_engine_client),
    state_service: StateService = Depends(get_state_service),
) -> CostAnalysisService:
    return CostAnalysisService(engine_client=engine_client, state_service=state_service)
