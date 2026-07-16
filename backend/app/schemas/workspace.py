from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkspaceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    settings: Dict[str, Any] = Field(default_factory=dict)


class WorkspaceCreate(WorkspaceBase):
    pass


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    settings: Optional[Dict[str, Any]] = None


class SavedFilter(BaseModel):
    id: str
    name: str
    description: str
    criteria: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SavedFilterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1024)
    criteria: Dict[str, Any] = Field(default_factory=dict)


class SavedFilterUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1024)
    criteria: Optional[Dict[str, Any]] = None


class SavedCandidateList(BaseModel):
    id: str
    name: str
    description: str
    candidate_ids: List[str]
    created_at: datetime
    updated_at: datetime


class SavedCandidateListCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1024)
    candidate_ids: List[str] = Field(default_factory=list)


class SavedCandidateListUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1024)
    candidate_ids: Optional[List[str]] = None


class RecruiterPreferencesRequest(BaseModel):
    preferences: Dict[str, Any] = Field(default_factory=dict)


class RecruiterPreferencesResponse(BaseModel):
    preferences: Dict[str, Any]
    updated_at: datetime


class DashboardWidget(BaseModel):
    id: str
    widget_type: str
    title: str
    settings: Dict[str, Any]
    enabled: bool
    order: int
    created_at: datetime
    updated_at: datetime


class DashboardWidgetCreate(BaseModel):
    widget_type: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=255)
    settings: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    order: int = 0


class DashboardWidgetUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    settings: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    order: Optional[int] = None


class WorkspaceResponse(WorkspaceBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    saved_filters: List[SavedFilter]
    saved_candidate_lists: List[SavedCandidateList]
    recruiter_preferences: Dict[str, RecruiterPreferencesResponse]
    dashboard_widgets: List[DashboardWidget]


class WorkspaceListResponse(BaseModel):
    workspaces: List[WorkspaceResponse]
