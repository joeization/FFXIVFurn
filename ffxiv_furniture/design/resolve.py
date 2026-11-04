"""Resolve plan entries to real DB furniture (interior scope, measured geometry, Item ID) and fixtures to house materials."""
from __future__ import annotations
from ..material_semantic import MaterialIndex

ROLE_CATEGORIES = {
    'seating': ('Furniture/Chair',), 'table': ('Furniture/Table',), 'storage': ('Furniture/Cabinet', 'Furniture/Shelf'),
    'rug': ('Furniture/Rug',), 'wall-art': ('Furniture/Wall-Mounted', 'Item/Printed'), 'lighting': ('Lighting',), 'decor': (), 'architecture': ('Fixture',),
}
EXCLUDED_CATEGORIES = ('Fixture',)  # partitions/pillars/doors are structure, not decor picks
MAX_EXTENT_M, MAX_HEIGHT_M = 24.0, 6.5   # only what cannot physically fit the Medium room (24 m wide, 6.5 m ceiling); no taste-based size cap
TAG_BOOST = 0.03


def _geometry(db, item_id):
    c = db.connection
    r = c.execute('''SELECT f.name,f.length,f.width,f.height,g.min_x,g.min_y,g.min_z,g.max_x,g.max_y,g.max_z,a.source_category,
        p.placement_type,p.small,p.front_deg,p.supports_top,p.top_z_local,p.top_area_fraction,p.mount_bottom_z
        FROM furniture f JOIN asset_geometry g ON g.item_id=f.id JOIN candidate_assets a ON a.item_id=f.id
        LEFT JOIN placement_info p ON p.item_id=f.id WHERE f.id=?''', (item_id,)).fetchone()
    if r is None: return None
    out = dict(name=r[0], length=r[1], width=r[2], height=r[3], lo=[r[4], r[5], r[6]], hi=[r[7], r[8], r[9]], category=r[10])
    if r[11] is not None:   # placement_info measured by scripts/fill_placement_info.py
        aspect = abs(r[1] - r[2]) / max(r[1], r[2], 1e-9)
        out.update(ptype=r[11], small=bool(r[12]), front_deg=r[13], supports_top=bool(r[14]), top_z_local=r[15], top_area_fraction=r[16], mount_bottom_z=r[17],
                   round_top=bool(r[14]) and aspect < 0.15 and r[16] < 0.85)
    try:   # every flat board / top measured from the mesh (scripts/fill_support_surfaces.py); optional table
        rows = db.connection.execute('SELECT z_local,min_x,min_y,max_x,max_y,area_m2,clearance_above_m FROM support_surfaces WHERE item_id=? ORDER BY z_local', (item_id,)).fetchall()
        if rows: out['surfaces'] = [{'z': r[0], 'min_x': r[1], 'min_y': r[2], 'max_x': r[3], 'max_y': r[4], 'area_m2': r[5], 'clearance_m': r[6]} for r in rows]
    except Exception: pass
    return out


