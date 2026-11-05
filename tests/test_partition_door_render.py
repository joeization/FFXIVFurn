"""Partition doors are native frame + socket-attached movable leaf, not empty arches."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from ffxiv_furniture.config import load_sources
from ffxiv_furniture.geometry import read_static_mesh_bounds
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
from ffxiv_furniture.rendering.assets import Assets
from ffxiv_furniture.rendering.resources import DecodedAssetCache


def frame_path(style):
    rel=Path('GameAssets/Fixture')/style/(style+'.uexp')
    return next((Path(root)/rel for root in load_sources()['furniture_roots'] if (Path(root)/rel).is_file()),None)


class PartitionDoorComponentTests(unittest.TestCase):
    def test_minimalist_partition_includes_native_hinged_leaf(self):
        path=frame_path('MinimalistPartitionDoor')
        if path is None:
            self.skipTest('proprietary native partition mesh unavailable')
        leaf_path=path.with_name(path.stem+'_Door.uexp')
        self.assertTrue(leaf_path.is_file(),'a missing movable leaf is not a passing frame-only render')
        record=read_static_mesh_bounds(path);record['item_id']=48135
        frame_vertices,frame_triangles=read_static_mesh_triangles(record)
        leaf_record=read_static_mesh_bounds(leaf_path)
        leaf_vertices,leaf_triangles=read_static_mesh_triangles(leaf_record)
        with tempfile.TemporaryDirectory() as tmp:
            loader=Assets([record],Path(tmp),mi_tint=True)
            mesh=loader.load(48135)
        self.assertTrue('components' in mesh,'movable door mesh is currently omitted')
        self.assertEqual(len(mesh['components']),1)
        component=mesh['components'][0]
        self.assertEqual(component['socket'],'DoorHinge')
        self.assertTrue(component['source'].endswith('MinimalistPartitionDoor_Door.uexp'))
        self.assertEqual(component['source_sha256'],leaf_record['source_sha256'])
        self.assertEqual(component['translation_m'],[-0.67,0.0,0.0])
        self.assertEqual(component['yaw_degrees'],-90.0)
        self.assertFalse(component['app_verified'])
        self.assertEqual(len(mesh['vertices']),len(frame_vertices)+len(leaf_vertices))
        self.assertEqual(len(mesh['triangles']),len(frame_triangles)+len(leaf_triangles))
        np.testing.assert_array_equal(mesh['vertices'][:len(frame_vertices)],frame_vertices)
        # Independently apply the decoded native -90 degree hinge pose.
        expected=np.asarray(leaf_vertices)@np.array([[0,-1,0],[1,0,0],[0,0,1]])+[-0.67,0,0]
        np.testing.assert_allclose(mesh['vertices'][len(frame_vertices):],expected,atol=1e-8)
        self.assertEqual(len(mesh['uv']),len(mesh['vertices']))
        self.assertEqual(loader.coverage[0]['material_slots'],6)
        self.assertEqual(loader.coverage[0]['textured_slots'],6)
        self.assertEqual(loader.coverage[0]['components'],mesh['components'])

    def test_log_partition_has_both_native_hinged_leaves(self):
        path=frame_path('LogPartitionDoor')
        if path is None:
            self.skipTest('proprietary native partition mesh unavailable')
        record=read_static_mesh_bounds(path);record['item_id']=1
        leaf_record=read_static_mesh_bounds(path.with_name(path.stem+'_Door.uexp'))
        with tempfile.TemporaryDirectory() as tmp:
            mesh=Assets([record],Path(tmp),mi_tint=True).load(1)
        self.assertEqual([c['socket'] for c in mesh['components']],['DoorHinge','DoorHinge2'])
        self.assertEqual([c['translation_m'] for c in mesh['components']],[[-0.9,0,0],[0.9,0,0]])
        self.assertEqual([c['yaw_degrees'] for c in mesh['components']],[-90,90])
        self.assertEqual(len(mesh['vertices']),record['vertex_count']+2*leaf_record['vertex_count'])

    def test_all_available_partition_families_have_valid_composite_geometry(self):
        paths=set()
        for root in load_sources()['furniture_roots']:
            paths.update((Path(root)/'GameAssets/Fixture').glob('*PartitionDoor/*PartitionDoor.uexp'))
        if not paths:
            self.skipTest('proprietary native partition meshes unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            for path in sorted(paths):
                with self.subTest(style=path.stem):
                    record=read_static_mesh_bounds(path);record['item_id']=1
                    loader=Assets([record],Path(tmp),mi_tint=True);mesh=loader.load(1)
                    self.assertGreater(len(mesh['vertices']),record['vertex_count'])
                    self.assertEqual(len(mesh['vertices']),len(mesh['uv']))
                    self.assertGreaterEqual(int(mesh['triangles'].min()),0)
                    self.assertLess(int(mesh['triangles'].max()),len(mesh['vertices']))
                    self.assertEqual(sum(g['triangle_count'] for g in mesh['groups']),len(mesh['triangles']))
                    self.assertTrue(all(-1<=g['material_index']<len(mesh['materials']) for g in mesh['groups']))
                    self.assertEqual(loader.coverage[0]['material_slots'],len(mesh['materials']))
                    self.assertTrue(all(c['pose']=='native-socket' for c in mesh['components']))

    def test_cached_composite_preserves_leaf_dependencies_and_provenance(self):
        path=frame_path('MinimalistPartitionDoor')
        if path is None:
            self.skipTest('proprietary native partition mesh unavailable')
        record=read_static_mesh_bounds(path);record['item_id']=48135
        cache=DecodedAssetCache()
        with tempfile.TemporaryDirectory() as tmp:
            cold=Assets([record],Path(tmp),mi_tint=True,resource_cache=cache)
            first=cold.load(48135)
            warm=Assets([record],Path(tmp),mi_tint=True,resource_cache=cache)
            second=warm.load(48135)
        self.assertIs(first,second)
        self.assertEqual(warm.coverage,cold.coverage)
        self.assertEqual(warm.dependencies,cold.dependencies)
        for ext in ('.uasset','.uexp','.ubulk'):
            leaf=path.with_name(path.stem+'_Door'+ext)
            self.assertIn(str(leaf.resolve()),warm.dependencies)


if __name__=='__main__':
    unittest.main()
