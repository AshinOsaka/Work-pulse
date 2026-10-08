from __future__ import annotations

from itertools import pairwise

from app.auth.permissions import (
    PERMISSION_CATALOG,
    ROLE_CATALOG,
    Permission,
    Role,
    can_assign_role,
    permissions_for_role,
)


def test_every_permission_is_documented() -> None:
    assert set(PERMISSION_CATALOG) == set(Permission)


def test_every_role_is_defined() -> None:
    assert set(ROLE_CATALOG) == set(Role)


def test_admins_have_all_permissions() -> None:
    assert permissions_for_role(Role.SUPER_ADMIN) == frozenset(Permission)
    assert permissions_for_role(Role.COMPANY_ADMIN) == frozenset(Permission)


def test_roles_are_hierarchical() -> None:
    ordered = sorted(ROLE_CATALOG.values(), key=lambda r: r.level)
    for lower, higher in pairwise(ordered):
        assert lower.permissions <= higher.permissions, f"{higher.key} must include {lower.key}"


def test_employee_has_no_tenant_wide_permissions() -> None:
    assert permissions_for_role(Role.EMPLOYEE) == frozenset()
    assert Permission.USER_MANAGE not in permissions_for_role(Role.MANAGER)


def test_unknown_role_has_no_permissions() -> None:
    assert permissions_for_role("NOT_A_ROLE") == frozenset()


def test_role_assignment_rules() -> None:
    assert can_assign_role(Role.COMPANY_ADMIN, Role.MANAGER)
    assert can_assign_role(Role.COMPANY_ADMIN, Role.COMPANY_ADMIN)
    assert not can_assign_role(Role.COMPANY_ADMIN, Role.SUPER_ADMIN)
    assert not can_assign_role(Role.COMPANY_ADMIN, "NOT_A_ROLE")
    assert not can_assign_role(Role.MANAGER, Role.COMPANY_ADMIN)
    assert can_assign_role(Role.SUPER_ADMIN, Role.SUPER_ADMIN)
