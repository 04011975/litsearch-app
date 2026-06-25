# app/routes/paper_routes.py

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.paper_service import build_paper_detail_dict

router = APIRouter()


@router.get("/paper/{source}/{pid}", response_class=HTMLResponse)
async def paper_detail(request: Request, source: str, pid: str):
    state = request.app.state

    if source not in state.allowed_sources:
        raise HTTPException(status_code=404, detail="Not Found")

    paper = await state.fetch_detail_by_source(source, pid)
    if not paper:
        raise HTTPException(status_code=404, detail="Not Found")

    d = build_paper_detail_dict(
        paper,
        source=source,
        pid=pid,
        paper_to_dict=state.paper_to_dict,
        pubmed_external_url=state.pubmed_external_url,
        europe_pmc_external_url=state.europe_pmc_external_url,
    )

    return state.templates.TemplateResponse(
        "paper.html",
        {
            "request": request,
            "pid": pid,
            "paper": d,
            "error": None,
            "source": source,
        },
    )


@router.get("/paper/{pmid}", include_in_schema=False)
async def legacy_pubmed_detail(pmid: str):
    return RedirectResponse(url=f"/paper/pubmed/{pmid}")


@router.get("/paper/europe_pmc/{pid}", include_in_schema=False)
async def legacy_epmc_detail(pid: str):
    return RedirectResponse(url=f"/paper/europe_pmc/{pid}")


@router.get("/paper/semantic_scholar/{pid}", include_in_schema=False)
async def legacy_semantic_scholar_detail(pid: str):
    return RedirectResponse(url=f"/paper/semantic_scholar/{pid}")