from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


def _abs_path(path: str) -> str:
    return os.path.abspath(path)


class OrganizationStore:
    """File-backed per-organization store.

    Data layout (under `data/orgs`):
      index.json                # list of org metadata
      <org_id>/
        org.json                # organization metadata and settings
        workspaces/<ws_id>.json
        recruiters.json         # list of recruiters

    This simple store uses per-org directories to make it easy to enforce
    isolation; migrating to a DB is straightforward by replacing this class.
    """

    BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "orgs")
    INDEX_PATH = os.path.join(BASE_DIR, "index.json")

    def __init__(self) -> None:
        os.makedirs(self.BASE_DIR, exist_ok=True)
        if not os.path.exists(self.INDEX_PATH):
            with open(self.INDEX_PATH, "w", encoding="utf-8") as fh:
                json.dump({}, fh)
        self._lock = threading.Lock()

    def _org_dir(self, org_id: str) -> str:
        return os.path.join(self.BASE_DIR, org_id)

    def _ensure_org_dir(self, org_id: str) -> None:
        od = self._org_dir(org_id)
        os.makedirs(od, exist_ok=True)
        os.makedirs(os.path.join(od, "workspaces"), exist_ok=True)

    def list_organizations(self) -> List[Dict[str, Any]]:
        try:
            with open(self.INDEX_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return list(data.values())
        except Exception:
            return []

    def get_organization(self, org_id: str) -> Optional[Dict[str, Any]]:
        try:
            with open(self.INDEX_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data.get(org_id)
        except Exception:
            return None

    def create_organization(self, name: str, owner_id: str, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            org_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat() + "Z"
            org = {"id": org_id, "name": name, "owner_id": owner_id, "created_at": now, "settings": settings or {}}
            # write index
            try:
                with open(self.INDEX_PATH, "r", encoding="utf-8") as fh:
                    idx = json.load(fh)
            except Exception:
                idx = {}
            idx[org_id] = org
            with open(self.INDEX_PATH, "w", encoding="utf-8") as fh:
                json.dump(idx, fh, ensure_ascii=False, indent=2)

            # create org dir and initial files
            self._ensure_org_dir(org_id)
            with open(os.path.join(self._org_dir(org_id), "org.json"), "w", encoding="utf-8") as fh:
                json.dump(org, fh, ensure_ascii=False, indent=2)

            # empty recruiters file
            with open(os.path.join(self._org_dir(org_id), "recruiters.json"), "w", encoding="utf-8") as fh:
                json.dump({}, fh)

            return org

    def update_organization(self, org_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            try:
                with open(self.INDEX_PATH, "r", encoding="utf-8") as fh:
                    idx = json.load(fh)
            except Exception:
                return None
            org = idx.get(org_id)
            if not org:
                return None
            org.update(updates)
            idx[org_id] = org
            with open(self.INDEX_PATH, "w", encoding="utf-8") as fh:
                json.dump(idx, fh, ensure_ascii=False, indent=2)
            with open(os.path.join(self._org_dir(org_id), "org.json"), "w", encoding="utf-8") as fh:
                json.dump(org, fh, ensure_ascii=False, indent=2)
            return org

    def delete_organization(self, org_id: str) -> None:
        with self._lock:
            try:
                with open(self.INDEX_PATH, "r", encoding="utf-8") as fh:
                    idx = json.load(fh)
            except Exception:
                idx = {}
            if org_id in idx:
                del idx[org_id]
                with open(self.INDEX_PATH, "w", encoding="utf-8") as fh:
                    json.dump(idx, fh, ensure_ascii=False, indent=2)
            # remove directory
            od = self._org_dir(org_id)
            if os.path.exists(od):
                shutil.rmtree(od)

    # Workspaces
    def create_workspace(self, org_id: str, name: str, settings: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            org = self.get_organization(org_id)
            if not org:
                return None
            ws_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat() + "Z"
            ws = {
                "id": ws_id,
                "name": name,
                "created_at": now,
                "settings": settings or {},
                "saved_filters": [],
                "saved_candidate_lists": [],
                "recruiter_preferences": {},
                "dashboard_widgets": [],
            }
            self._ensure_org_dir(org_id)
            path = os.path.join(self._org_dir(org_id), "workspaces", f"{ws_id}.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(ws, fh, ensure_ascii=False, indent=2)
            return ws

    def _save_workspace(self, org_id: str, workspace: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        path = os.path.join(self._org_dir(org_id), "workspaces", f"{workspace.get('id')}.json")
        if not os.path.exists(path):
            return None
        self._ensure_org_dir(org_id)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(workspace, fh, ensure_ascii=False, indent=2)
        return workspace

    def _normalize_workspace(self, workspace: Dict[str, Any]) -> Dict[str, Any]:
        workspace.setdefault("settings", {})
        workspace.setdefault("saved_filters", [])
        workspace.setdefault("saved_candidate_lists", [])
        workspace.setdefault("recruiter_preferences", {})
        workspace.setdefault("dashboard_widgets", [])
        return workspace

    def update_workspace(self, org_id: str, ws_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            workspace = self.get_workspace(org_id, ws_id)
            if not workspace:
                return None
            workspace = self._normalize_workspace(workspace)
            for key, value in updates.items():
                if key == "settings" and isinstance(value, dict):
                    workspace.setdefault("settings", {}).update(value)
                elif key in {"name", "settings"}:
                    workspace[key] = value
            workspace["updated_at"] = datetime.utcnow().isoformat() + "Z"
            return self._save_workspace(org_id, workspace)

    def delete_workspace(self, org_id: str, ws_id: str) -> None:
        path = os.path.join(self._org_dir(org_id), "workspaces", f"{ws_id}.json")
        if os.path.exists(path):
            os.remove(path)

    def list_workspaces(self, org_id: str) -> List[Dict[str, Any]]:
        od = self._org_dir(org_id)
        wdir = os.path.join(od, "workspaces")
        if not os.path.exists(wdir):
            return []
        out: List[Dict[str, Any]] = []
        for fn in os.listdir(wdir):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(wdir, fn), "r", encoding="utf-8") as fh:
                        out.append(self._normalize_workspace(json.load(fh)))
                except Exception:
                    continue
        return out

    def get_workspace(self, org_id: str, ws_id: str) -> Optional[Dict[str, Any]]:
        path = os.path.join(self._org_dir(org_id), "workspaces", f"{ws_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return self._normalize_workspace(json.load(fh))
        except Exception:
            return None

    def _workspace_item_by_id(self, workspace: Dict[str, Any], collection_name: str, item_id: str) -> Optional[Dict[str, Any]]:
        return next((item for item in workspace.get(collection_name, []) if item.get("id") == item_id), None)

    def _mutate_workspace_collection(self, org_id: str, ws_id: str, collection_name: str, item_id: str | None, changes: Dict[str, Any], mutate: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            workspace = self.get_workspace(org_id, ws_id)
            if not workspace:
                return None
            workspace = self._normalize_workspace(workspace)
            collection = workspace.setdefault(collection_name, [])
            if mutate == "create":
                new_item = {"id": str(uuid.uuid4()), "created_at": datetime.utcnow().isoformat() + "Z"}
                new_item.update(changes)
                new_item["updated_at"] = new_item["created_at"]
                collection.append(new_item)
                self._save_workspace(org_id, workspace)
                return new_item
            existing = self._workspace_item_by_id(workspace, collection_name, item_id)
            if not existing:
                return None
            if mutate == "update":
                existing.update(changes)
                existing["updated_at"] = datetime.utcnow().isoformat() + "Z"
                self._save_workspace(org_id, workspace)
                return existing
            if mutate == "delete":
                workspace[collection_name] = [item for item in collection if item.get("id") != item_id]
                self._save_workspace(org_id, workspace)
                return {"id": item_id}
            return None

    def list_saved_filters(self, org_id: str, ws_id: str) -> List[Dict[str, Any]]:
        workspace = self.get_workspace(org_id, ws_id)
        if not workspace:
            return []
        return workspace.get("saved_filters", [])

    def get_saved_filter(self, org_id: str, ws_id: str, filter_id: str) -> Optional[Dict[str, Any]]:
        workspace = self.get_workspace(org_id, ws_id)
        return self._workspace_item_by_id(workspace, "saved_filters", filter_id) if workspace else None

    def add_saved_filter(self, org_id: str, ws_id: str, name: str, criteria: Dict[str, Any], description: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self._mutate_workspace_collection(org_id, ws_id, "saved_filters", None, {"name": name, "description": description or "", "criteria": criteria}, "create")

    def update_saved_filter(self, org_id: str, ws_id: str, filter_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"name", "description", "criteria"}
        sanitized = {k: v for k, v in updates.items() if k in allowed}
        return self._mutate_workspace_collection(org_id, ws_id, "saved_filters", filter_id, sanitized, "update")

    def delete_saved_filter(self, org_id: str, ws_id: str, filter_id: str) -> bool:
        result = self._mutate_workspace_collection(org_id, ws_id, "saved_filters", filter_id, {}, "delete")
        return result is not None

    def list_saved_candidate_lists(self, org_id: str, ws_id: str) -> List[Dict[str, Any]]:
        workspace = self.get_workspace(org_id, ws_id)
        if not workspace:
            return []
        return workspace.get("saved_candidate_lists", [])

    def get_saved_candidate_list(self, org_id: str, ws_id: str, list_id: str) -> Optional[Dict[str, Any]]:
        workspace = self.get_workspace(org_id, ws_id)
        return self._workspace_item_by_id(workspace, "saved_candidate_lists", list_id) if workspace else None

    def add_saved_candidate_list(self, org_id: str, ws_id: str, name: str, candidate_ids: list[str], description: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self._mutate_workspace_collection(
            org_id,
            ws_id,
            "saved_candidate_lists",
            None,
            {"name": name, "description": description or "", "candidate_ids": candidate_ids},
            "create",
        )

    def update_saved_candidate_list(self, org_id: str, ws_id: str, list_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"name", "description", "candidate_ids"}
        sanitized = {k: v for k, v in updates.items() if k in allowed}
        return self._mutate_workspace_collection(org_id, ws_id, "saved_candidate_lists", list_id, sanitized, "update")

    def delete_saved_candidate_list(self, org_id: str, ws_id: str, list_id: str) -> bool:
        result = self._mutate_workspace_collection(org_id, ws_id, "saved_candidate_lists", list_id, {}, "delete")
        return result is not None

    def get_recruiter_preferences(self, org_id: str, ws_id: str, recruiter_id: str) -> Dict[str, Any]:
        workspace = self.get_workspace(org_id, ws_id)
        if not workspace:
            return {}
        return workspace.get("recruiter_preferences", {}).get(recruiter_id, {})

    def set_recruiter_preferences(self, org_id: str, ws_id: str, recruiter_id: str, preferences: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            workspace = self.get_workspace(org_id, ws_id)
            if not workspace:
                return None
            workspace = self._normalize_workspace(workspace)
            workspace.setdefault("recruiter_preferences", {})[recruiter_id] = {"preferences": preferences, "updated_at": datetime.utcnow().isoformat() + "Z"}
            self._save_workspace(org_id, workspace)
            return workspace["recruiter_preferences"][recruiter_id]

    def list_dashboard_widgets(self, org_id: str, ws_id: str) -> List[Dict[str, Any]]:
        workspace = self.get_workspace(org_id, ws_id)
        if not workspace:
            return []
        return workspace.get("dashboard_widgets", [])

    def get_dashboard_widget(self, org_id: str, ws_id: str, widget_id: str) -> Optional[Dict[str, Any]]:
        workspace = self.get_workspace(org_id, ws_id)
        return self._workspace_item_by_id(workspace, "dashboard_widgets", widget_id) if workspace else None

    def add_dashboard_widget(self, org_id: str, ws_id: str, widget_type: str, title: str, settings: Dict[str, Any], enabled: bool = True, order: int = 0) -> Optional[Dict[str, Any]]:
        return self._mutate_workspace_collection(
            org_id,
            ws_id,
            "dashboard_widgets",
            None,
            {"widget_type": widget_type, "title": title, "settings": settings, "enabled": enabled, "order": order},
            "create",
        )

    def update_dashboard_widget(self, org_id: str, ws_id: str, widget_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"title", "settings", "enabled", "order"}
        sanitized = {k: v for k, v in updates.items() if k in allowed}
        return self._mutate_workspace_collection(org_id, ws_id, "dashboard_widgets", widget_id, sanitized, "update")

    def delete_dashboard_widget(self, org_id: str, ws_id: str, widget_id: str) -> bool:
        result = self._mutate_workspace_collection(org_id, ws_id, "dashboard_widgets", widget_id, {}, "delete")
        return result is not None

    # Recruiters
    def add_recruiter(self, org_id: str, recruiter_id: str, email: str, role: str = "recruiter") -> Dict[str, Any]:
        self._ensure_org_dir(org_id)
        path = os.path.join(self._org_dir(org_id), "recruiters.json")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                recs = json.load(fh)
        except Exception:
            recs = {}
        recs[recruiter_id] = {"id": recruiter_id, "email": email, "role": role, "added_at": datetime.utcnow().isoformat() + "Z"}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(recs, fh, ensure_ascii=False, indent=2)
        return recs[recruiter_id]

    def remove_recruiter(self, org_id: str, recruiter_id: str) -> None:
        path = os.path.join(self._org_dir(org_id), "recruiters.json")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                recs = json.load(fh)
        except Exception:
            recs = {}
        if recruiter_id in recs:
            del recs[recruiter_id]
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(recs, fh, ensure_ascii=False, indent=2)

    def list_recruiters(self, org_id: str) -> List[Dict[str, Any]]:
        path = os.path.join(self._org_dir(org_id), "recruiters.json")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                recs = json.load(fh)
            return list(recs.values())
        except Exception:
            return []


class OrganizationService:
    """High-level API for multi-tenant organization and workspace management.

    This service focuses on per-organization isolation, basic RBAC for recruiters,
    and workspace management. It is intentionally small and built to be
    replaceable with a DB-backed implementation later.
    """

    def __init__(self, store: Optional[OrganizationStore] = None) -> None:
        self.store = store or OrganizationStore()

    def create_organization(self, name: str, owner_id: str, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.store.create_organization(name=name, owner_id=owner_id, settings=settings)

    def get_organization(self, org_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_organization(org_id)

    def update_organization(self, org_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.store.update_organization(org_id, updates)

    def delete_organization(self, org_id: str) -> None:
        return self.store.delete_organization(org_id)

    def list_organizations(self) -> List[Dict[str, Any]]:
        return self.store.list_organizations()

    # Workspace operations
    def create_workspace(self, org_id: str, name: str, settings: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        return self.store.create_workspace(org_id, name, settings)

    def list_workspaces(self, org_id: str) -> List[Dict[str, Any]]:
        return self.store.list_workspaces(org_id)

    def get_workspace(self, org_id: str, ws_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_workspace(org_id, ws_id)

    def update_workspace(self, org_id: str, ws_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.store.update_workspace(org_id, ws_id, updates)

    def delete_workspace(self, org_id: str, ws_id: str) -> None:
        return self.store.delete_workspace(org_id, ws_id)

    def list_saved_filters(self, org_id: str, ws_id: str) -> List[Dict[str, Any]]:
        return self.store.list_saved_filters(org_id, ws_id)

    def get_saved_filter(self, org_id: str, ws_id: str, filter_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_saved_filter(org_id, ws_id, filter_id)

    def add_saved_filter(self, org_id: str, ws_id: str, name: str, criteria: Dict[str, Any], description: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.store.add_saved_filter(org_id, ws_id, name, criteria, description)

    def update_saved_filter(self, org_id: str, ws_id: str, filter_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.store.update_saved_filter(org_id, ws_id, filter_id, updates)

    def delete_saved_filter(self, org_id: str, ws_id: str, filter_id: str) -> bool:
        return self.store.delete_saved_filter(org_id, ws_id, filter_id)

    def list_saved_candidate_lists(self, org_id: str, ws_id: str) -> List[Dict[str, Any]]:
        return self.store.list_saved_candidate_lists(org_id, ws_id)

    def get_saved_candidate_list(self, org_id: str, ws_id: str, list_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_saved_candidate_list(org_id, ws_id, list_id)

    def add_saved_candidate_list(self, org_id: str, ws_id: str, name: str, candidate_ids: list[str], description: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.store.add_saved_candidate_list(org_id, ws_id, name, candidate_ids, description)

    def update_saved_candidate_list(self, org_id: str, ws_id: str, list_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.store.update_saved_candidate_list(org_id, ws_id, list_id, updates)

    def delete_saved_candidate_list(self, org_id: str, ws_id: str, list_id: str) -> bool:
        return self.store.delete_saved_candidate_list(org_id, ws_id, list_id)

    def get_recruiter_preferences(self, org_id: str, ws_id: str, recruiter_id: str) -> Dict[str, Any]:
        return self.store.get_recruiter_preferences(org_id, ws_id, recruiter_id)

    def set_recruiter_preferences(self, org_id: str, ws_id: str, recruiter_id: str, preferences: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.store.set_recruiter_preferences(org_id, ws_id, recruiter_id, preferences)

    def list_dashboard_widgets(self, org_id: str, ws_id: str) -> List[Dict[str, Any]]:
        return self.store.list_dashboard_widgets(org_id, ws_id)

    def get_dashboard_widget(self, org_id: str, ws_id: str, widget_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_dashboard_widget(org_id, ws_id, widget_id)

    def add_dashboard_widget(self, org_id: str, ws_id: str, widget_type: str, title: str, settings: Dict[str, Any], enabled: bool = True, order: int = 0) -> Optional[Dict[str, Any]]:
        return self.store.add_dashboard_widget(org_id, ws_id, widget_type, title, settings, enabled, order)

    def update_dashboard_widget(self, org_id: str, ws_id: str, widget_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.store.update_dashboard_widget(org_id, ws_id, widget_id, updates)

    def delete_dashboard_widget(self, org_id: str, ws_id: str, widget_id: str) -> bool:
        return self.store.delete_dashboard_widget(org_id, ws_id, widget_id)

    # Recruiter management and RBAC
    def add_recruiter(self, org_id: str, recruiter_id: str, email: str, role: str = "recruiter") -> Dict[str, Any]:
        return self.store.add_recruiter(org_id, recruiter_id, email, role)

    def remove_recruiter(self, org_id: str, recruiter_id: str) -> None:
        return self.store.remove_recruiter(org_id, recruiter_id)

    def list_recruiters(self, org_id: str) -> List[Dict[str, Any]]:
        return self.store.list_recruiters(org_id)

    def is_recruiter_in_org(self, org_id: str, recruiter_id: str) -> bool:
        recs = self.list_recruiters(org_id)
        return any(r.get("id") == recruiter_id for r in recs)

    def get_org_context(self, org_id: str) -> Optional[Dict[str, Any]]:
        org = self.get_organization(org_id)
        if not org:
            return None
        # Return minimal context useful for downstream services
        return {"org": org, "workspaces": self.list_workspaces(org_id), "recruiters": self.list_recruiters(org_id)}


# convenient singleton
organization_service = OrganizationService()
