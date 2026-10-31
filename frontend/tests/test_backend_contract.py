"""P3 integration check: mock wire response must satisfy the real backend model."""
from pathlib import Path
import subprocess

from app.models import PassportResponse

FRONTEND = Path(__file__).resolve().parents[1]


def test_mock_transport_matches_backend_passport_contract() -> None:
    result = subprocess.run(
        ["node", "tests/emit_mock_response.mjs"], cwd=FRONTEND,
        check=True, capture_output=True, encoding="utf-8", timeout=30,
    )
    passport = PassportResponse.model_validate_json(result.stdout)
    assert len(passport.fields) == 5
    assert all(field.verdict is not None for field in passport.fields)
