"""Synthetic native-layout fixtures test decoding, not game metadata."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

try:
    from PIL import Image
except ImportError:
    Image = None

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare_thumbnails',ROOT/'scripts/prepare_thumbnails.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@unittest.skipIf(Image is None,'optional Pillow is not installed')
class ThumbnailTests(unittest.TestCase):
    def fixture(self,fmt,payload,offset):
        w=h=4
        header=bytearray(offset)
        marker=(fmt+'\0').encode()
        start=93 if fmt=='PF_DXT1' else offset-20
        struct.pack_into('<III',header,start-16,w,h,1)
        struct.pack_into('<i',header,start-4,len(marker))
        header[start:start+len(marker)]=marker
        trailer=struct.pack('<6I',w,h,1,0,0,0)+bytes.fromhex('c1832a9e')
        return bytes(header)+payload+trailer

    def decode(self,b):
        # Use a project-specific scratch override if supplied by the test runner.
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'test.uexp';path.write_bytes(b)
            return module.decode_thumbnail(path)

    def test_bgra_channels(self):
        for offset in (117,120):
            b=self.fixture('PF_B8G8R8A8',bytes([10,20,30,255])*16,offset)
            image,meta=self.decode(b)
            self.assertEqual(image.getpixel((0,0)),(30,20,10,255))
            self.assertEqual(meta['payload_offset'],offset)

    def test_bc1(self):
        # RGB565 red endpoint and zero selectors => red block.
        b=self.fixture('PF_DXT1',struct.pack('<HHI',0xf800,0,0),113)
        image,meta=self.decode(b)
        self.assertEqual(image.size,(4,4))
        self.assertEqual(image.getpixel((0,0))[:3],(255,0,0))

    def test_invalid_footer_and_layout_rejected(self):
        b=self.fixture('PF_DXT1',struct.pack('<HHI',0xf800,0,0),113)
        with self.assertRaises(ValueError):self.decode(b[:-1]+b'X')
        with self.assertRaises(ValueError):self.decode(b[:113]+b'X'+b[113:])


if __name__=='__main__':unittest.main()
