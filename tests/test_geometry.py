import hashlib
import importlib.util
import math
from pathlib import Path
import struct
import tempfile
import unittest
from ffxiv_furniture.geometry import read_static_mesh_bounds
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles

spec=importlib.util.spec_from_file_location('arrange_ground_floor',Path(__file__).resolve().parents[1]/'scripts/arrange_ground_floor.py')
arr=importlib.util.module_from_spec(spec);spec.loader.exec_module(arr)


def fixture():
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


class GeometryTests(unittest.TestCase):
    def save(self,folder,data):
        p=Path(folder)/'mesh.uexp';p.write_bytes(data);p.with_suffix('.uasset').write_bytes(b'StaticMesh\0');return p

    def test_buffers_bounds_and_triangles_agree(self):
        with tempfile.TemporaryDirectory() as temp:
            p=self.save(temp,fixture());r=read_static_mesh_bounds(p)
            self.assertEqual([r[k] for k in ('length_m','width_m','height_m')],[2,1,1])
            self.assertEqual(r['local_min_m'],[0,0,0])
            self.assertEqual(r['local_max_m'],[2,1,1])
            vertices,triangles=read_static_mesh_triangles(r)
            self.assertEqual(vertices,[(0,0,0),(2,0,0),(0,1,1)])
            self.assertEqual(triangles,[(0,1,2)])

    def test_signature_alone_is_insufficient(self):
        with tempfile.TemporaryDirectory() as temp:
            b=bytearray(fixture());struct.pack_into('<I',b,2+16+3*12+2+20,99)
            with self.assertRaises(ValueError):read_static_mesh_bounds(self.save(temp,b))
            b=bytearray(fixture());struct.pack_into('<f',b,18,math.nan)
            with self.assertRaises(ValueError):read_static_mesh_bounds(self.save(temp,b))

    def test_independent_bounds_and_source_hash_required(self):
        with tempfile.TemporaryDirectory() as temp:
            p=self.save(temp,fixture());r=read_static_mesh_bounds(p)
            b=bytearray(p.read_bytes());struct.pack_into('<d',b,r['bounds_offset'],999)
            p.write_bytes(b)
            with self.assertRaises(ValueError):read_static_mesh_bounds(p)
            with self.assertRaisesRegex(ValueError,'changed'):read_static_mesh_triangles(r)

    def test_triangle_support_not_bounding_box_top(self):
        vertices=[(0,0,.9),(2,0,.9),(0,2,.9),(0,0,1.02)]
        triangles=[(0,1,2)]
        self.assertAlmostEqual(arr.projected_surface(vertices,triangles,.5,.5),.9)
        with self.assertRaises(ValueError):arr.projected_surface(vertices,triangles,3,3)

    def test_pivot_relative_rotated_bounds(self):
        g={'min_x':-1,'max_x':3,'min_y':-2,'max_y':2,'min_z':.5,'max_z':1.5}
        b=arr.rotated_bounds(g,[10,20,-.5],90)
        self.assertAlmostEqual(b['min'][0],8)
        self.assertAlmostEqual(b['max'][0],12)
        self.assertAlmostEqual(b['min'][1],19)
        self.assertAlmostEqual(b['max'][1],23)
        self.assertEqual(b['min'][2],0)


if __name__=='__main__':unittest.main()
