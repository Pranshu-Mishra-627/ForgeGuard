"""Preemption evaluation and execution schemas."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import PreemptionDecision, SafetyOutcome


class PreemptionEvaluateRequest(BaseModel):
    incoming_job_id: str = Field(..., description="ID of urgent incoming job requiring dispatch")
    technician_id: str = Field(..., description="ID of busy technician under consideration")


class PreemptionAlternative(BaseModel):
    action: str = Field(..., description="Action alternative: finish_current_job, preempt, assign_other_technician, defer_incoming_job")
    estimated_total_cost: Optional[float] = Field(None, description="Projected cost impact in currency units")
    feasible: bool = Field(..., description="Whether this operational option is currently feasible")
    reason: str = Field(..., description="Explanation of trade-offs and feasibility")


class PreemptionEvaluateResponse(BaseModel):
    decision: PreemptionDecision = Field(..., description="Preemption recommendation: allow, deny, or needs_review")
    safe_to_interrupt: bool = Field(..., description="Hard safety gate indicator. True ONLY if safety is explicitly confirmed SAFE")
    reason_codes: List[str] = Field(default_factory=list, description="Machine-readable rationale codes")
    explanation: str = Field(..., description="Clear operator explanation of evaluation result")
    estimated_interruption_cost: Optional[float] = Field(None, description="Direct cost of interrupting current active job")
    alternatives: List[PreemptionAlternative] = Field(default_factory=list, description="Feasible operational alternatives")
    evaluation_id: str = Field(..., description="Stable evaluation token for guarded execution")
    current_job_id: str = Field(..., description="Job considered for interruption")
    incoming_job_id: str = Field(..., description="Urgent job requesting immediate dispatch")
    safety_outcome: SafetyOutcome = Field(..., description="Safety assessment outcome: SAFE_TO_INTERRUPT, UNSAFE_TO_INTERRUPT, INDETERMINATE")
    safety_evidence: List[str] = Field(default_factory=list, description="Signals supporting safety assessment")
    missing_signals: List[str] = Field(default_factory=list, description="Missing safety inputs if any")
    conflicting_signals: List[str] = Field(default_factory=list, description="Conflicting sensor signals if any")
    created_at: datetime = Field(..., description="Evaluation timestamp")
    requires_human_approval: bool = Field(default=False, description="Whether manual supervisor sign-off is required")


class PreemptionExecuteRequest(BaseModel):
    evaluation_id: str = Field(..., description="Valid, unexpired evaluation ID from evaluation step")
    incoming_job_id: str = Field(..., description="Urgent incoming job ID matching the evaluation")
    approval_granted: bool = Field(default=False, description="Explicit operator approval flag when review required")


class PreemptionExecuteResponse(BaseModel):
    success: bool = Field(..., description="Whether preemption was successfully applied to operational state")
    status: str = Field(default="executed", description="Resulting status: executed or denied")
    preemption_executed: bool = Field(..., description="Confirmation that assignment change occurred")
    interrupted_job_id: str = Field(..., description="ID of job transitioned to paused state")
    incoming_job_id: str = Field(..., description="ID of urgent job transitioned to in_progress state")
    technician_id: str = Field(..., description="Technician who received the emergency assignment")
    executed_at: datetime = Field(..., description="Execution timestamp")
    message: str = Field(..., description="Operator summary of outcome")
