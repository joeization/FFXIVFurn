"""Exterior-scoped decoration session. The seed's entire indoor payload stays untouched."""

from copy import deepcopy
from pathlib import Path
import json, math, os, hashlib
from shapely.geometry import Polygon
from .core import Catalog, Session, Room, DecoError, DB_PATH, quat_to_yaw
from ..exteriors import (
    ExteriorProfile,
    KINDS,
    FIXTURE_TYPES,
    TYPE_FOR_CATEGORY,
    category_for_type,
    fixture_row,
    fixture_folder,
    compatible,
)
from ..housing import HOUSING_LIMITS


class ExteriorCatalog(Catalog):
    def __init__(self, house_size="Small", path=None):
        super().__init__(path, scope="exterior")
        self.house_size = house_size

    def material(self, item_id, name, ftype):
        cat = category_for_type(ftype)
        if cat not in FIXTURE_TYPES.values():
            raise DecoError("BAD_INPUT", "Unsupported exterior fixture type")
        try:
            row = fixture_row(self.db, self.house_size, cat, item_id=item_id, name=name)
        except ValueError as error:
            raise DecoError("UNKNOWN_ITEM", str(error)) from error
        if (
            self.max_patch is not None
            and row.get("patch") is not None
            and float(row["patch"]) > self.max_patch
        ):
            raise DecoError("ITEM_TOO_NEW", row["name"] + " exceeds max_patch")
        folder = fixture_folder(row)
        required = [
            folder / (folder.name + s + ".uexp")
            for s in (("", "_b", "_c", "_d") if cat == "Fence" else ("",))
        ]
        if not all(p.is_file() for p in required):
            raise DecoError(
                "GEOMETRY_UNAVAILABLE", "Incomplete native exterior mesh family: " + row["name"]
            )
        return row

    def search_materials(self, query, kind, limit=20):
        cat = KINDS.get(kind)
        if cat is None:
            raise DecoError(
                "BAD_INPUT",
                "kind must be wall/roof/fence/door/window/roof_decor/wall_decor/placard",
            )
        result = []
        for raw in self.db.execute(
            "SELECT * FROM house_materials WHERE category=? ORDER BY name", (cat,)
        ):
            row = dict(raw)
            if not compatible(row["name"], self.house_size, cat):
                continue
            if (
                self.max_patch is not None
                and row.get("patch")
                and float(row["patch"]) > self.max_patch
            ):
                continue
            text = (row["name"] + " " + str(row.get("visual_description") or "")).lower()
            if not all(w in text for w in query.lower().split()):
                continue
            folder = fixture_folder(row)
            required = [
                folder / (folder.name + s + ".uexp")
                for s in (("", "_b", "_c", "_d") if cat == "Fence" else ("",))
            ]
            result.append(
                dict(
                    item_id=row["item_id"],
                    name=row["name"],
                    category=cat,
                    renderable=all(p.is_file() for p in required),
                    patch=row["patch"],
                )
            )
        return result[: max(1, min(int(limit), 60))]


class ExteriorRoom:
    UPPER_Z = 7.0
    style = "Exterior"
    levels = ("ground",)
    level_z = {"ground": 0.0}

    def __init__(self, house_size="Small", fixtures=(), db_path=None):
        self.house_size = house_size
        self.profile = ExteriorProfile(house_size, fixtures, db_path=db_path)
        self.limit = HOUSING_LIMITS[house_size]["exterior"]
        self.floor = self.profile.polygon()
        self.upper = Polygon()
        self.basement = Polygon()
        self.polys = {"ground": self.floor}
        self.openings = []
        self.stairs = []
        self.pillars_by_level = {"ground": []}
        self.walls = Room._walls(self.floor)
        self.walls_by_level = {"ground": self.walls}
        self.door_xy = (0.0, self.floor.bounds[3])

    def level_of(self, z):
        return "ground"

    def floor_at(self, z):
        return self.floor

    def boundary_distance(self, x, y, z=0):
        from shapely.geometry import Point

        return self.floor.boundary.distance(Point(x, y))

    def stair_info(self):
        return dict(up=dict(solid=None, foot_access=None, arrival_access=None))

    def stair_summary(self):
        return dict(note="Exterior has no interior staircase context.")

    def stair_clearance(self):
        return {}


