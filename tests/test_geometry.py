"""Native mesh bounds, triangles and synthetic model-local support surfaces."""

import importlib.util
import math
import numpy as np
import struct
import tempfile
import unittest
from ffxiv_furniture.geometry import read_static_mesh_bounds
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
from pathlib import Path
from tests.support import ROOT

def load_script(name):
    """Load one repository script without repeating importlib boilerplate."""
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ground_floor = load_script('arrange_ground_floor')


def native_mesh_buffer():
    # Synthetic cross-validated native-buffer fixture, not game measurements.
    points=[(0.,0.,0.),(200.,0.,0.),(0.,100.,100.)]
    data=b'\x01\x00'+struct.pack('<4I',12,3,12,3)+b''.join(struct.pack('<3f',*p) for p in points)
    data+=b'\x01\x00'+struct.pack('<6I',1,3,0,0,8,3)+bytes(24)
    data+=struct.pack('<2I',4,3)+bytes(12)
    data+=b'\x01\x00'+struct.pack('<2I',0,0)
    data+=struct.pack('<3I',0,1,6)+struct.pack('<3H',0,1,2)
    center=(100.,50.,50.);extent=(100.,50.,50.)
    data+=struct.pack('<7d',*center,*extent,math.sqrt(15000))
    data+=struct.pack('<I',1)+b''.join(struct.pack('<If',1,1. if i==0 else 0.) for i in range(8))
    data+=bytes.fromhex('c1832a9e')
    return data


class NativeMeshGeometryTests(unittest.TestCase):
    def save(self,folder,data):
        p=Path(folder)/'mesh.uexp';p.write_bytes(data);p.with_suffix('.uasset').write_bytes(b'StaticMesh\0');return p

    def test_buffers_bounds_and_triangles_agree(self):
        with tempfile.TemporaryDirectory() as temp:
            p=self.save(temp,native_mesh_buffer());r=read_static_mesh_bounds(p)
            self.assertEqual([r[k] for k in ('length_m','width_m','height_m')],[2,1,1])
            self.assertEqual(r['local_min_m'],[0,0,0])
            self.assertEqual(r['local_max_m'],[2,1,1])
            vertices,triangles=read_static_mesh_triangles(r)
            self.assertEqual(vertices,[(0,0,0),(2,0,0),(0,1,1)])
            self.assertEqual(triangles,[(0,1,2)])

    def test_signature_alone_is_insufficient(self):
        with tempfile.TemporaryDirectory() as temp:
            b=bytearray(native_mesh_buffer());struct.pack_into('<I',b,2+16+3*12+2+20,99)
            with self.assertRaises(ValueError):read_static_mesh_bounds(self.save(temp,b))
            b=bytearray(native_mesh_buffer());struct.pack_into('<f',b,18,math.nan)
            with self.assertRaises(ValueError):read_static_mesh_bounds(self.save(temp,b))

    def test_independent_bounds_and_source_hash_required(self):
        with tempfile.TemporaryDirectory() as temp:
            p=self.save(temp,native_mesh_buffer());r=read_static_mesh_bounds(p)
            b=bytearray(p.read_bytes());struct.pack_into('<d',b,r['bounds_offset'],999)
            p.write_bytes(b)
            with self.assertRaises(ValueError):read_static_mesh_bounds(p)
            with self.assertRaisesRegex(ValueError,'changed'):read_static_mesh_triangles(r)

    def test_triangle_support_not_bounding_box_top(self):
        vertices=[(0,0,.9),(2,0,.9),(0,2,.9),(0,0,1.02)]
        triangles=[(0,1,2)]
        self.assertAlmostEqual(ground_floor.projected_surface(vertices,triangles,.5,.5),.9)
        with self.assertRaises(ValueError):ground_floor.projected_surface(vertices,triangles,3,3)

    def test_pivot_relative_rotated_bounds(self):
        g={'min_x':-1,'max_x':3,'min_y':-2,'max_y':2,'min_z':.5,'max_z':1.5}
        b=ground_floor.rotated_bounds(g,[10,20,-.5],90)
        self.assertAlmostEqual(b['min'][0],8)
        self.assertAlmostEqual(b['max'][0],12)
        self.assertAlmostEqual(b['min'][1],19)
        self.assertAlmostEqual(b['max'][1],23)
        self.assertEqual(b['min'][2],0)


def support_board(z, x=0.0, size=1.0, downward=False):
    vertices = [(x, 0, z), (x + size, 0, z), (x + size, size, z), (x, size, z)]
    faces = [(0, 1, 2), (0, 2, 3)]
    return vertices, [tuple(reversed(f)) for f in faces] if downward else faces


