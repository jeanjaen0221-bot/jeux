from __future__ import annotations
import os
import json
import uuid
import math
import random
import hashlib
from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path
import yaml

# -------- utils --------

def _seed_to_namespace(seed: int) -> uuid.UUID:
    h = hashlib.sha256(f"steampunk:{seed}".encode()).digest()
    return uuid.UUID(bytes=h[:16])

def _uuid5_ns(seed_ns: uuid.UUID, name: str) -> str:
    return str(uuid.uuid5(seed_ns, name))

def _rng(seed: int, stream: str) -> random.Random:
    h = hashlib.sha256(f"{seed}:{stream}".encode()).hexdigest()
    return random.Random(int(h[:16], 16))

# -------- config --------

def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# -------- generator --------

def generate_chunk(config_path: str, seed: int, scope_type: str, scope_node_id: Optional[str]) -> Dict[str, Any]:
    cfg = _load_yaml(config_path)
    ns = _seed_to_namespace(seed)

    worldp = cfg["world_params"]
    namep = worldp["name_pools"]
    buildings_cfg = {b["id"]: b for b in cfg["buildings"]}
    professions_cfg = cfg["professions"]
    prof_by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for p in professions_cfg:
        prof_by_cat.setdefault(p["category"], []).append(p)

    factions = cfg["factions"]
    faction_by_id = {f["id"]: f for f in factions}

    # choose chunk id
    if scope_type == "country":
        if not scope_node_id:
            # pick a country name deterministically
            r = _rng(seed, "country-name")
            cname = r.choice(namep["countries"])
            country_id = _uuid5_ns(ns, f"country:{cname}")
        else:
            country_id = scope_node_id
        chunk_id = f"country:{country_id}"
    elif scope_type == "city":
        if not scope_node_id:
            r = _rng(seed, "city-name")
            cname = r.choice(namep["cities"])
            city_id = _uuid5_ns(ns, f"city:{cname}")
        else:
            city_id = scope_node_id
        chunk_id = f"city:{city_id}"
    else:
        raise ValueError("scope_type must be 'country' or 'city'")

    nodes: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []

    # ---- helpers ----
    def add_node(node_type: str, name: str, parent_id: Optional[str], attrs: Dict[str, Any], slug: Optional[str] = None, fixed_id: Optional[str] = None) -> str:
        nid = fixed_id or _uuid5_ns(ns, f"{chunk_id}:{node_type}:{name}:{parent_id}")
        nodes.append({
            "id": nid,
            "node_type": node_type,
            "name": name,
            "parent_id": parent_id,
            "slug": slug,
            "chunk_id": chunk_id,
            "attrs": attrs,
        })
        return nid

    def add_link(src_id: str, dst_id: str, link_type: str, weight: Optional[float] = None, attrs: Optional[Dict[str, Any]] = None):
        lid = _uuid5_ns(ns, f"{chunk_id}:link:{src_id}:{dst_id}:{link_type}")
        links.append({
            "id": lid,
            "src_id": src_id,
            "dst_id": dst_id,
            "link_type": link_type,
            "weight": weight,
            "attrs": attrs or {},
        })

    # ---- build country + cities ----
    topo_rng = _rng(seed, cfg["random"]["streams"]["topology"])
    style_rng = _rng(seed, cfg["random"]["streams"]["style"])
    pop_rng = _rng(seed, cfg["random"]["streams"]["population"])
    place_rng = _rng(seed, cfg["random"]["streams"]["placement"])
    factions_rng = _rng(seed, cfg["random"]["streams"]["factions"])

    if scope_type == "country":
        # country node
        rname = topo_rng.choice(namep["countries"]) if not scope_node_id else None
        cid = scope_node_id or _uuid5_ns(ns, f"country:{rname}")
        country_name = rname or rname or "Country"
        country_node_id = add_node("country", country_name, None, {
            "tech": style_rng.choice(cfg["styles"]["technologies"]),
            "wealth": topo_rng.choice(["low", "medium", "high"])
        }, fixed_id=cid)

        # decide how many cities for this country
        total_countries = worldp["countries"]
        total_cities = worldp["cities_total"]
        base = total_cities // total_countries
        remainder = total_cities % total_countries
        # deterministic assignment of remainder
        country_index = int(uuid.UUID(country_node_id)) % total_countries
        city_count = base + (1 if country_index < remainder else 0)
        cities_to_make = city_count
        # make cities
        city_ids: List[str] = []
        for i in range(cities_to_make):
            cname = topo_rng.choice(namep["cities"]) + f" {i+1}"
            city_id = add_node("city", cname, country_node_id, {
                "dominant_industry": topo_rng.choice(["manufacturing", "shipyard", "academia", "mining"]),
                "wealth": topo_rng.choice(["low", "medium", "high"]),
                "density": topo_rng.choice(worldp["city_density_levels"]),
                "population_target": pop_rng.randint(worldp["city_size_range"][0], worldp["city_size_range"][1]),
            })
            city_ids.append(city_id)
            _generate_city_contents(cfg, ns, chunk_id, city_id, buildings_cfg, style_rng, topo_rng, nodes)
        # generate NPCs and place them per city
        for city_id in city_ids:
            _generate_npcs_for_city(cfg, ns, chunk_id, city_id, prof_by_cat, buildings_cfg, faction_by_id, pop_rng, factions_rng, place_rng, nodes, links)

        scope_node_id_out = country_node_id

    else:  # city chunk
        # if city id not set, create an orphan city (parent can be linked later)
        rname = topo_rng.choice(namep["cities"]) if not scope_node_id else None
        city_node_id = add_node("city", rname or "City", None, {
            "dominant_industry": topo_rng.choice(["manufacturing", "shipyard", "academia", "mining"]),
            "wealth": topo_rng.choice(["low", "medium", "high"]),
            "density": topo_rng.choice(worldp["city_density_levels"]),
            "population_target": pop_rng.randint(worldp["city_size_range"][0], worldp["city_size_range"][1]),
        }, fixed_id=(scope_node_id or None))
        _generate_city_contents(cfg, ns, chunk_id, city_node_id, buildings_cfg, style_rng, topo_rng, nodes)
        _generate_npcs_for_city(cfg, ns, chunk_id, city_node_id, prof_by_cat, buildings_cfg, faction_by_id, pop_rng, factions_rng, place_rng, nodes, links)
        scope_node_id_out = city_node_id

    return {"chunk_id": chunk_id, "nodes": nodes, "links": links, "scope_node_id": scope_node_id_out}


