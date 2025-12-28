import os
import uuid
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException
from sqlalchemy import text
from .db import engine, session
from .types import BulkUpsertIn, GenerateChunkIn, GenerateChunkOut, ChunkStats
from .services.generation.steampunk import generate_chunk

API_KEY = os.getenv("API_KEY")
STEAMPUNK_CONFIG_PATH = os.getenv("STEAMPUNK_CONFIG_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "steampunk_gen_config.yaml")))

app = FastAPI(title="World Editor API", version="1.0")


def require_api_key(x_api_key: Optional[str] = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/api/bulk_upsert", dependencies=[Depends(require_api_key)])
def bulk_upsert(payload: BulkUpsertIn):
    with session() as conn:
        for n in payload.nodes:
            conn.execute(text(
                """
                INSERT INTO nodes (id, node_type, name, parent_id, slug, chunk_id, attrs)
                VALUES (:id::uuid, :node_type, :name, :parent_id::uuid, :slug, :chunk_id, :attrs::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                  node_type = EXCLUDED.node_type,
                  name = EXCLUDED.name,
                  parent_id = EXCLUDED.parent_id,
                  slug = EXCLUDED.slug,
                  chunk_id = EXCLUDED.chunk_id,
                  attrs = EXCLUDED.attrs,
                  updated_at = NOW()
                """
            ), {
                "id": n.id,
                "node_type": n.node_type,
                "name": n.name,
                "parent_id": n.parent_id,
                "slug": n.slug,
                "chunk_id": n.chunk_id,
                "attrs": n.attrs,
            })
        for l in payload.links:
            conn.execute(text(
                """
                INSERT INTO links (id, src_id, dst_id, link_type, weight, attrs)
                VALUES (:id::uuid, :src_id::uuid, :dst_id::uuid, :link_type, :weight, :attrs::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                  src_id = EXCLUDED.src_id,
                  dst_id = EXCLUDED.dst_id,
                  link_type = EXCLUDED.link_type,
                  weight = EXCLUDED.weight,
                  attrs = EXCLUDED.attrs
                """
            ), {
                "id": l.id,
                "src_id": l.src_id,
                "dst_id": l.dst_id,
                "link_type": l.link_type,
                "weight": l.weight,
                "attrs": l.attrs,
            })
    return {"inserted": len(payload.nodes) + len(payload.links)}

@app.post("/api/generate/chunk", response_model=GenerateChunkOut, dependencies=[Depends(require_api_key)])
def api_generate_chunk(body: GenerateChunkIn):
    result = generate_chunk(config_path=STEAMPUNK_CONFIG_PATH, seed=body.seed, scope_type=body.scope_type, scope_node_id=body.scope_node_id)
    with session() as conn:
        # ensure chunk row
        conn.execute(text(
            """
            INSERT INTO chunks (chunk_id, scope_type, scope_node_id, status, attrs)
            VALUES (:chunk_id, :scope_type, :scope_node_id::uuid, 'generated', :attrs::jsonb)
            ON CONFLICT (chunk_id)
            DO UPDATE SET status = 'generated', attrs = EXCLUDED.attrs, updated_at = NOW()
            """
        ), {
            "chunk_id": result["chunk_id"],
            "scope_type": body.scope_type,
            "scope_node_id": result["scope_node_id"],
            "attrs": {"seed": body.seed}
        })
        # upsert nodes
        for n in result["nodes"]:
            conn.execute(text(
                """
                INSERT INTO nodes (id, node_type, name, parent_id, slug, chunk_id, attrs)
                VALUES (:id::uuid, :node_type, :name, :parent_id::uuid, :slug, :chunk_id, :attrs::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                  node_type = EXCLUDED.node_type,
                  name = EXCLUDED.name,
                  parent_id = EXCLUDED.parent_id,
                  slug = EXCLUDED.slug,
                  chunk_id = EXCLUDED.chunk_id,
                  attrs = EXCLUDED.attrs,
                  updated_at = NOW()
                """
            ), n)
        for l in result["links"]:
            conn.execute(text(
                """
                INSERT INTO links (id, src_id, dst_id, link_type, weight, attrs)
                VALUES (:id::uuid, :src_id::uuid, :dst_id::uuid, :link_type, :weight, :attrs::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                  src_id = EXCLUDED.src_id,
                  dst_id = EXCLUDED.dst_id,
                  link_type = EXCLUDED.link_type,
                  weight = EXCLUDED.weight,
                  attrs = EXCLUDED.attrs
                """
            ), l)
        # mark validated (simple pass)
        conn.execute(text("UPDATE chunks SET status='validated', updated_at=NOW() WHERE chunk_id=:cid"), {"cid": result["chunk_id"]})
    return GenerateChunkOut(chunk_id=result["chunk_id"], nodes_count=len(result["nodes"]), links_count=len(result["links"]) )

@app.get("/api/chunks/{chunk_id}/stats", response_model=ChunkStats, dependencies=[Depends(require_api_key)])
def api_chunk_stats(chunk_id: str):
    nodes_by_type = {}
    links_count = 0
    with session() as conn:
        res = conn.execute(text("SELECT node_type, COUNT(*) FROM nodes WHERE chunk_id = :cid GROUP BY node_type"), {"cid": chunk_id})
        for nt, c in res:
            nodes_by_type[nt] = int(c)
        res2 = conn.execute(text("SELECT COUNT(*) FROM links l JOIN nodes n ON l.src_id = n.id WHERE n.chunk_id = :cid"), {"cid": chunk_id})
        links_count = int(res2.scalar_one())
    return ChunkStats(chunk_id=chunk_id, nodes_by_type=nodes_by_type, links_count=links_count)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.fastapi.app.main:app", host="127.0.0.1", port=8000, reload=True)
