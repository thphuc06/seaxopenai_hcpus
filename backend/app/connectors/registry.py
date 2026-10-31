"""Offline MOCK registry; source records are always SYNTHETIC."""
import json
from hashlib import sha256
from typing import Literal
from pydantic import BaseModel, ConfigDict
from app import config
from app.pipeline.normalize import normalize


class RegistryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_name: str
    holder: str
    status: Literal["ACTIVE", "REVOKED"]
    issued: str
    revoked: str | None = None


def revision() -> str:
    return sha256((config.settings.fixtures_dir / "synthetic/registry/mock_registry.json").read_bytes()).hexdigest()


def lookup(number: str) -> RegistryRecord | None:
    path = config.settings.fixtures_dir / "synthetic/registry/mock_registry.json"
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream)
    matches = [value for key, value in data["records"].items() if normalize("notification_number", key) == normalize("notification_number", number)]
    if len(matches) > 1:
        raise ValueError("Ambiguous registry number")
    value = matches[0] if matches else None
    return RegistryRecord.model_validate(value) if value else None
