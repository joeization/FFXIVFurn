"""Shared, evidence-backed Medium interior geometry for MCP and render.
Native local enclosure transforms remain approximate; stairs use map component
base transforms or named per-style overrides, never screenshot corrections.
"""
from copy import deepcopy
from functools import lru_cache
import math
from pathlib import Path
import struct
import numpy as np
from .config import source_path
from .geometry import read_static_mesh_bounds
from .geometry_mesh import read_static_mesh_triangles

ROOT = Path(__file__).resolve().parents[1]
CONTENT = source_path('interiors')
BASE = CONTENT / 'HouseAssets/InteriorStyles'
STYLES = ('Shirogane', 'Mist', 'LavBed', 'Goblet', 'Empyreum', 'Minimalist', 'DarkMinimalist')
LEVEL_Z = {'ground': 0.0, 'upper': 7.0}


def validate_style(style):
    if style not in STYLES:
        raise ValueError(f'Unknown interior {style!r}; expected one of {STYLES}')
    return style


@lru_cache(maxsize=1)
def medium_actor_transforms():
    """Bounded UE5.3 Medium decode: named override entries and component defaults.
    Component fields148/149/150 are RelativeLocation/Rotation/Scale. Rotation
    absent in all four exports => SceneComponent default zero; not an inferred
    rotation chosen by geometric fitting. Restrict to the exact observed layouts.
    """
    from .rendering.native import Reader, names, tables
    path = source_path('houses') / 'Maps/XIVMediumHouse.umap'
    tab = tables.map_tables(path); data = path.with_suffix('.uexp').read_bytes()
    result = {}
    for actor in ('Stairs', 'Stairs2_9', 'Railing', 'Railing2_2'):
        e = next(e for e in tab['exports'] if e['name'] == actor)
        b = data[e['serial_offset_in_uexp']:e['serial_offset_in_uexp'] + e['serial_size']]
        if struct.unpack_from('<I', b, 14)[0] != 2: raise ValueError('Unknown DistrictFixture overrides layout')
        pos = 18; overrides = {}
        for expected in ('Minimalist', 'DarkMinimalist'):
            n = struct.unpack_from('<i', b, pos)[0]; pos += 4
            if not 1 < n < 100: raise ValueError('Bad style key length')
            key = b[pos:pos+n].decode('ascii').rstrip('\0'); pos += n
            if key != expected or b[pos:pos+2] != b'\0\x07': raise ValueError('Bad named transform entry')
            pos += 2; v = struct.unpack_from('<10d', b, pos); pos += 80
            if not all(math.isfinite(x) for x in v) or abs(sum(x*x for x in v[:4])-1) > 1e-6 or abs(v[0])+abs(v[1]) > 1e-9:
                raise ValueError('Invalid native style transform')
            overrides[key] = dict(translation_m=[x/100 for x in v[4:7]], yaw_degrees=math.degrees(2*math.atan2(v[2], v[3])), scale=list(v[7:]), evidence='native named DistrictFixture entry', style_key=key)
        comp = next(c for c in tab['exports'] if c['outer'] == e['index'] and c['class'].endswith('.StaticMeshComponent'))
        raw = data[comp['serial_offset_in_uexp']:comp['serial_offset_in_uexp']+comp['serial_size']]
        fields, zero = Reader(raw, names(path)).header()
        expected_fields = {4, 124, 148, 169} | ({23} if actor == 'Stairs' else set()) | ({150} if actor in ('Stairs2_9', 'Railing2_2') else set())
        if set(fields) != expected_fields or zero or 149 in fields or raw[-13:] != b'\x02'+bytes(12):
            raise ValueError('Unsupported stair component properties; cannot assume rotation')
        locoff = len(raw)-13-(48 if 150 in fields else 24)
        loc = struct.unpack_from('<3d', raw, locoff)
        scale = struct.unpack_from('<3d', raw, locoff+24) if 150 in fields else (1., 1., 1.)
        default = dict(translation_m=[x/100 for x in loc], yaw_degrees=0.0, scale=list(scale), evidence='native StaticMeshComponent RelativeLocation/Scale; rotation field149 absent (identity default)', component_export=comp['index'])
        result[actor] = dict(default=default, overrides=overrides, map_sha256=tab['sha256'])
    return result


