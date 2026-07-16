from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.db.database import get_db
from app.schemas.workspace import (
    DashboardWidgetCreate,
    DashboardWidgetUpdate,
    RecruiterPreferencesRequest,
    RecruiterPreferencesResponse,
    SavedCandidateListCreate,
    SavedCandidateListUpdate,
    SavedFilterCreate,
    SavedFilterUpdate,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/orgs/{org_id}/workspaces", tags=["workspaces"])


def get_organization_service(db: Session = Depends(get_db)) -> OrganizationService:
    return OrganizationService()


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    org_id: str,
    payload: WorkspaceCreate,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    workspace = service.create_workspace(org_id=org_id, name=payload.name, settings=payload.settings)
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return workspace


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(
    org_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> list[dict]:
    _ = current_user
    return service.list_workspaces(org_id=org_id)


@router.get("/{ws_id}", response_model=WorkspaceResponse)
def get_workspace(
    org_id: str,
    ws_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    workspace = service.get_workspace(org_id=org_id, ws_id=ws_id)
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


@router.put("/{ws_id}", response_model=WorkspaceResponse)
def update_workspace(
    org_id: str,
    ws_id: str,
    payload: WorkspaceUpdate,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    workspace = service.update_workspace(org_id=org_id, ws_id=ws_id, updates=payload.model_dump(exclude_unset=True))
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


@router.delete("/{ws_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    org_id: str,
    ws_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> None:
    _ = current_user
    service.delete_workspace(org_id=org_id, ws_id=ws_id)


# Saved filters
@router.post("/{ws_id}/filters", response_model=dict, status_code=status.HTTP_201_CREATED)
def add_saved_filter(
    org_id: str,
    ws_id: str,
    payload: SavedFilterCreate,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    result = service.add_saved_filter(org_id=org_id, ws_id=ws_id, name=payload.name, criteria=payload.criteria, description=payload.description)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return result


@router.get("/{ws_id}/filters", response_model=list[dict])
def list_saved_filters(
    org_id: str,
    ws_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> list[dict]:
    _ = current_user
    return service.list_saved_filters(org_id=org_id, ws_id=ws_id)


@router.get("/{ws_id}/filters/{filter_id}", response_model=dict)
def get_saved_filter(
    org_id: str,
    ws_id: str,
    filter_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    result = service.get_saved_filter(org_id=org_id, ws_id=ws_id, filter_id=filter_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved filter not found")
    return result


@router.put("/{ws_id}/filters/{filter_id}", response_model=dict)
def update_saved_filter(
    org_id: str,
    ws_id: str,
    filter_id: str,
    payload: SavedFilterUpdate,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    result = service.update_saved_filter(org_id=org_id, ws_id=ws_id, filter_id=filter_id, updates=payload.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved filter not found")
    return result


@router.delete("/{ws_id}/filters/{filter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_filter(
    org_id: str,
    ws_id: str,
    filter_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> None:
    _ = current_user
    if not service.delete_saved_filter(org_id=org_id, ws_id=ws_id, filter_id=filter_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved filter not found")


# Saved candidate lists
@router.post("/{ws_id}/candidate-lists", response_model=dict, status_code=status.HTTP_201_CREATED)
def add_saved_candidate_list(
    org_id: str,
    ws_id: str,
    payload: SavedCandidateListCreate,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    result = service.add_saved_candidate_list(org_id=org_id, ws_id=ws_id, name=payload.name, candidate_ids=payload.candidate_ids, description=payload.description)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return result


@router.get("/{ws_id}/candidate-lists", response_model=list[dict])
def list_saved_candidate_lists(
    org_id: str,
    ws_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> list[dict]:
    _ = current_user
    return service.list_saved_candidate_lists(org_id=org_id, ws_id=ws_id)


@router.get("/{ws_id}/candidate-lists/{list_id}", response_model=dict)
def get_saved_candidate_list(
    org_id: str,
    ws_id: str,
    list_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    result = service.get_saved_candidate_list(org_id=org_id, ws_id=ws_id, list_id=list_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved candidate list not found")
    return result


@router.put("/{ws_id}/candidate-lists/{list_id}", response_model=dict)
def update_saved_candidate_list(
    org_id: str,
    ws_id: str,
    list_id: str,
    payload: SavedCandidateListUpdate,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    result = service.update_saved_candidate_list(org_id=org_id, ws_id=ws_id, list_id=list_id, updates=payload.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved candidate list not found")
    return result


@router.delete("/{ws_id}/candidate-lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_candidate_list(
    org_id: str,
    ws_id: str,
    list_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> None:
    _ = current_user
    if not service.delete_saved_candidate_list(org_id=org_id, ws_id=ws_id, list_id=list_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved candidate list not found")


# Recruiter preferences
@router.get("/{ws_id}/preferences/{recruiter_id}", response_model=RecruiterPreferencesResponse)
def get_recruiter_preferences(
    org_id: str,
    ws_id: str,
    recruiter_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    result = service.get_recruiter_preferences(org_id=org_id, ws_id=ws_id, recruiter_id=recruiter_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preferences not found")
    return result


@router.put("/{ws_id}/preferences/{recruiter_id}", response_model=RecruiterPreferencesResponse)
def set_recruiter_preferences(
    org_id: str,
    ws_id: str,
    recruiter_id: str,
    payload: RecruiterPreferencesRequest,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    result = service.set_recruiter_preferences(org_id=org_id, ws_id=ws_id, recruiter_id=recruiter_id, preferences=payload.preferences)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return result


# Dashboard widgets
@router.post("/{ws_id}/widgets", response_model=dict, status_code=status.HTTP_201_CREATED)
def add_dashboard_widget(
    org_id: str,
    ws_id: str,
    payload: DashboardWidgetCreate,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    result = service.add_dashboard_widget(org_id=org_id, ws_id=ws_id, widget_type=payload.widget_type, title=payload.title, settings=payload.settings, enabled=payload.enabled, order=payload.order)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return result


@router.get("/{ws_id}/widgets", response_model=list[dict])
def list_dashboard_widgets(
    org_id: str,
    ws_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> list[dict]:
    _ = current_user
    return service.list_dashboard_widgets(org_id=org_id, ws_id=ws_id)


@router.get("/{ws_id}/widgets/{widget_id}", response_model=dict)
def get_dashboard_widget(
    org_id: str,
    ws_id: str,
    widget_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    result = service.get_dashboard_widget(org_id=org_id, ws_id=ws_id, widget_id=widget_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard widget not found")
    return result


@router.put("/{ws_id}/widgets/{widget_id}", response_model=dict)
def update_dashboard_widget(
    org_id: str,
    ws_id: str,
    widget_id: str,
    payload: DashboardWidgetUpdate,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> dict:
    _ = current_user
    result = service.update_dashboard_widget(org_id=org_id, ws_id=ws_id, widget_id=widget_id, updates=payload.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard widget not found")
    return result


@router.delete("/{ws_id}/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard_widget(
    org_id: str,
    ws_id: str,
    widget_id: str,
    current_user=Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
) -> None:
    _ = current_user
    if not service.delete_dashboard_widget(org_id=org_id, ws_id=ws_id, widget_id=widget_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard widget not found")
