"""Cost analysis service normalizing engine-supported economic evaluations."""
import logging
from datetime import datetime, timezone
from typing import Optional

from app.clients.engine_client import EngineClient, EngineConnectionError, EngineTimeoutError
from app.schemas.cost_analysis import CostAnalysisResponse, CostOption
from app.services.state_service import StateService, get_state_service

logger = logging.getLogger(__name__)


class CostAnalysisService:
    """Consumes engine threshold and cost configurations to provide economic comparisons."""

    def __init__(self, engine_client: Optional[EngineClient] = None, state_service: Optional[StateService] = None):
        self.engine_client = engine_client or EngineClient()
        self.state_service = state_service or get_state_service()

    async def get_cost_analysis(self) -> CostAnalysisResponse:
        """Retrieves cost breakdown and options comparison without fabricating missing metrics."""
        now = datetime.now(timezone.utc)
        engine_threshold_data = None

        try:
            engine_threshold_data = await self.engine_client.get_threshold()
        except (EngineConnectionError, EngineTimeoutError) as exc:
            logger.warning(f"Engine threshold endpoint unreachable: {exc}")

        # If engine returns threshold optimization results, normalize them
        if engine_threshold_data:
            opt_cost = engine_threshold_data.get("optimal_cost")
            baseline_cost = engine_threshold_data.get("baseline_cost") or engine_threshold_data.get("baseline_comparison")
            conf_matrix = engine_threshold_data.get("confusion_matrix") or {}
            fp_cost = engine_threshold_data.get("cost_fp")
            fn_cost = engine_threshold_data.get("cost_fn")

            options = [
                CostOption(
                    option_id="optimized_policy",
                    label="Engine Optimized Maintenance Dispatch",
                    maintenance_cost=fp_cost if isinstance(fp_cost, (int, float)) else None,
                    downtime_cost=fn_cost if isinstance(fn_cost, (int, float)) else None,
                    delay_risk_cost=None,
                    interruption_cost=None,
                    total_estimated_cost=opt_cost if isinstance(opt_cost, (int, float)) else None,
                    assumptions=[
                        f"Optimal threshold: {engine_threshold_data.get('optimal_threshold', 'configured')}",
                        "Costs based on engine cost model parameters",
                    ],
                ),
            ]

            if baseline_cost is not None and isinstance(baseline_cost, (int, float)):
                options.append(
                    CostOption(
                        option_id="unoptimized_baseline",
                        label="Run-to-Failure Baseline (Unoptimized)",
                        maintenance_cost=None,
                        downtime_cost=baseline_cost,
                        delay_risk_cost=None,
                        interruption_cost=None,
                        total_estimated_cost=baseline_cost,
                        assumptions=["Standard default threshold without cost optimization"],
                    )
                )

            return CostAnalysisResponse(
                currency="INR",
                generated_at=now,
                options=options,
                recommended_option_id="optimized_policy",
                explanation="Threshold optimization minimizes total operational cost across false-positive inspection and false-negative downtime penalties.",
                cost_data_available=True,
                note=None,
            )

        # If engine does not supply threshold/cost figures, report explicit unavailable state
        return CostAnalysisResponse(
            currency="INR",
            generated_at=now,
            options=[],
            recommended_option_id=None,
            explanation="Cost analysis currently unavailable: Decision Engine has not provided threshold optimization data.",
            cost_data_available=False,
            note="Decision Engine endpoint GET /decision/threshold is unreachable or returned empty figures. Values not fabricated.",
        )
