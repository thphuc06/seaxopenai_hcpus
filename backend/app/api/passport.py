"""Stored results and role-filtered evidence; buyer reads create no work."""
from typing import Annotated
from contextlib import closing

from fastapi import APIRouter, HTTPException, Query, Response

from app.api.contracts import EvidenceResponse, PassportMetadata, ProductPresentation, ProductResponse
from app.api.dependencies import Actor
from app.api import read
from app import db, source_images
from app.models import PassportResponse, Role, PUBLIC_FIELDS

router = APIRouter()


@router.get(
    "/sources/{source_version_id}/image", response_class=Response, response_model=None,
    responses={200: {"content": {
        media: {"schema": {"type": "string", "format": "binary"}}
        for media in ("image/png", "image/jpeg", "image/webp")
    }}},
)
def source_image(source_version_id: str, as_role: Annotated[Role, Query()]) -> Response:
    source = read.one("SELECT v.raw_path,s.kind,s.visibility FROM source_versions v JOIN sources s ON s.id=v.source_id WHERE v.id=?", (source_version_id,))
    if source["visibility"] != "PUBLIC" and as_role not in {Role.REVIEWER, Role.OPERATOR}:
        raise HTTPException(403, "Image access requires an expert role")
    if source["kind"] != "PACKAGING_IMAGE" or not source["raw_path"]:
        raise HTTPException(404, "Source image not available")
    try:
        data, media, _, _ = source_images.read_image(str(source["raw_path"]))
    except (OSError, ValueError) as error:
        raise HTTPException(404, "Source image not available") from error
    return Response(data, media_type=media, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/products", response_model=list[ProductResponse])
def products(actor: Actor) -> list[ProductResponse]:
    products: list[ProductResponse] = []
    for row in read.rows("SELECT * FROM products ORDER BY id"):
        result = ProductResponse(**{key: row[key] for key in ("id","name","brand","variant","market","dataset_origin")})
        cases = read.rows("SELECT id FROM cases WHERE product_id=?", (row["id"],))
        if cases:
            case_id = cases[0]["id"]
            latest = read.rows("SELECT * FROM runs WHERE case_id=? ORDER BY case_revision DESC,created_at DESC LIMIT 1", (case_id,))
            hidden = {str(item["field_key"]): read.evidence(str(item["citations_json"]),actor.role)[1]
                      for item in read.rows("SELECT field_key,citations_json FROM field_results WHERE case_id=? AND superseded_by IS NULL", (case_id,)) if item["field_key"] in PUBLIC_FIELDS}
            pending = read.one("SELECT COUNT(*) AS n FROM field_results WHERE case_id=? AND superseded_by IS NULL AND field_key LIKE 'claim:%' AND review_state='NEEDS_REVIEW'",(case_id,))
            metadata = PassportMetadata(llm_mode=read.run_response(latest[0]).llm_mode if latest else None,hidden_citations=hidden,pending_claims=int(pending["n"]))
            result.presentation = ProductPresentation(image=str(row["image_path"] or ""),image_alt=str(row["name"]),
                price=float(row["price_vnd"] or 0),currency="VND",shop=str(row["shop_name"] or ""),
                official_store=bool(row["official_store"]),category="",passport_metadata=metadata)
        products.append(result)
    return products


@router.get("/products/{product_id}/passport", response_model=PassportResponse)
def passport(product_id: str, actor: Actor) -> PassportResponse:
    with closing(db.connect()) as connection:
        connection.execute("BEGIN")
        result = read.passport_snapshot(connection, product_id, actor.role)
    if actor.role == Role.BUYER:
        read.passport_reads(increment=True)
    return result


@router.get("/products/{product_id}/fields/{field_key}/evidence", response_model=EvidenceResponse)
def evidence(product_id: str, field_key: str, actor: Actor) -> EvidenceResponse:
    if field_key not in PUBLIC_FIELDS and actor.role not in {Role.REVIEWER,Role.OPERATOR,Role.SYSTEM}:
        raise HTTPException(404,"Field not found")
    case = read.one("SELECT * FROM cases WHERE product_id=?", (product_id,))
    result = read.one("SELECT * FROM field_results WHERE case_id=? AND field_key=? AND superseded_by IS NULL",
                      (case["id"],field_key))
    passages, hidden = read.evidence(str(result["citations_json"]), actor.role)
    return EvidenceResponse(citations=passages,hidden_citations=hidden)
