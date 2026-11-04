"""Every rendered room must include the native main entrance door (user-reported MCP gap).

Before the fix, run_pipeline drew room-frame/ceiling/walls/pillars but never the door fixture
the maps reference (Small RivieraWoodenDoor, Medium HinganDoor Mokuzo, Large RivieraWoodenDoor,
Apartment Mist ChamberDoor), so the entrance read as an empty wall in every house size.
"""
import json, tempfile, unittest
from pathlib import Path
import numpy as np

from ffxiv_furniture.rendering.pipeline import run_pipeline

ROOT = Path(__file__).resolve().parents[1]
SEED = json.loads((ROOT / 'data/seeds/apartment-seed.json').read_bytes())
SIZES = ('Small', 'Medium', 'Large', 'Apartment')


def layout_for(size):
    lay = json.loads(json.dumps(SEED))
    lay['houseSize'] = size
    lay['interiorFurniture'] = []
    return lay


class MainEntranceRenderTests(unittest.TestCase):
    def _run(self, size, selected_door=None):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f'{size}.json'
            layout = layout_for(size)
            if selected_door:
                layout['exteriorFixture'] = [dict(type='Door', name=selected_door)]
            src.write_text(json.dumps(layout), encoding='utf-8')
            return run_pipeline(src, Path(tmp) / f'run-{size}', db_path=ROOT / 'data/furniture-test.sqlite3',
                                room_context=True, size=(96, 64), mirror_view=False,
                                cameras=[dict(name='entry', position=[0, 4, 2.2], target=[0, 8, 1.2], fov=80)])

    def test_cutaway_plan_views_keep_main_door(self):
        """User-reported: overview/top cutaways dropped the door with the walls, so plan views hid the entrance
        and the arrival area was misjudged. The door is an entrance marker, not wall: keep it in cutaways."""
        cams = [dict(name='overview', position=[12, -12, 16], target=[1, 0, 0], fov=60, cutaway=True),
                dict(name='top', position=[0.5, 0, 38], target=[0, 0, 0], fov=34, cutaway=True)]
        for size, door in (('Small', None), ('Small', 'Riviera Wooden Door'), ('Apartment', None)):
            with self.subTest(size=size, door=door), tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / f'{size}.json'; layout = layout_for(size)
                if door: layout['exteriorFixture'] = [dict(type='Door', name=door)]
                src.write_text(json.dumps(layout), encoding='utf-8')
                m = run_pipeline(src, Path(tmp) / 'run', db_path=ROOT / 'data/furniture-test.sqlite3', room_context=True,
                                 size=(192, 128), mirror_view=False, cameras=cams)
                did = str(m['objects']['main-door']['render_id'])
                for view in m['views']:
                    self.assertGreater(view['visible_object_pixels'].get(did, 0), 0, f"{view.get('camera', view)}: cutaway must still show the entrance door")

    def test_small_stairwell_ceiling_is_cut_in_plan_views(self):
        # user-visible: the Small stairwell ceiling drew as a grey slab over the landing in top views
        from collections import defaultdict
        from unittest.mock import patch
        from ffxiv_furniture.rendering import pipeline
        roles = defaultdict(set); original = pipeline.render
        def audited(meshes, *a, **k):
            for mesh in meshes: roles[mesh['id']].add(mesh['role'])
            return original(meshes, *a, **k)
        with patch.object(pipeline, 'render', audited):
            m = self._run('Small')
        ceil = [k for k, v in m['objects'].items() if k.isdigit() and v.get('instance_id') == 'stairceiling']
        self.assertEqual(len(ceil), 1)
        self.assertEqual(roles[int(ceil[0])], {'enclosure'})
        stair = [k for k, v in m['objects'].items() if k.isdigit() and v.get('instance_id') == 'stair-down']
        self.assertEqual(roles[int(stair[0])], {'stair'})

    def test_every_house_size_renders_main_door(self):
        for size in SIZES:
            with self.subTest(size=size):
                m = self._run(size)
                self.assertIn('main-door', m['objects'], 'main entrance door must be part of the room context')
                door = m['objects']['main-door']
                self.assertFalse(door['app_verified'])
                self.assertIn('MakePlace/Content/HouseAssets/MainDoor/', str(door['mesh_source']).replace('\\', '/'),
                              'door geometry must come from a converted native MainDoor mesh, never a synthetic box')
                self.assertTrue(str(door['mesh_source']).lower().endswith('.uexp'))
                for v in m['views']:
                    self.assertFalse(v.get('cache_hit'))
                hits = [w for w in m['warnings'] if 'main entrance door' in w.lower()]
                self.assertTrue(hits, 'door placement assumption must be disclosed as a warning')

    def test_door_sits_at_documented_entrance_and_above_floor(self):
        NORTH_WALL_Y = {'Small': 6.0, 'Medium': 8.0, 'Large': 12.0, 'Apartment': 8.0}  # measured wall mesh planes
        for size in SIZES:
            with self.subTest(size=size):
                m = self._run(size)
                world = np.asarray(m['objects']['main-door']['world_bounds_m'], float)
                (x0, y0, z0), (x1, y1, z1) = world
                wall = NORTH_WALL_Y[size]
                self.assertGreater(y0, wall - 1.5, f'{size}: door must stand against the north wall (y={wall})')
                self.assertLessEqual(y1, wall + 0.05, f'{size}: door must not poke through the north wall')
                self.assertLess(abs((x0 + x1) / 2), 0.25, f'{size}: door must sit on the documented centre entrance')
                self.assertGreaterEqual(z0, -0.05, f'{size}: door must not sink below the floor')
                self.assertGreater(z1, 1.8, f'{size}: a house entrance is at least ~2 m tall')

    def test_structural_ids_separate_door_from_railings(self):
        from collections import defaultdict
        from unittest.mock import patch
        from ffxiv_furniture.rendering import pipeline
        for size in SIZES:
            with self.subTest(size=size):
                roles = defaultdict(set)
                original_render = pipeline.render
                def audited_render(meshes, *args, **kwargs):
                    for mesh in meshes:
                        roles[mesh['id']].add(mesh['role'])
                    return original_render(meshes, *args, **kwargs)
                with patch.object(pipeline, 'render', audited_render):
                    manifest = self._run(size)
                collisions = {key: sorted(value) for key, value in roles.items() if len(value) > 1}
                self.assertEqual(collisions, {}, 'different structural objects must not share an ID')
                door = manifest['objects']['main-door']
                self.assertIn('render_id', door)
                door_id = door['render_id']
                self.assertEqual(manifest['objects'][str(door_id)], door)
                self.assertEqual(roles[door_id], {'door'})
                self.assertGreater(manifest['views'][0]['visible_object_pixels'].get(str(door_id), 0), 0,
                                   'door pixels must resolve to door metadata, not a railing')
                for render_id in roles:
                    self.assertIn(str(render_id), manifest['objects'])

    def test_small_selected_door_has_no_duplicate_fallback(self):
        manifest = self._run('Small', 'Riviera Wooden Door')
        doors = [(k, v) for k, v in manifest['objects'].items()
                 if k.isdigit() and v['instance_id'] in ('main-door', 'native-door')]
        self.assertEqual(len(doors), 1, 'selected and fallback doors must not both render')
        key, door = doors[0]
        self.assertEqual(door['name'], 'Riviera Wooden Door')
        self.assertEqual(manifest['objects']['main-door'], door)
        self.assertEqual(str(door['render_id']), key)
        self.assertGreater(manifest['views'][0]['visible_object_pixels'].get(key, 0), 0)

    def test_small_missing_selected_door_uses_fallback(self):
        manifest = self._run('Small', 'Missing Door Asset For Regression')
        doors = [(k, v) for k, v in manifest['objects'].items()
                 if k.isdigit() and v['instance_id'] in ('main-door', 'native-door')]
        self.assertEqual(len(doors), 1)
        key, door = doors[0]
        self.assertEqual(door['instance_id'], 'main-door')
        self.assertTrue(any('Native Door not drawn' in w for w in manifest['warnings']))
        self.assertGreater(manifest['views'][0]['visible_object_pixels'].get(key, 0), 0)

    def test_small_without_selected_door_uses_fallback(self):
        from unittest.mock import patch
        layout = layout_for('Small')
        layout['exteriorFixture'] = []
        with patch(__name__ + '.layout_for', return_value=layout):
            manifest = self._run('Small')
        doors = [v for k, v in manifest['objects'].items()
                 if k.isdigit() and v['instance_id'] in ('main-door', 'native-door')]
        self.assertEqual(len(doors), 1)
        self.assertEqual(doors[0]['instance_id'], 'main-door')

    def test_material_diagnostics_include_structure_and_fixtures(self):
        manifest = self._run('Small', 'Riviera Wooden Door')
        self.assertIn('native_material_diagnostics', manifest)
        diagnostics = manifest['native_material_diagnostics']
        self.assertIn('native decode only', diagnostics['scope'])
        for kind in ('furniture', 'structure', 'fixtures'):
            group = diagnostics[kind]
            self.assertEqual(group['decoded_entries'], len(group['coverage']))
            self.assertEqual(group['material_slots'], sum(a['material_slots'] for a in group['coverage']))
            self.assertEqual(group['textured_slots'], sum(a['textured_slots'] for a in group['coverage']))
            self.assertEqual(group['untextured_slots'], group['material_slots'] - group['textured_slots'])
            for row in group['coverage']:
                self.assertIn('source', row)
                self.assertIn('source_sha256', row)
                self.assertIn('notes', row)
                self.assertTrue(all('warning' in m for m in row['materials']))
        fixtures = diagnostics['fixtures']['coverage']
        self.assertTrue(any('MainDoor' in Path(a['source']).parts for a in fixtures))
        self.assertTrue(any('CeilingLight' in Path(a['source']).parts for a in fixtures))
        self.assertGreater(diagnostics['structure']['decoded_entries'], 0)
        self.assertEqual(manifest['asset_coverage'], diagnostics['furniture']['coverage'])

    def test_no_room_context_keeps_scene_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'apt.json'
            lay = layout_for('Apartment')
            item = dict(SEED['interiorFurniture'][0]) if SEED.get('interiorFurniture') else None
            if item is None: self.skipTest('seed has no furniture sample')
            lay['interiorFurniture'] = [item]
            src.write_text(json.dumps(lay), encoding='utf-8')
            m = run_pipeline(src, Path(tmp) / 'run-nc', db_path=ROOT / 'data/furniture-test.sqlite3', size=(96, 64),
                             mirror_view=False, cameras=[dict(name='top', position=[0, 0, 40], target=[0, 0, 0], fov=32)])
            self.assertNotIn('main-door', m['objects'])


if __name__ == '__main__':
    unittest.main()
