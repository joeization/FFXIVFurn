"""Bounded material proof regression tests; real-asset tests skip outside this workspace."""
import importlib.util
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
if not importlib.util.find_spec('numpy'):raise unittest.SkipTest('Optional numpy absent')
spec=importlib.util.spec_from_file_location('material_spike',ROOT/'spikes/002-native-material-render/extract.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SOURCE=ROOT/'data/geometry-legacy/MakePlace/Content/GameAssets/Furniture/Chair/LeatherSofa'

class MaterialHeaderTests(unittest.TestCase):
    def test_zero_mask_and_truncation(self):
        r=m.Reader(struct.pack('<H',0x0780)+bytes([6]),[])
        self.assertEqual(r.header(),([0,1,2],{1,2}))
        with self.assertRaises(ValueError):m.Reader(struct.pack('<H',0x0780),[]).header()

@unittest.skipUnless(SOURCE.exists(),'Local native sofa assets not present')
class NativeMaterialTests(unittest.TestCase):
    def test_native_material_binding(self):
        result=m.material_instance(SOURCE/'MI_LeatherSofa_0.uasset')
        self.assertTrue(result['parent'].endswith('M_MasterTint.M_MasterTint'))
        self.assertEqual(result['parameters']['Base']['kind'],'texture')
        self.assertIn('fun_b0_m0899_1a_d',result['parameters']['Base']['value'])
        self.assertEqual(result['parameters']['Tint']['value'][3],1)
        self.assertGreater(result['remaining_native_properties_not_decoded'],0)

    def test_external_and_inline_mips_all_checked(self):
        for suffix in ('d','n','s'):
            image,meta=m.decode_texture(SOURCE/('fun_b0_m0899_1a_'+suffix+'.uasset'))
            self.assertEqual(image.size,(512,512));self.assertEqual(len(meta['mips']),10)
            self.assertEqual(meta['mips'][-1]['dimensions'],[1,1])
            self.assertEqual(len(meta['source_file_hashes']),3)

    def test_wrong_resource_index_rejected_without_source_write(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'texture.uasset'
            for suffix in ('.uasset','.uexp','.ubulk'):shutil.copyfile(SOURCE/('fun_b0_m0899_1a_d'+suffix),target.with_suffix(suffix))
            data=bytearray(target.with_suffix('.uexp').read_bytes());struct.pack_into('<i',data,106,1);target.with_suffix('.uexp').write_bytes(data)
            with self.assertRaisesRegex(ValueError,'resource index'):m.decode_texture(target)

if __name__=='__main__':unittest.main()
