"""Real schematic CLI regression; source layouts stay local."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import sqlite3
from contextlib import closing
from PIL import Image
from scripts.layout_schematic import load_items
ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT/'outputs/deco-sessions/s-woodland/S_Woodland_Retreat-r34.json'

@unittest.skipUnless(LAYOUT.exists(), 'Local example layout absent')
class SchematicPlanningTests(unittest.TestCase):
    def test_default_plan_does_not_allocate_furniture_inventory_space(self):
        with tempfile.TemporaryDirectory() as folder:
            p = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'scripts/layout_schematic.py'), str(LAYOUT), '--out', folder], cwd=ROOT, capture_output=True, text=True, check=True)
            report = json.loads(p.stdout)
            with Image.open(report['image']) as image:
                self.assertEqual(image.height, 1800)
            self.assertFalse(report['furniture_index'])

class SchematicFloorAssignmentTests(unittest.TestCase):
    def test_medium_upper_is_separate_from_elevated_ground_furniture(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'bounds.sqlite3'
            with closing(sqlite3.connect(db)) as con:
                con.execute('create table furniture_bounds(id integer,min_x real,min_y real,min_z real,max_x real,max_y real,max_z real)')
                con.execute('insert into furniture_bounds values(1,-1,-1,0,1,1,1)')
                con.execute('insert into furniture_bounds values(2,-1,-1,-7,1,1,0)')
                con.commit()
            def item(ident,z):
                return {'name':'Measured fixture','itemId':ident,'transform':{'location':[0,0,z],'rotation':[0,0,0,1],'scale':[1,1,1]}}
            layout={'houseSize':'Medium','interiorScale':100,'interiorFurniture':[item(1,0),item(1,700),item(1,400),item(2,700)]}
            rows=load_items(layout,db)
            self.assertEqual([r['level'] for r in rows],['ground','upper','ground','ground'])
            self.assertEqual([r['height'] for r in rows],[0,0,4,0])

if __name__ == '__main__':
    unittest.main()
