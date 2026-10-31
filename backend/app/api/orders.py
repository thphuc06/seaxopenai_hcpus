"""S4 receipt and marketplace contracts; authorized requests await implementation."""
from fastapi import APIRouter

from app.api.dependencies import Actor, OperatorActor, not_implemented
from app.api.s4_contracts import (
    BuyerMarketplaceResponse, ExpertMarketplaceResponse, MarketplaceScanResponse,
    OrderRequest, ReceiptResponse,
)

router = APIRouter()


@router.post("/orders", response_model=ReceiptResponse)
def create_order(body: OrderRequest, actor: Actor) -> ReceiptResponse:
    not_implemented()


@router.get("/orders", response_model=list[ReceiptResponse])
def orders(actor: Actor) -> list[ReceiptResponse]:
    not_implemented()


@router.get("/orders/{order_id}", response_model=ReceiptResponse)
def order(order_id: str, actor: Actor) -> ReceiptResponse:
    not_implemented()


@router.get("/products/{product_id}/marketplace", response_model=BuyerMarketplaceResponse | ExpertMarketplaceResponse)
def marketplace(product_id: str, actor: Actor) -> BuyerMarketplaceResponse | ExpertMarketplaceResponse:
    not_implemented()


@router.post("/internal/marketplace/{product_id}/scan", response_model=MarketplaceScanResponse)
def scan_marketplace(product_id: str, actor: OperatorActor) -> MarketplaceScanResponse:
    not_implemented()