class ExteriorSession(Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.cat.scope != "exterior":
            raise DecoError("SCOPE_MISMATCH", "ExteriorSession needs an exterior catalog")

    def _save(self):
        d = dict(
            name=self.name,
            scope="exterior",
            house_size=self.room.house_size,
            revision=self.revision,
            state=self._state(),
            undo=self.undo_stack,
            redo=self.redo_stack,
            snapshots=self.snapshots,
            seed=self.seed,
            catalog=self.cat.sha(),
            max_patch=self.max_patch,
        )
        tmp = self.dir / "state.json.tmp"
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, self.dir / "state.json")

    def _set_state(self, st):
        room = ExteriorRoom(
            self.room.house_size, self._fixture_list(st.get("fixtures", {})), db_path=self.cat.path
        )
        self.instances = deepcopy(st["instances"])
        self.next_id = st["next_id"]
        self.fixtures = deepcopy(st.get("fixtures", {}))
        self.room = room
        self.instances_view = None

    def _import(self, layout):
        scale = layout.get("exteriorScale")
        if (
            not isinstance(scale, (float, int))
            or isinstance(scale, bool)
            or not math.isfinite(scale)
            or scale <= 0
        ):
            raise DecoError("BAD_INPUT", "Invalid exteriorScale")
        self.seed = {k: deepcopy(v) for k, v in layout.items() if k != "exteriorFurniture"}
        for f in layout.get("exteriorFurniture", []):
            t = f["transform"]
            q = t["rotation"]
            if (
                f.get("attachments")
                or t.get("scale", [1, 1, 1]) != [1, 1, 1]
                or len(q) != 4
                or abs(q[0]) + abs(q[1]) > 1e-6
            ):
                raise DecoError(
                    "BAD_INPUT",
                    "Imported yard items require yaw-only unit transforms and no attachments",
                )
            it = self.cat.item(f["itemId"])
            if it["name"] != f["name"]:
                raise DecoError("BAD_INPUT", "Conflicting exterior itemId/name")
            if self.cat._too_new(it["id"]):
                raise DecoError("ITEM_TOO_NEW", it["name"])
            iid = f"i{self.next_id}"
            self.next_id += 1
            self.instances[iid] = dict(
                id=iid,
                item_id=it["id"],
                name=it["name"],
                pivot=[v / scale for v in t["location"]],
                yaw=quat_to_yaw(q),
                source_item=deepcopy(f),
            )
            color = f.get("properties", {}).get("color")
            if color:
                self.instances[iid]["color"] = color[:6]
        self.room = ExteriorRoom(self.room.house_size, self.seed.get("exteriorFixture", []))
        if len(self.instances) > self.room.limit:
            raise DecoError("BUDGET_EXCEEDED", "Exterior furnishing cap exceeded")

    def _fixture_list(self, selections):
        rows = deepcopy((self.seed or {}).get("exteriorFixture", []))
        for key, row in selections.items():
            cat = category_for_type(key)
            matches = [r for r in rows if category_for_type(r.get("type")) == cat]
            if len(matches) > 1:
                raise DecoError("BAD_INPUT", "Duplicate exterior fixture slot")
            slot = matches[0] if matches else dict(type=TYPE_FOR_CATEGORY[cat], level="", color="")
            slot.update(name=row["name"], itemId=row["item_id"] or 0)
            if not matches:
                rows.append(slot)
        return rows

    def _apply_one(self, st, op):
        if op.get("op") == "interior":
            raise DecoError("BAD_INPUT", "Exterior mode has no interior style switch")
        if op.get("op") != "fixture":
            return super()._apply_one(st, op)
        row = self.cat.material(op.get("item_id"), op.get("name"), op.get("type"))
        st.setdefault("fixtures", {})[TYPE_FOR_CATEGORY[row["category"]]] = dict(
            name=row["name"], item_id=row["item_id"]
        )
        try:
            ExteriorProfile(self.room.house_size, self._fixture_list(st["fixtures"])).scene()
        except ValueError as error:
            raise DecoError("GEOMETRY_UNAVAILABLE", str(error)) from error
        return set(), set()

    def validate(self, inst, issues, op_index=None):
        if not all(math.isfinite(v) for v in inst["pivot"] + [inst["yaw"]]):
            issues.append(
                dict(
                    code="BAD_INPUT",
                    message="Nonfinite exterior transform",
                    instance_id=inst["id"],
                    op_index=op_index,
                )
            )
            return
        self.cat.item(inst["item_id"])
        if self.footprint(inst).difference(self.room.floor.buffer(0.02)).area > 0.01:
            issues.append(
                dict(
                    code="OUTSIDE_FLOOR",
                    message="Outside native yard region or inside projected house footprint; advisory, not game collision.",
                    instance_id=inst["id"],
                    op_index=op_index,
                )
            )

    def _budget(self, instances, issues):
        if len(instances) > self.room.limit:
            issues.append(
                dict(
                    code="BUDGET_EXCEEDED",
                    message=f"{len(instances)} > {self.room.limit} exterior items",
                    instance_id=None,
                    op_index=None,
                )
            )

    def restore(self, sid):
        if sid not in self.snapshots:
            raise DecoError("UNKNOWN_SNAPSHOT", str(sid))
        st = deepcopy(self.snapshots[sid]["state"])
        self.undo_stack.append(
            dict(revision=self.revision, state=self._state(), label="restore " + sid)
        )
        self.redo_stack = []
        self._set_state(st)
        self.revision += 1
        self._save()
        return self.status()

    def status(self):
        result = super().status()
        result.update(scope="exterior")
        result["capabilities"].update(
            switch_interior=False, exterior_fixtures=list(KINDS), native_transforms_decoded=True
        )
        return result

    def layout_dict(self):
        if self.seed is None:
            raise DecoError("IO_ERROR", "Session has no seed")
        d = deepcopy(self.seed)
        d["exteriorFixture"] = self._fixture_list(self.fixtures)
        scale = d.get("exteriorScale")
        if (
            not isinstance(scale, (int, float))
            or isinstance(scale, bool)
            or not math.isfinite(scale)
            or scale <= 0
        ):
            raise DecoError("BAD_INPUT", "Invalid exteriorScale")
        items = []
        for inst in self.instances.values():
            item = deepcopy(inst.get("source_item", {}))
            a = math.radians(inst["yaw"])
            item.update(
                itemId=inst["item_id"],
                name=inst["name"],
                transform=dict(
                    location=[round(v * scale, 6) for v in inst["pivot"]],
                    rotation=[0, 0, math.sin(a / 2), math.cos(a / 2)],
                    scale=[1, 1, 1],
                ),
                attachments=[],
            )
            item.setdefault("properties", {}).pop("color", None)
            if inst.get("color"):
                item["properties"]["color"] = inst["color"] + "FF"
            items.append(item)
        d["exteriorFurniture"] = items
        return d

    def export(self, name):
        safe = "".join(c for c in name if c.isalnum() or c in "-_") or "yard"
        p = self.dir / f"{safe}-r{self.revision}.json"
        data = self.write_layout(p)
        back = json.loads(p.read_bytes())
        assert len(back["exteriorFurniture"]) == len(self.instances)
        for key, value in self.seed.items():
            if key not in ("exteriorFurniture", "exteriorFixture"):
                assert back[key] == value, key
        mapping = self.dir / f"{safe}-r{self.revision}.map.json"
        mapping.write_text(
            json.dumps(
                [
                    dict(index=i, instance_id=k, scope="exterior")
                    for i, k in enumerate(self.instances)
                ],
                indent=1,
            ),
            encoding="utf-8",
        )
        return dict(
            ok=True,
            revision=self.revision,
            scope="exterior",
            layout=dict(path=str(p), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)),
            instance_map=str(mapping),
            item_count=len(self.instances),
            encoding="UTF-16LE-BOM",
            note="Native yard preview/export; app import not verified.",
        )
