from __future__ import annotations

from typing import Iterable, Dict, Iterable, List, Optional
import json
import os
import threading


class RoleError(Exception):
    """Raised when a role is not supported by the RBAC rules."""


# Default, global permissions for built-in roles. These are conservative
# and should be extended per-organization via organization-level role files.
DEFAULT_ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "admin": [
        "org:manage",
        "workspace:manage",
        "recruiter:manage",
        "candidate:read",
        "candidate:write",
        "interview:manage",
        "notification:send",
        "audit:read",
    ],
    "recruiter": [
        "candidate:read",
        "candidate:write",
        "interview:schedule",
        "notification:send",
    ],
    "hiring_manager": [
        "candidate:read",
        "candidate:comment",
        "interview:review",
    ],
    "interviewer": [
        "candidate:read",
        "interview:participate",
        "feedback:write",
    ],
    "user": [
        "candidate:self_read",
        "candidate:self_update",
    ],
}


def _org_roles_path(org_id: str) -> str:
    base = os.path.join(os.path.dirname(__file__), "..", "data", "orgs")
    return os.path.join(base, org_id, "roles.json")


class RoleManager:
    """Manage roles and permissions, supporting org-level custom roles.

    This manager reads optional per-organization role definitions from
    `data/orgs/<org_id>/roles.json`. Organization role files should be a
    mapping of role_name -> list_of_permissions. When a role is requested,
    permissions are merged: org-level overrides/extends default permissions.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _load_org_roles(self, org_id: str) -> Dict[str, List[str]]:
        path = _org_roles_path(org_id)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                # normalize lists
                return {k: list(v) for k, v in raw.items()}
        except Exception:
            pass
        return {}

    def get_permissions_for_role(self, role: str, org_id: Optional[str] = None) -> List[str]:
        role_norm = (role or "").strip().lower()
        perms = list(DEFAULT_ROLE_PERMISSIONS.get(role_norm, []))
        if org_id:
            org_roles = self._load_org_roles(org_id)
            org_perms = org_roles.get(role_norm)
            if org_perms is not None:
                # organization can replace or extend; we choose to merge unique items
                merged = list(dict.fromkeys(perms + list(org_perms)))
                return merged
        return perms

    def user_has_permission(self, user_roles: Iterable[str], permission: str, org_id: Optional[str] = None) -> bool:
        """Return True if any of the user's roles grant the permission.

        `user_roles` can be a list of role names (strings). This allows a user
        to have multiple roles simultaneously.
        """
        perm = (permission or "").strip().lower()
        for r in user_roles:
            for p in self.get_permissions_for_role(r, org_id=org_id):
                if p == perm:
                    return True
        return False

    def list_org_roles(self, org_id: str) -> Dict[str, List[str]]:
        return self._load_org_roles(org_id)

    def create_or_update_org_role(self, org_id: str, role: str, permissions: List[str]) -> None:
        path = _org_roles_path(org_id)
        with self._lock:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                data = {}
            data[role.strip().lower()] = permissions
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)

    def delete_org_role(self, org_id: str, role: str) -> None:
        path = _org_roles_path(org_id)
        with self._lock:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                return
            key = role.strip().lower()
            if key in data:
                del data[key]
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)


# Singleton manager for convenience across the application
role_manager = RoleManager()


def validate_role(role: str) -> str:
    """Normalize role string. Does not enforce a global whitelist.

    Existing code that called `validate_role` expecting normalization will
    continue to work. Use `role_manager` for permission checks.
    """
    if not isinstance(role, str) or not role.strip():
        raise RoleError("Role must be a non-empty string")
    return role.strip().lower()


def has_any_role(user_role: str, allowed_roles: Iterable[str]) -> bool:
    """Compatibility helper that checks if `user_role` is among allowed_roles."""
    try:
        normalized_user_role = validate_role(user_role)
    except RoleError:
        return False
    normalized_allowed_roles = {validate_role(role) for role in allowed_roles}
    return normalized_user_role in normalized_allowed_roles

