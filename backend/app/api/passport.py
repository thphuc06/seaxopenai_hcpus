"""S1 public read contracts; business implementation follows contract-1."""
from fastapi import APIRouter

from app.api.contracts import EvidenceResponse, ProductResponse
from app.api.dependencies import Actor, not_implemented
from app.models import PassportResponse

router = APIRouter()


@router.get("/products", response_model=list[ProductResponse])
def products(actor: Actor) -> list[ProductResponse]:
    not_implemented()


@router.get("/products/{product_id}/passport", response_model=PassportResponse)
def passport(product_id: str, actor: Actor) -> PassportResponse:
    not_implemented()


@router.get("/products/{product_id}/fields/{field_key}/evidence", response_model=EvidenceResponse)
def evidence(product_id: str, field_key: str, actor: Actor) -> EvidenceResponse:
    not_implemented()
