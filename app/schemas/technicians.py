"""Technician resource and workload schemas."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import TechnicianStatus


class TechnicianResponse(BaseModel):
    technician_id: str = Field(..., description="Canonical technician identifier (e.g., TECH-01)")
    name: str = Field(..., description="Technician full name")
    status: TechnicianStatus = Field(..., description="Current status: available, assigned, on_job, unavailable")
    skills: List[str] = Field(default_factory=list, description="Skill certifications (e.g., electrical, mechanical, hydraulics)")
    current_job_id: Optional[str] = Field(None, description="Active job ID if currently dispatched")
    estimated_available_at: Optional[datetime] = Field(None, description="Estimated completion timestamp of active job")