def _generate_city_contents(cfg: Dict[str, Any], ns: uuid.UUID, chunk_id: str, city_id: str, buildings_cfg: Dict[str, Dict[str, Any]], style_rng, topo_rng, nodes: List[Dict[str, Any]]):
    def add(node_type, name, parent, attrs, slug=None, fixed_id=None):
        nid = str(uuid.uuid5(ns, f"{chunk_id}:{node_type}:{name}:{parent}")) if not fixed_id else fixed_id
        nodes.append({"id": nid, "node_type": node_type, "name": name, "parent_id": parent, "slug": slug, "chunk_id": chunk_id, "attrs": attrs})
        return nid

    # districts
    dmin, dmax = cfg["world_params"]["district_per_city_range"]
    dcount = topo_rng.randint(dmin, dmax)
    archs = cfg["styles"]["district_archetypes"]
    district_ids: List[Tuple[str, Dict[str, Any]]] = []
    for i in range(dcount):
        arch = topo_rng.choice(archs)
        dname = arch["id"].capitalize() + f" District {i+1}"
        did = add("district", dname, city_id, {
            "archetype": arch["id"],
            "pollution": arch.get("pollution_bias", "medium"),
            "wealth_bias": arch.get("wealth_bias", "medium"),
            "tags": arch.get("tags", []),
        })
        district_ids.append((did, arch))

    # buildings
    target_buildings = cfg["world_params"]["building_count_target"]
    per_city = max(1, target_buildings // max(1, cfg["world_params"]["cities_total"]))

    # ensure required buildings for some industries/economy
    required_pool = []
    for ind in cfg["industries"]:
        required_pool.extend(ind.get("required_buildings", []))

    all_buildings = list(buildings_cfg.values())

    built = 0
    for (did, arch) in district_ids:
        # baseline 5-20 buildings per district, then trimmed to per_city
        b_target = topo_rng.randint(5, 20)
        candidates = [b for b in all_buildings if arch["id"] in b.get("preferred_districts", [])]
        if not candidates:
            candidates = all_buildings
        for j in range(b_target):
            bcfg = topo_rng.choice(candidates)
            bname = bcfg["id"].replace("_", " ").title() + f" {j+1}"
            cap = int(round(bcfg["base_capacity"] * topo_rng.uniform(0.9, 1.1)))
            add("building", bname, did, {
                "building_id": bcfg["id"],
                "capacity": cap,
                "tags": bcfg.get("tags", []),
            })
            built += 1
            if built >= per_city:
                break
        if built >= per_city:
            break

    # floors/rooms omitted for brevity; can be expanded later


def _collect_city_snapshot(nodes: List[Dict[str, Any]], city_id: str) -> Dict[str, Any]:
    # Build lookups
    districts = [n for n in nodes if n["node_type"] == "district" and n["parent_id"] == city_id]
    buildings = [n for n in nodes if n["node_type"] == "building" and n["parent_id"] in {d["id"] for d in districts}]
    by_district: Dict[str, List[Dict[str, Any]]] = {d["id"]: [] for d in districts}
    for b in buildings:
        by_district[b["parent_id"]].append(b)
    facility_tags = set()
    for b in buildings:
        for t in b["attrs"].get("tags", []):
            facility_tags.add(t)
    return {
        "districts": districts,
        "buildings": buildings,
        "by_district": by_district,
        "facility_tags": facility_tags,
    }


def _generate_npcs_for_city(cfg: Dict[str, Any], ns: uuid.UUID, chunk_id: str, city_id: str, prof_by_cat: Dict[str, List[Dict[str, Any]]], buildings_cfg: Dict[str, Dict[str, Any]], faction_by_id: Dict[str, Any], pop_rng, factions_rng, place_rng, nodes: List[Dict[str, Any]], links: List[Dict[str, Any]]):
    # compute city attrs
    city_node = next(n for n in nodes if n["id"] == city_id)
    dom_ind = city_node["attrs"]["dominant_industry"]
    wealth = city_node["attrs"]["wealth"]
    pop_target = int(city_node["attrs"]["population_target"])

    # ratios lookup
    ratios_entries = cfg["ratios"]
    ratio = next((r for r in ratios_entries if r["key"] == [dom_ind, wealth]), None)
    if not ratio:
        ratio = ratios_entries[0]
    cat_shares = ratio["categories"]

    # collect city snapshot
    snap = _collect_city_snapshot(nodes, city_id)

    # filter professions by available facilities
    allowed_profs_by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for cat, lst in prof_by_cat.items():
        allowed = []
        for p in lst:
            req = p.get("requires_facility_tags", [])
            if not req or any(tag in snap["facility_tags"] for tag in req):
                allowed.append(p)
        if allowed:
            allowed_profs_by_cat[cat] = allowed

    # expand profession counts
    prof_counts: Dict[str, int] = {}
    npc_target = pop_target
    for cat, share in cat_shares.items():
        if cat not in allowed_profs_by_cat:
            continue
        count_cat = int(round(npc_target * share))
        weights = [p.get("weight", 1.0) for p in allowed_profs_by_cat[cat]]
        weight_sum = sum(weights) or 1.0
        for p, w in zip(allowed_profs_by_cat[cat], weights):
            prof_counts[p["id"]] = prof_counts.get(p["id"], 0) + int(round(count_cat * (w / weight_sum)))

    # placement prep
    buildings = snap["buildings"]
    by_district = snap["by_district"]
    capacity_left = {b["id"]: int(b["attrs"].get("capacity", 0)) for b in buildings}
    prof_in_district: Dict[Tuple[str, str], int] = {}

    diversity_pct = cfg["placement_rules"]["diversity"]["max_same_profession_pct_per_district"]
    overflow_type = cfg["placement_rules"]["failsafe"]["overflow_building"]

    # make a quick lookup for buildings by tags and by district
    buildings_by_tag: Dict[str, List[Dict[str, Any]]] = {}
    for b in buildings:
        for t in b["attrs"].get("tags", []):
            buildings_by_tag.setdefault(t, []).append(b)

    def add_node_local(node_type: str, name: str, parent_id: Optional[str], attrs: Dict[str, Any]):
        nid = str(uuid.uuid5(ns, f"{chunk_id}:{node_type}:{name}:{parent_id}"))
        nodes.append({"id": nid, "node_type": node_type, "name": name, "parent_id": parent_id, "slug": None, "chunk_id": chunk_id, "attrs": attrs})
        return nid

    def place_in_building(p: Dict[str, Any], district_pref: List[str]) -> Optional[str]:
        # Try preferred districts first
        allowed_tags = set(p.get("allowed_building_tags", []))
        candidate_buildings = [b for b in buildings if allowed_tags & set(b["attrs"].get("tags", []))]
        # Bias by district preferences
        if district_pref:
            candidate_buildings.sort(key=lambda b: 0 if any(_district_name(b["parent_id"]) in district_pref or _district_arch(b["parent_id"]) in district_pref else 1)
                                     )
        # Try to keep diversity per district
        for b in candidate_buildings:
            if capacity_left.get(b["id"], 0) <= 0:
                continue
            d = b["parent_id"]
            key = (d, p["id"])  # district, profession
            cur = prof_in_district.get(key, 0)
            total_in_d = sum(v for (dd, _), v in prof_in_district.items() if dd == d) or 1
            if (cur + 1) / total_in_d > diversity_pct and total_in_d > 5:
                continue
            capacity_left[b["id"]] -= 1
            prof_in_district[key] = cur + 1
            return b["id"]
        # overflow
        ob = next((b for b in buildings if b["attrs"].get("building_id") == overflow_type and capacity_left.get(b["id"], 0) > 0), None)
        if ob:
            capacity_left[ob["id"]] -= 1
            key = (ob["parent_id"], p["id"])  # still track
            prof_in_district[key] = prof_in_district.get(key, 0) + 1
            return ob["id"]
        return None

    # helpers for district info
    _district_cache_name: Dict[str, str] = {d["id"]: d["name"].lower() for d in snap["districts"]}
    _district_cache_arch: Dict[str, str] = {d["id"]: d["attrs"].get("archetype", "") for d in snap["districts"]}

    def _district_name(did: str) -> str:
        return _district_cache_name.get(did, "")

    def _district_arch(did: str) -> str:
        return _district_cache_arch.get(did, "")

    # generate faction membership weights per district
    def faction_for(npc_cat: str, did: str) -> Optional[str]:
        # compute weights from cfg influence
        weights: List[Tuple[str, float]] = []
        tags = set()
        for b in by_district.get(did, []):
            tags.update(b["attrs"].get("tags", []))
        for fid, f in faction_by_id.items():
            if npc_cat not in f.get("admits_categories", []):
                continue
            w = float(f.get("influence", {}).get("country", {}).get("base", 0.0))
            w += float(f.get("influence", {}).get("city", {}).get(_district_arch(did), 0.0))
            for t in tags:
                w += float(f.get("influence", {}).get("district_tags", {}).get(t, 0.0))
            if w > 0:
                weights.append((fid, w))
        if not weights:
            return None
        total = sum(w for _, w in weights)
        pick = factions_rng.random() * total
        acc = 0.0
        for fid, w in weights:
            acc += w
            if pick <= acc:
                return fid
        return weights[-1][0]

    # create NPCs
    name_given = cfg["world_params"]["name_pools"]["given_names"]
    name_surn = cfg["world_params"]["name_pools"]["surnames"]

    created = 0
    for prof_id, count in prof_counts.items():
        p = next(pp for pp in sum(prof_by_cat.values(), []) if pp["id"] == prof_id)
        cat = p["category"]
        for i in range(count):
            g = pop_rng.choice(name_given)
            s = pop_rng.choice(name_surn)
            npc_name = f"{g} {s}"
            # place
            b_id = place_in_building(p, p.get("preferred_districts", []))
            if not b_id and cfg["placement_rules"]["failsafe"]["create_overflow_if_missing"]:
                # create overflow building in a random district
                any_d = next(iter(by_district.keys()))
                ob_name = "Boarding House Overflow"
                ob_node = {
                    "id": str(uuid.uuid5(ns, f"{chunk_id}:building:{ob_name}:{any_d}")),
                    "node_type": "building",
                    "name": ob_name,
                    "parent_id": any_d,
                    "slug": None,
                    "chunk_id": chunk_id,
                    "attrs": {"building_id": cfg["placement_rules"]["failsafe"]["overflow_building"], "capacity": 100, "tags": ["residential", "overflow"]}
                }
                nodes.append(ob_node)
                capacity_left[ob_node["id"]] = 100
                b_id = ob_node["id"]
            # create npc node regardless, but parent is building if available
            npc_id = str(uuid.uuid5(ns, f"{chunk_id}:npc:{npc_name}:{b_id or city_id}"))
            faction_id = faction_for(cat, next((b["parent_id"] for b in buildings if b["id"] == b_id), city_id)) if b_id else None
            nodes.append({
                "id": npc_id,
                "node_type": "npc",
                "name": npc_name,
                "parent_id": b_id or city_id,
                "slug": None,
                "chunk_id": chunk_id,
                "attrs": {"profession": prof_id, "category": cat, "faction_id": faction_id}
            })
            if faction_id:
                _add_link(ns, chunk_id, npc_id, _uuid_faction(ns, chunk_id, faction_id), "member_of", 0.8, None, links)
            created += 1

    # ensure faction nodes exist
    for fid in faction_by_id.keys():
        fnid = _uuid_faction(ns, chunk_id, fid)
        if not any(n for n in nodes if n["id"] == fnid):
            nodes.append({
                "id": fnid,
                "node_type": "faction",
                "name": fid.replace("_", " ").title(),
                "parent_id": None,
                "slug": None,
                "chunk_id": chunk_id,
                "attrs": {"id": fid}
            })

    # attach created nodes/links back to caller
    # (they reference the global lists)

def _add_link(ns: uuid.UUID, chunk_id: str, src_id: str, dst_id: str, link_type: str, weight: Optional[float], attrs: Optional[Dict[str, Any]], links: List[Dict[str, Any]]):
    lid = str(uuid.uuid5(ns, f"{chunk_id}:link:{src_id}:{dst_id}:{link_type}"))
    links.append({"id": lid, "src_id": src_id, "dst_id": dst_id, "link_type": link_type, "weight": weight, "attrs": attrs or {}})

def _uuid_faction(ns: uuid.UUID, chunk_id: str, fid: str) -> str:
    return str(uuid.uuid5(ns, f"{chunk_id}:faction:{fid}"))