def support_mesh(*boards):
    vertices, faces = [(0, 0, 0)], []
    for points, triangles in boards:
        offset = len(vertices)
        vertices.extend(points)
        faces.extend(tuple(i + offset for i in face) for face in triangles)
    return np.array(vertices), np.array(faces)


class SupportSurfacesTests(unittest.TestCase):
    def test_height_area_and_clearance_filters(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = support_mesh(support_board(0.1), support_board(0.3), support_board(0.4, downward=True),
                               support_board(0.8, size=0.1), support_board(1.2))
        surfaces = measure_support_surfaces(vertices, faces)
        np.testing.assert_allclose([s['z_local'] for s in surfaces], [1.2])

    def test_nearby_heights_merge_but_not_transitively(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = support_mesh(support_board(0.3), support_board(0.32, x=2), support_board(0.35, x=4), support_board(1.0, x=6))
        surfaces = measure_support_surfaces(vertices, faces)
        np.testing.assert_allclose([s['z_local'] for s in surfaces], [0.31, 0.35, 1.0])
        self.assertAlmostEqual(surfaces[0]['area_m2'], 2.0)

    def test_xy_disjoint_geometry_does_not_reduce_clearance(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = support_mesh(support_board(0.3), support_board(0.35, x=2, downward=True), support_board(1.0, x=2))
        surfaces = measure_support_surfaces(vertices, faces)
        self.assertAlmostEqual(surfaces[0]['clearance_above_m'], 0.7)

    def test_vertical_edge_contacts_do_not_block_boards(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = support_mesh(support_board(0.3), support_board(1.0))
        offset = len(vertices)
        vertices = np.vstack([vertices, [(0, 0, 0.3), (1, 0, 0.3), (1, 0, 1.0)]])
        faces = np.vstack([faces, [(offset, offset + 1, offset + 2)]])
        self.assertEqual(len(measure_support_surfaces(vertices, faces)), 2)

    def test_duplicate_triangles_do_not_inflate_area(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = support_mesh(support_board(0.3, size=0.1), support_board(0.3, size=0.1))
        self.assertEqual(measure_support_surfaces(vertices, faces), [])

    def test_side_panel_rising_from_board_is_not_an_overhead_plane(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = support_mesh(support_board(0.3), support_board(1.0))
        offset = len(vertices)
        vertices = np.vstack([vertices, [(0, 0, 0.3), (1, 0, 0.3), (1, 0.01, 1.0)]])
        faces = np.vstack([faces, [(offset, offset + 1, offset + 2)]])
        surfaces = measure_support_surfaces(vertices, faces)
        self.assertEqual(len(surfaces), 2)
        self.assertAlmostEqual(surfaces[0]['clearance_above_m'], 0.7)

    def test_inward_wound_extracted_box_has_upward_outward_top(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices = np.array([(0,0,0), (1,0,0), (1,1,0), (0,1,0),
                             (0,0,0.3), (1,0,0.3), (1,1,0.3), (0,1,0.3)])
        outward = np.array([(0,2,1),(0,3,2),(4,5,6),(4,6,7),
                            (0,1,5),(0,5,4),(1,2,6),(1,6,5),
                            (2,3,7),(2,7,6),(3,0,4),(3,4,7)])
        surfaces = measure_support_surfaces(vertices, outward[:, ::-1])
        self.assertEqual(len(surfaces), 1)
        self.assertAlmostEqual(surfaces[0]['z_local'], 0.3)
        self.assertEqual(surfaces[0]['is_top'], 1)

    def test_stacked_boards_cluster_and_clearance(self):
        from ffxiv_furniture.design.surfaces import measure_support_surfaces
        vertices, faces = support_mesh(support_board(0.3), support_board(0.8, downward=True), support_board(0.85), support_board(1.4))
        surfaces = measure_support_surfaces(vertices, faces)
        np.testing.assert_allclose([s['z_local'] for s in surfaces], [0.3, 0.85, 1.4])
        np.testing.assert_allclose([s['clearance_above_m'] for s in surfaces], [0.5, 0.55, 9.9])
        self.assertEqual([s['is_top'] for s in surfaces], [0, 0, 1])
        self.assertAlmostEqual(surfaces[0]['area_m2'], 1.0)
        self.assertEqual([surfaces[0][k] for k in ('min_x', 'min_y', 'max_x', 'max_y')], [0, 0, 1, 1])


if __name__ == '__main__':
    unittest.main()
