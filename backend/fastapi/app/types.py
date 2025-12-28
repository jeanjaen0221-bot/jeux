from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class NodeIn(BaseModel):
    id: str
    node_type: str
    name: str
    parent_id: Optional[str] = None
    slug: Optional[str] = None
    chunk_id: Optional[str] = None
    attrs: Dict[str, Any] = Field(default_factory=dict)

class LinkIn(BaseModel):
    id: str
    src_id: str
    dst_id: str
    link_type: str
    weight: Optional[float] = None
    attrs: Dict[str, Any] = Field(default_factory=dict)

class BulkUpsertIn(BaseModel):
    nodes: List[NodeIn] = Field(default_factory=list)
    links: List[LinkIn] = Field(default_factory=list)

class GenerateChunkIn(BaseModel):
    seed: int
    scope_type: str  # "country" | "city"
    scope_node_id: Optional[str] = None  # if None, new will be created

class GenerateChunkOut(BaseModel):
    chunk_id: str
    nodes_count: int
    links_count: int

class ChunkStats(BaseModel):
    chunk_id: str
    nodes_by_type: Dict[str, int]
    links_count: int
