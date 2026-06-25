# app/routes/paper_routes.py

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/paper/{pmid}", include_in_schema=False)
async def legacy_pubmed_detail(pmid: str):
    return RedirectResponse(url=f"/paper/pubmed/{pmid}")


@router.get("/paper/europe_pmc/{pid}", include_in_schema=False)
async def legacy_epmc_detail(pid: str):
    return RedirectResponse(url=f"/paper/europe_pmc/{pid}")


@router.get("/paper/semantic_scholar/{pid}", include_in_schema=False)
async def legacy_semantic_scholar_detail(pid: str):
    return RedirectResponse(url=f"/paper/semantic_scholar/{pid}")