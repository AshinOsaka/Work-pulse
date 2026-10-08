"""Two-step verification (TOTP authenticator apps + single-use recovery codes)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import segno
from bson import ObjectId

from app.auth.permissions import Role, can_assign_role
from app.auth.principal import Principal
from app.core import totp
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.security import verify_password
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.helpers import parse_id
from app.utils.time import utcnow

ISSUER = "WorkPulse"

SecondFactor = Literal["totp", "recovery_code"]


@dataclass(frozen=True, slots=True)
class MfaSetup:
    secret: str
    uri: str
    qr_svg: str


class MfaService:
    def __init__(self, users: UserRepository, audit: AuditService, key: bytes) -> None:
        self._users = users
        self._audit = audit
        self._key = key

    # ------------------------------------------------------------------ verification
    async def verify(self, user: User, code: str) -> SecondFactor | None:
        """Check an authenticator code or a recovery code; consumes it so it can't be replayed."""
        if not user.mfa_enabled or not user.mfa_secret:
            return None
        cleaned = code.strip().replace(" ", "")
        if cleaned.isdigit():
            secret = totp.decrypt_secret(self._key, user.mfa_secret, str(user.id))
            step = totp.matching_step(secret, cleaned, utcnow().timestamp(), user.mfa_last_step)
            if step is None:
                return None
            # Compare-and-set: two requests racing with the same code can't both succeed.
            if not await self._users.set_mfa_step(user.company_id, user.id, step, user.mfa_last_step):
                return None
            return "totp"
        hashed = totp.hash_recovery_code(cleaned)
        if hashed in user.mfa_recovery_codes and await self._users.use_recovery_code(
            user.company_id, user.id, hashed
        ):
            return "recovery_code"
        return None

    # ------------------------------------------------------------------ self-service
    def _check_password(self, user: User, password: str) -> None:
        if not verify_password(user.password_hash, password):
            raise BadRequestError(
                "Your password is incorrect.", code="invalid_password", details={"field": "password"}
            )

    async def begin_setup(self, user: User, password: str) -> MfaSetup:
        self._check_password(user, password)
        if user.mfa_enabled:
            raise ConflictError("Two-step verification is already on.", code="mfa_already_enabled")
        secret = totp.new_secret()
        await self._users.update_by_id(
            user.company_id,
            user.id,
            {"mfa_pending_secret": totp.encrypt_secret(self._key, secret, str(user.id))},
        )
        uri = totp.provisioning_uri(secret, user.email, ISSUER)
        qr = segno.make(uri, error="m").svg_data_uri(scale=5, border=2, dark="#111827", light="#ffffff")
        return MfaSetup(secret=secret, uri=uri, qr_svg=qr)

    async def confirm_setup(self, user: User, code: str, meta: RequestMeta) -> list[str]:
        if user.mfa_enabled:
            raise ConflictError("Two-step verification is already on.", code="mfa_already_enabled")
        if not user.mfa_pending_secret:
            raise BadRequestError("Start the setup again.", code="mfa_setup_not_started")
        secret = totp.decrypt_secret(self._key, user.mfa_pending_secret, str(user.id))
        step = totp.matching_step(secret, code, utcnow().timestamp())
        if step is None:
            raise BadRequestError(
                "That code didn't match. Check the time on your phone and try the newest code.",
                code="invalid_mfa_code",
                details={"field": "code"},
            )
        codes = totp.new_recovery_codes()
        await self._users.update_by_id(
            user.company_id,
            user.id,
            {
                "mfa_enabled": True,
                "mfa_enabled_at": utcnow(),
                "mfa_secret": user.mfa_pending_secret,
                "mfa_pending_secret": None,
                "mfa_last_step": step,
                "mfa_recovery_codes": [totp.hash_recovery_code(c) for c in codes],
            },
        )
        await self._audit.record(
            "auth.mfa_enabled", company_id=user.company_id, actor_user_id=user.id, meta=meta
        )
        return codes

    async def _require_second_factor(self, user: User, code: str) -> None:
        if await self.verify(user, code) is None:
            raise BadRequestError(
                "That code didn't match.", code="invalid_mfa_code", details={"field": "code"}
            )

    async def disable(self, user: User, password: str, code: str, meta: RequestMeta) -> None:
        self._check_password(user, password)
        if not user.mfa_enabled:
            raise ConflictError("Two-step verification is already off.", code="mfa_not_enabled")
        await self._require_second_factor(user, code)
        await self._users.update_by_id(user.company_id, user.id, _MFA_OFF)
        await self._audit.record(
            "auth.mfa_disabled", company_id=user.company_id, actor_user_id=user.id, meta=meta
        )

    async def regenerate_recovery_codes(
        self, user: User, password: str, code: str, meta: RequestMeta
    ) -> list[str]:
        self._check_password(user, password)
        if not user.mfa_enabled:
            raise ConflictError("Two-step verification is off.", code="mfa_not_enabled")
        await self._require_second_factor(user, code)
        codes = totp.new_recovery_codes()
        await self._users.update_by_id(
            user.company_id, user.id, {"mfa_recovery_codes": [totp.hash_recovery_code(c) for c in codes]}
        )
        await self._audit.record(
            "auth.mfa_recovery_codes_regenerated",
            company_id=user.company_id,
            actor_user_id=user.id,
            meta=meta,
        )
        return codes

    # ------------------------------------------------------------------ administration
    async def reset_for(self, principal: Principal, user_id: str, meta: RequestMeta) -> User:
        """For someone who lost their phone and recovery codes. They sign in with their password and can set it up again."""
        oid: ObjectId = parse_id(user_id, not_found="User not found.", code="user_not_found")
        target = await self._users.get_by_id(principal.company_id, oid)
        if target is None:
            raise NotFoundError("User not found.", code="user_not_found")
        if target.id == principal.user_id:
            raise BadRequestError(
                "Turn off your own two-step verification from your security settings.",
                code="cannot_reset_own_mfa",
            )
        if not can_assign_role(principal.role, target.role) and principal.role != Role.SUPER_ADMIN:
            raise ForbiddenError("You cannot manage this account.", code="role_not_assignable")
        if not target.mfa_enabled:
            raise ConflictError(
                "Two-step verification is already off for this person.", code="mfa_not_enabled"
            )
        updated = await self._users.update_by_id(principal.company_id, target.id, _MFA_OFF) or target
        await self._audit.record(
            "user.mfa_reset",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="user",
            target_id=str(target.id),
            subject_employee_id=target.employee_id,
            meta=meta,
        )
        return updated


_MFA_OFF: dict[str, object] = {
    "mfa_enabled": False,
    "mfa_enabled_at": None,
    "mfa_secret": None,
    "mfa_pending_secret": None,
    "mfa_last_step": None,
    "mfa_recovery_codes": [],
}
