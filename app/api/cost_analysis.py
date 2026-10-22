"""Cost analysis and trade-off comparison endpoints."""
from fastapi import APIRouter, Depends

from app.api.dependencies import get_cost_analysis_service
from app.schemas.cost_analysis import CostAnalysisResponse
from app.services.cost_analysis_service import CostAnalysisService

router = APIRouter(prefix="/api/cost-analysis", tags=["Cost Analysis"])


@router.get("", response_model=CostAnalysisResponse)
async def get_cost_analysis(
    cost_service: CostAnalysisService = Depends(get_cost_analysis_service),
):
    """Return engine-supported cost comparisons, components, and assumptions.

    RULE:
    If engine data is missing, returns an explicit unavailable result. Figures are not fabricated.
    """
    return await cost_service.get_cost_analysis()
