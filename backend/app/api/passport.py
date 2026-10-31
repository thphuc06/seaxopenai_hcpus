"""Stored results and role-filtered evidence; buyer reads create no work."""
from fastapi import APIRouter, HTTPException

from app.api.contracts import EvidenceResponse, PassportMetadata, ProductPresentation, ProductResponse
from app.api.dependencies import Actor
from app.api import read
from app.models import Citation, PassportField, PassportResponse, Role, PUBLIC_FIELDS

router = APIRouter()


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
    product = read.one("SELECT * FROM products WHERE id=?", (product_id,))
    case = read.one("SELECT * FROM cases WHERE product_id=?", (product_id,))
    results = read.rows("SELECT * FROM field_results WHERE case_id=? AND superseded_by IS NULL ORDER BY field_key", (case["id"],))
    latest = read.rows("SELECT * FROM runs WHERE case_id=? ORDER BY case_revision DESC,created_at DESC LIMIT 1", (case["id"],))
    fields = []
    for result in results:
        if result["field_key"] not in PUBLIC_FIELDS:
            continue
        passages, _ = read.evidence(str(result["citations_json"]), actor.role)
        label = "Stale" if result["freshness"] == "STALE" else "Updating" if latest and latest[0]["status"] == "RUNNING" else "Conflict in source" if result["conflict_locus"] == "WITHIN_SOURCE" else {
            "CONSISTENT": "Consistent", "CONFLICTING": "Conflicting", "SINGLE_SOURCE": "Single source",
            "INSUFFICIENT": "Not verified", "UNCERTAIN": "Not verified", "NOT_APPLICABLE": "Not applicable",
        }[str(result["verdict"])]
        fields.append(PassportField(field_key=result["field_key"],label=label,public_text=result["public_text"],
            verdict=result["verdict"],conflict_locus=result["conflict_locus"],freshness=result["freshness"],
            review_state=result["review_state"],checked_at=result["confirmed_at"] or result["created_at"],
            citations=[Citation(**{k: getattr(p,k) for k in Citation.model_fields}) for p in passages]))
    if actor.role == Role.BUYER:
        read.passport_reads(increment=True)
    return PassportResponse(product_id=product_id,dataset_origin=product["dataset_origin"],
        last_checked_at=max((str(r["confirmed_at"] or r["created_at"]) for r in results),default=None),
        run_status=latest[0]["status"] if latest else None,fields=fields,
        disclaimer="Describes only the sources checked; it does not establish product origin or suitability.")


@router.get("/products/{product_id}/fields/{field_key}/evidence", response_model=EvidenceResponse)
def evidence(product_id: str, field_key: str, actor: Actor) -> EvidenceResponse:
    if field_key not in PUBLIC_FIELDS and actor.role not in {Role.REVIEWER,Role.OPERATOR,Role.SYSTEM}:
        raise HTTPException(404,"Field not found")
    case = read.one("SELECT * FROM cases WHERE product_id=?", (product_id,))
    result = read.one("SELECT * FROM field_results WHERE case_id=? AND field_key=? AND superseded_by IS NULL",
                      (case["id"],field_key))
    passages, hidden = read.evidence(str(result["citations_json"]), actor.role)
    return EvidenceResponse(citations=passages,hidden_citations=hidden)
