"""Deterministic ReMakePlace layout builder; geometry/import still need app testing."""
from copy import deepcopy
import math
from .housing import validate_layout_budget


def build_layout(db, seed, placements, *, scope='interior'):
    """Replace the selected furniture scope using DB identities; preserve other fields.

    Each placement contains item_id, location (native layout units, Z-up), and
    optional yaw_degrees. IDs must already exist in the supplied catalog.
    """
    if scope not in ('interior','exterior'):
        raise ValueError('scope must be interior or exterior')
    scale=seed.get(scope+'Scale')
    if isinstance(scale,bool) or not isinstance(scale,(int,float)) or not math.isfinite(scale) or scale<=0:
        raise ValueError(f'Seed needs a finite positive {scope}Scale')
    result=deepcopy(seed)
    items=[]
    for placement in placements:
        item=db.get_furniture(placement['item_id'])
        if item is None:
            raise ValueError(f"Unmapped Item ID: {placement['item_id']}")
        if item.get('scope')!=scope:
            raise ValueError(f"Furniture {item['id']} scope {item.get('scope')!r} cannot be exported to {scope}; unknown is not permitted")
        location=list(placement['location'])
        if len(location)!=3 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in location):
            raise ValueError('location must have three finite numbers')
        yaw=placement.get('yaw_degrees',0)
        if isinstance(yaw,bool) or not isinstance(yaw,(int,float)) or not math.isfinite(yaw):
            raise ValueError('yaw_degrees must be finite')
        angle=math.radians(yaw)/2
        items.append({'itemId':item['id'],'name':item['name'],
             'transform':{'location':location,'rotation':[0,0,math.sin(angle),math.cos(angle)],'scale':[1,1,1]},
             'properties':{},'attachments':[]})
    if not items:
        raise ValueError('At least one mapped furniture instance is required')
    field=scope+'Furniture'
    result[field]=items
    validate_layout_budget(result)
    assert {k:v for k,v in result.items() if k!=field}=={k:v for k,v in seed.items() if k!=field}
    return result


# FixtureWords.uasset (app data) lists these type/level strings; category->type mapping is by folder name.
FIXTURE_TYPE_BY_CATEGORY = {'Wallpaper': 'Wall', 'Flooring': 'Floor', 'CeilingLight': 'Light', 'MainDoor': 'Door', 'Window': 'Window',
                            'ExteriorWall': 'Exterior Wall', 'ExteriorWallDecor': 'Exterior Wall Decor', 'Roof': 'Roof',
                            'RoofDecor': 'Roof Decor', 'Fence': 'Fence', 'Placard': 'Placard'}
INTERIOR_FIXTURE_TYPES = {'Wall', 'Floor', 'Light'}
# Exterior types seen in real saves; others come from FixtureWords but were never observed inside exteriorFixture.
OBSERVED_EXTERIOR_TYPES = {'Door', 'Window', 'Exterior Wall'}


def apply_fixtures(db, layout, fixtures):
    """Set wallpaper/floor/light (per level) and exterior fixtures from the house_materials table.

    fixtures: [{'item_id': int, 'level': 'Ground Floor'|...}]  (level only for interior types).
    Interior: the seed must already hold that (type, level) slot (replaced in place; no inventing levels).
    Exterior: replaces the single entry of that type (level ''), or appends it. Returns (new_layout, warnings).
    Unknown item ids, Item-less materials and category/type mismatches are rejected.
    """
    result = deepcopy(layout); warnings = []
    for f in fixtures:
        row = db.connection.execute('SELECT asset_key,item_id,category,name FROM house_materials WHERE item_id=?', (f['item_id'],)).fetchone()
        if row is None:
            raise ValueError(f"Item ID {f['item_id']} is not a known house material")
        ftype = FIXTURE_TYPE_BY_CATEGORY.get(row['category'])
        if ftype is None:
            raise ValueError(f"Category {row['category']} has no fixture type")
        entry = {'level': '', 'type': ftype, 'name': row['name'], 'itemId': row['item_id'], 'color': f.get('color', '')}
        if ftype in INTERIOR_FIXTURE_TYPES:
            level = f.get('level')
            slots = [x for x in result['interiorFixture'] if x['type'] == ftype and x['level'] == level]
            if len(slots) != 1:
                raise ValueError(f'Seed has no unique interior {ftype} slot for level {level!r}')
            entry['level'] = level; slots[0].update(entry)
        else:
            if f.get('level'):
                raise ValueError('Exterior fixtures have no level')
            same = [x for x in result['exteriorFixture'] if x['type'] == ftype]
            if len(same) > 1:
                raise ValueError(f'Seed has several exterior {ftype} entries')
            if same: same[0].update(entry)
            else: result['exteriorFixture'].append(entry)
            if ftype not in OBSERVED_EXTERIOR_TYPES:
                warnings.append(f"exterior type {ftype!r} is in FixtureWords but was never seen in a real save's exteriorFixture; verify in app")
            if row['category'] in ('ExteriorWall', 'Roof', 'RoofDecor', 'ExteriorWallDecor') and result.get('houseSize'):
                warnings.append(f"{row['name']}: compatibility with houseSize {result['houseSize']} not verified")
    return result, warnings
