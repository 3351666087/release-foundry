from __future__ import annotations

from ashr_clone.unified_identity import UnifiedAccount


def test_python_canonical_account_security_posture_is_public_and_secret_free() -> None:
    account = UnifiedAccount.from_public_response(
        {
            "account_id": "acct_canonical",
            "status": "active",
            "display_name": "Owner",
            "created_at": "2026-07-12T00:00:00Z",
            "updated_at": "2026-07-12T00:00:00Z",
            "credentials": [],
            "memberships": [],
            "security_posture": {
                "primary_email": {"present": True, "verified": True, "source": "google"},
                "password": {"status": "absent", "settable": True},
                "two_factor": {"status": "disabled", "optional": True, "recommended": True},
            },
        }
    )
    assert account.security_posture == {
        "primary_email": {"present": True, "verified": True, "source": "google"},
        "password": {"status": "absent", "settable": True},
        "two_factor": {"status": "disabled", "optional": True, "recommended": True},
    }
    assert "@" not in str(account.to_dict())


def test_canonical_identity_migration_contains_fail_closed_invariants() -> None:
    sql = (
        __import__("pathlib").Path(__file__).parents[2]
        / "services/api/migrations/016_a1_canonical_account_security.sql"
    ).read_text(encoding="utf-8").lower()
    for required in (
        "normalized_email_digest text not null unique",
        "two_factor_recommended boolean not null default true",
        "p_csrf_validated",
        "interval '10 minutes'",
        "revoke_reason_code = 'password_changed'",
        "revoke_reason_code = 'two_factor_changed'",
        "canonical_email_conflict",
        "enable row level security",
        "force row level security",
    ):
        assert required in sql
    for forbidden in ("raw_email", "raw_password", "password_hash"):
        assert forbidden not in sql