def resolve_furniture(db, index, plan, *, top_k=80, options=24):
    """Returns (resolved, report). Each resolved entry has the chosen item and what was considered."""
    c = db.connection; resolved = []; report = []
    tagid = {f'{t[1]}:{t[2]}': t[0] for t in c.execute('SELECT id,category,name FROM tags')}
    for zi, zone in enumerate(plan['zones']):
        for ei, e in enumerate(zone['items']):
            hits = index.search(e['query'], top_k=top_k, scope='interior')
            cand = []
            for h in hits:
                g = _geometry(db, h['furniture']['id'])
                if g is None or (g['category'].startswith(EXCLUDED_CATEGORIES) and e['role'] != 'architecture'): continue
                if max(g['length'], g['width']) > MAX_EXTENT_M or g['height'] > MAX_HEIGHT_M: continue
                tags = {f'{r[0]}:{r[1]}' for r in c.execute('SELECT t.category,t.name FROM furniture_tags ft JOIN tags t ON t.id=ft.tag_id WHERE ft.furniture_id=?', (h['furniture']['id'],))}
                boost = TAG_BOOST * sum(t in tags for t in e['tags'])
                cand.append({'item_id': h['furniture']['id'], 'similarity': h['similarity'], 'score': h['similarity'] + boost, 'geometry': g})
            allowed = ROLE_CATEGORIES[e['role']]
            matched = [x for x in cand if x['geometry']['category'].startswith(allowed)] if allowed else cand
            pool = matched + [x for x in cand if x not in matched] if allowed else cand   # role-matching categories first, the rest after (the model decides, flagged by category)
            if not pool:
                report.append({'zone': zone['name'], 'entry': e, 'status': 'no candidate with geometry'}); continue
            pool = sorted(pool, key=lambda x: (0 if x in matched or not allowed else 1, -x['score'], x['item_id']))
            best = pool[0]
            opts = []
            for x in pool[:options]:
                d = c.execute('SELECT description FROM furniture WHERE id=?', (x['item_id'],)).fetchone()[0]
                tg = [f'{r[0]}:{r[1]}' for r in c.execute('SELECT t.category,t.name FROM furniture_tags ft JOIN tags t ON t.id=ft.tag_id WHERE ft.furniture_id=? AND t.category NOT IN ("function","scope") LIMIT 8', (x['item_id'],))]
                try: col = c.execute('SELECT hue_name,c1_hex,c2_hex FROM item_colors WHERE item_id=?', (x['item_id'],)).fetchone()
                except Exception: col = None
                g = x['geometry']; fit = c.execute('SELECT placement_type,supports_top FROM placement_info WHERE item_id=?', (x['item_id'],)).fetchone()
                opts.append({'item_id': x['item_id'], 'name': g['name'], 'category': g['category'], 'size_m': [round(g['length'], 2), round(g['width'], 2), round(g['height'], 2)],
                             'placement': (fit[0] + (', flat top' if fit[1] else '')) if fit else None, 'matches_role_category': (not allowed) or g['category'].startswith(allowed), 'colour': ({'name': col[0], 'main': col[1], 'second': col[2]} if col and col[0] else None), 'shelf_boards': len(g.get('surfaces') or []) or None,
                             'description': d[:240], 'tags': tg, 'similarity': round(x['similarity'], 3), 'geometry': g})
            resolved.append({'zone_index': zi, 'zone': zone['name'], 'area_fraction': zone['area_fraction'], 'role': e['role'], 'count': e['count'], 'query': e['query'], 'placement': e.get('placement', {}), 'entry_key': f'{zi}:{ei}', 'region': zone.get('region'), 'item_id': best['item_id'], 'geometry': best['geometry'], 'similarity': best['similarity'], 'options': opts})
            report.append({'zone': zone['name'], 'role': e['role'], 'query': e['query'], 'chosen': best['geometry']['name'], 'item_id': best['item_id'], 'category': best['geometry']['category'],
                           'similarity': round(best['similarity'], 3), 'role_category_match': bool(matched),
                           'runner_ups': [(x['geometry']['name'], round(x['score'], 3)) for x in sorted(pool, key=lambda x: -x['score'])[1:4]]})
    return resolved, report


FIXTURE_CATEGORY = {'floor': 'Flooring', 'wall': 'Wallpaper', 'light': 'CeilingLight'}


def resolve_fixtures(index: MaterialIndex, plan):
    out = []
    for kind, query in plan['fixtures'].items():
        hit = index.search_materials(query, top_k=3, category=FIXTURE_CATEGORY[kind])
        if not hit: raise ValueError(f'No {kind} material for query {query!r}')
        out.append({'kind': kind, 'query': query, 'item_id': hit[0]['item_id'], 'name': hit[0]['name'], 'similarity': round(hit[0]['similarity'], 3),
                    'runner_ups': [(h['name'], round(h['similarity'], 3)) for h in hit[1:]]})
    return out
