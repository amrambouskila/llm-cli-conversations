from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from db import get_graph_service
from schemas import WikiArticle, WikiIndex, WikiLookup
from services.graph_service import GraphService

router = APIRouter(prefix="/api/graph/wiki", tags=["graph"])


@router.get("/index", response_model=WikiIndex)
async def get_wiki_index(
    service: GraphService = Depends(get_graph_service),
) -> dict:
    data = await service.load_wiki_index()
    if data is None:
        raise HTTPException(status_code=404, detail="Wiki index not found")
    return data


@router.get("/lookup", response_model=WikiLookup)
async def get_wiki_lookup(
    concept_id: str | None = Query(None),
    concept_name: str | None = Query(None),
    service: GraphService = Depends(get_graph_service),
) -> dict:
    slug = await service.resolve_wiki_slug(concept_id=concept_id, concept_name=concept_name)
    if slug is None:
        raise HTTPException(status_code=404, detail="No matching wiki article")
    return {"slug": slug}


@router.get("/{slug}", response_model=WikiArticle)
async def get_wiki_article(
    slug: str,
    service: GraphService = Depends(get_graph_service),
) -> dict:
    data = await service.load_wiki_article(slug)
    if data is None:
        raise HTTPException(status_code=404, detail="Wiki article not found")
    return data