@lru_cache(maxsize=256)
def pillar_footprints_from(mesh_path, max_bottom=2.0):
    """XY footprints of the structural pillars (triangles starting below max_bottom m), one polygon per pillar."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    v, t = triangles(str(mesh_path)); P = v[t]; keep = P[:, :, 2].min(1) < max_bottom
    polys = [g for q in P[keep] if (g := Polygon(q[:, :2])).area > 1e-6]
    if not polys: return []
    u = unary_union([p.buffer(0.01) for p in polys]).buffer(-0.01)
    # the mesh only has caps/side faces, so the projected union can be a hollow outline: use each pillar's convex hull as its solid footprint
    return [g.convex_hull for g in getattr(u, 'geoms', [u]) if g.convex_hull.area > 0.02]


def geometry(path):
    return read_static_mesh_bounds(Path(path))


@lru_cache(maxsize=256)
def triangles(path):
    v, t = read_static_mesh_triangles(geometry(path))
    return np.asarray(v, float), np.asarray(t, int)


def transform_points(vertices, actor):
    """Full FTransform: scale -> rotation -> translation, including negative scale."""
    v = np.asarray(vertices, float) * np.asarray(actor['scale'])
    a = math.radians(actor['yaw_degrees']); c, s = math.cos(a), math.sin(a)
    return v @ np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]]) + np.asarray(actor['translation_m'])


class InteriorProfile:
    house_size = 'Medium'
    def __init__(self, style='Shirogane'):
        self.style = validate_style(style)
        if not BASE.exists(): raise ValueError('Interior assets missing: extract /InteriorStyles/ into data/house-interiors-legacy')
        # Explicit style override -> common mesh mapping. Never use another style.
        self.paths = {}
        for level, prefix in (('ground', 'GroundFloor'), ('upper', 'UpperFloor')):
            custom_floor = BASE / style / 'Medium' / (prefix+'.uexp')
            self.paths[level] = {
                'floor': custom_floor if custom_floor.exists() else BASE/'SizeCommon/Medium'/(prefix+'.uexp'),
                'room-frame': BASE/style/'Medium'/('GroundFloorFrame.uexp' if level=='ground' else 'UpperFrame.uexp'),
                'pillars': BASE/style/'Medium'/(prefix+'Pillars.uexp'),
                'walls': BASE/style/'Medium/Wall.uexp' if (BASE/style/'Medium/Wall.uexp').exists() else BASE/'SizeCommon/Medium/Wall.uexp',
                'ceiling': BASE/'SizeCommon/Medium/Ceiling.uexp',
            }
            for p in self.paths[level].values():
                if not p.exists(): raise ValueError(f'Missing {style} {level} mesh: {p}')
        self.actors = {}
        for name, entries in medium_actor_transforms().items():
            self.actors[name] = deepcopy(entries['overrides'].get(style, entries['default']))
            self.actors[name]['map_sha256'] = entries['map_sha256']
            self.actors[name]['mesh'] = str(BASE/style/('Stair/Stair1.uexp' if name.startswith('Stairs') else 'Railing/Railing1.uexp'))

    def pillar_footprints(self, level='ground'): return pillar_footprints_from(self.paths[level]['pillars'])

    def record(self, role, level='ground'):
        return deepcopy(geometry(str(self.paths[level][role])))

    def polygon(self, level='ground'):
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        v, t = triangles(str(self.paths[level]['floor']))
        return unary_union([p for tri in t if (p:=Polygon(v[tri, :2])).area>1e-8]).buffer(.002).buffer(-.002)

    def actor_world(self, name):
        a = self.actors[name]; v, t = triangles(a['mesh'])
        return transform_points(v, a), t

    def stair_footprints(self, level='ground'):
        from shapely.geometry import MultiPoint
        out=[]
        for name in ('Stairs','Stairs2_9'):
            w,_=self.actor_world(name)
            z0=LEVEL_Z[level]
            # Diagnostic projection near/above this floor, not solid collision.
            pts=w[w[:,2]>=z0-.3, :2]
            if len(pts):out.append(MultiPoint(pts).convex_hull)
        return out

    def ceiling_texture(self):
        from .rendering import native
        from .rendering.assets import find_asset
        material = BASE/self.style/'Material/MI_Ceiling.uasset'
        if not material.exists():
            raise ValueError(f'{self.style} has no named MI_Ceiling; ceiling material mapping unverified')
        mi = native.material_instance(material); base = mi['parameters'].get('Base')
        if not base or base['kind'] != 'texture': raise ValueError('Ceiling MI has no explicit Base')
        texture = find_asset(CONTENT, base['value']); image, meta = native.decode_texture(texture)
        return {'texture': np.asarray(image.convert('RGBA')), 'provenance': {'style': self.style, 'material': str(material), 'texture': str(texture), 'source_sha256': meta['source_sha256'], 'note': 'native style MI_Ceiling Base; common ceiling mesh mapping inferred'}}

    def summary(self):
        return dict(style=self.style, house_size=self.house_size, levels=dict(LEVEL_Z), renderable=True,
                    stairs=deepcopy(self.actors), native_transform_source='XIVMediumHouse: components + named style overrides',
                    limitations=['Enclosure component placement assumes native-local identity plus level offset.', 'Traditional style mesh replacement uses matching native Stair1/Railing1 asset families; not app-verified for every style.', 'No character collision/navigation proof; app import confirmation pending.'], app_verified=False)


APT_STYLES = tuple(s for s in STYLES if (BASE / s / 'Apt' / 'GroundFloorFrame.uexp').exists())


class ApartmentProfile:
    """Apartment: one 12 x 16 m ground floor (measured SizeCommon/Apartment/SimpleFrame bounds), no stairs, 150-item interior cap.
    Enclosure (frame + pillars) comes from <style>/Apt; the door is assumed at the north wall centre (0, 8) from the symmetric frame mesh gap."""
    house_size = 'Apartment'; limit = 150; levels = ('ground',)
    def __init__(self, style='Shirogane'):
        if style not in APT_STYLES: raise ValueError(f'Apartment enclosure must be one of {APT_STYLES} (no {style!r}/Apt meshes)')
        self.style = style
    def mesh(self, role):
        return BASE / self.style / 'Apt' / {'room-frame': 'GroundFloorFrame.uexp', 'pillars': 'Pillars.uexp'}[role]
    def polygon(self, level='ground'):
        from shapely.geometry import Polygon, box
        return box(-6.0, -8.0, 6.0, 8.0) if level == 'ground' else Polygon()
    def stair_footprints(self, level='ground'): return []
    def pillar_footprints(self, level='ground'): return pillar_footprints_from(self.mesh('pillars')) if level == 'ground' else []
    def actor_world(self, name): raise ValueError('Apartment has no stairs')
    def summary(self):
        return dict(style=self.style, house_size='Apartment', levels={'ground': 0.0}, renderable=True, stairs={}, limit=self.limit,
                    footprint_m=[-6.0, -8.0, 6.0, 8.0], door_assumed_xy=[0.0, 8.0],
                    limitations=['Footprint is the SimpleFrame rectangle; pillars/frame may eat into it near the walls.', 'Door position and width are inferred from the symmetric frame mesh, not app-verified.', 'Enclosure = <style>/Apt frame+pillars with identity transform; not app-verified.'])


SMALL_STYLES = tuple(s for s in STYLES if (BASE / s / 'Small' / 'GroundFloorFrame.uexp').exists() and (BASE / s / 'Stair' / 'Stair5.uexp').exists())


class SmallProfile:
    """Small: one ground floor (Shirogane/Small/GroundFloor mesh (SizeCommon copy is unparseable; footprint is common): 12x12 main room x-6..6,y-6..6 plus an east strip x6..10 whose y-1..6 part is the
    basement stairwell), basement not modelled, 300-item interior cap. Door assumed at the north wall centre (0, 6) (floor-mesh notch x-2..2).
    Basement stair = <style>/Stair/Stair5 at XIVSmallHouse 'Stairs' actor RelativeLocation (8, 0, -7) m, no rotation/scale (decoded from the umap)."""
    house_size = 'Small'; limit = 300; levels = ('ground', 'basement'); door_xy = (0.0, 6.0)
    # native exterior-fixture openings (XIVSmallHouse.umap RivieraArchedWindow*/door StaticMeshComponent RelativeLocation/Rotation): (x, y, z_base, yaw_deg)
    WINDOWS = ((-4.0, 6.0, 1.0, -180.0), (3.97, 5.97, 1.0, -180.0), (-6.0, 0.0, 1.0, -90.0), (10.0, 0.0, 1.0, 90.0))
    DOOR = (0.0, 6.0, 0.0, -180.0)
    BASEMENT_Z = -7.0
    def __init__(self, style='Minimalist'):
        if style not in SMALL_STYLES: raise ValueError(f'Small enclosure must be one of {SMALL_STYLES}')
        self.style = style
        t = dict(translation_m=[8.0, 0.0, -7.0], yaw_degrees=0.0, scale=[1.0, 1.0, 1.0], evidence='XIVSmallHouse Stairs_74/Stairs_0 StaticMeshComponent RelativeLocation')
        self.actors = {'Stairs2_9': dict(t, mesh=str(BASE / style / 'Stair' / 'Stair5.uexp')), 'StairCeiling': dict(t, mesh=str(BASE / style / 'Stair' / 'Stair5_Ceiling.uexp'))}
    def mesh(self, role):
        return BASE / self.style / 'Small' / {'room-frame': 'GroundFloorFrame.uexp', 'pillars': 'GroundFloorPillars.uexp', 'bs-room-frame': 'BasementFrame.uexp', 'bs-pillars': 'BasementPillars.uexp'}[role]
    def openings(self):
        """Native windows/door as wall openings (exterior fixtures; their STYLE can be changed in game, their position cannot).
        xy = centre on the wall face, z = [bottom, top] in metres, half_width along the wall. Windows: measured mesh ~1.0-1.4 m wide, ~2 m tall."""
        out = []
        for k, (x, y, z, yaw) in enumerate(self.WINDOWS + (self.DOOR,)):
            door = k == len(self.WINDOWS)
            along = 'x' if abs(yaw) % 180 < 1 else 'y'
            out.append(dict(kind='door' if door else 'window', xy=[x, y], along=along, z=[z, z + (4.0 if door else 2.1)], half_width=1.7 if door else 0.75))
        return out
    def polygon(self, level='ground'):
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        if level == 'basement':
            if getattr(self, '_bs_poly', None) is None: self._bs_poly = self._basement_region()
            return self._bs_poly
        if level != 'ground': return Polygon()
        v, t = triangles(str(BASE / 'Shirogane/Small/GroundFloor.uexp'))
        g = unary_union([p for tri in t if (p := Polygon(v[tri, :2])).area > 1e-8]).buffer(.002).buffer(-.002)
        return g.simplify(0.01)
    def _basement_region(self, h=1.0):
        """Walkable basement outline of THIS style (user-reported: Mist/Shirogane/Goblet/Empyreum wall off the stair underside and the area
        under the ground landing, Minimalist/DarkMinimalist/LavBed leave it open). Slice the native BasementFrame walls and the stair mesh at
        `h` above the basement floor, subtract them (+-6 cm) from the BasementSimpleFrame box and keep the component holding the room centre.
        Mesh-derived, not app-verified; the remaining stair body is still an obstacle via stair_info."""
        import numpy as np
        from shapely.geometry import LineString, MultiLineString, box, Point
        from shapely.ops import unary_union
        def slice_(v, t, z):
            P = v[t]; d = P[:, :, 2] - z; out = []
            for tri, dd in zip(P[(d.min(1) <= 0) & (d.max(1) >= 0)], d[(d.min(1) <= 0) & (d.max(1) >= 0)]):
                pts = [tri[a, :2] + dd[a] / (dd[a] - dd[b]) * (tri[b, :2] - tri[a, :2]) for a, b in ((0, 1), (1, 2), (2, 0)) if (dd[a] > 0) != (dd[b] > 0)]
                if len(pts) == 2 and np.linalg.norm(pts[0] - pts[1]) > 1e-3: out.append(LineString(pts))
            return out
        v, t = triangles(str(self.mesh('bs-room-frame'))); v = np.asarray(v); t = np.asarray(t)
        lines = slice_(v, t, float(v[:, 2].min()) + h)
        w, st = self.actor_world('Stairs2_9'); lines += slice_(np.asarray(w), np.asarray(st), self.BASEMENT_Z + h)
        outer = box(-6.0, -6.0, 10.0, 14.0)   # SizeCommon/Small/BasementSimpleFrame bounds
        comp = outer.difference(unary_union(MultiLineString(lines)).buffer(0.06))
        reg = next((g for g in getattr(comp, 'geoms', [comp]) if g.contains(Point(0.0, 4.0))), None)
        if reg is None or reg.area < 100: return outer   # slice failed: keep the old conservative box rather than an empty floor
        # +0.06 undoes the barrier buffer; +0.13 more steps over the dado rail the 1 m slice hits (Mist rail face x=-5.875 vs wall plane -6.0),
        # so wall-backed furniture against the true wall plane is not reported outside the floor
        return reg.buffer(0.19, join_style=2).intersection(outer).simplify(0.02)
    def stair_footprints(self, level='ground'):
        from shapely.geometry import MultiPoint
        w, _ = self.actor_world('Stairs2_9'); pts = w[w[:, 2] >= -0.3, :2]
        return [MultiPoint(pts).convex_hull] if len(pts) else []
    def pillar_footprints(self, level='ground'): return pillar_footprints_from(self.mesh('pillars' if level == 'ground' else 'bs-pillars')) if level in self.levels else []
    def actor_world(self, name):
        a = self.actors[name]; v, t = triangles(a['mesh']); return transform_points(v, a), t
    def summary(self):
        return dict(style=self.style, house_size='Small', levels={'ground': 0.0}, renderable=True, stairs={k: {kk: vv for kk, vv in v.items()} for k, v in self.actors.items()}, limit=self.limit,
                    door_assumed_xy=list(self.door_xy), limitations=['Basement outline sliced per style from the native BasementFrame + stair walls at 1 m (not app-verified).', 'Door position inferred from the floor-mesh notch, not app-verified.', 'Stair actor transform decoded from the Small umap; style overrides (if any) not decoded.'])


def list_interiors():
    return [dict(style=s, house_size='Medium', renderable=all((BASE/s/'Medium'/f).exists() for f in ('GroundFloorFrame.uexp','UpperFrame.uexp')) and (BASE/s/'Stair/Stair1.uexp').exists(), levels=['ground','upper'], app_verified=False) for s in STYLES]
