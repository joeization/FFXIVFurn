"""Compare rendered colours of known items with pixels sampled from an app screenshot (user-provided). Usage: check_colors_vs_app.py <layout.json> <out_dir>
Boxes are in the 960x640 render of the fixed camera below; app values were sampled from the user's 1922x1112 screenshot (medians)."""
from pathlib import Path
import sys
import numpy as np
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture.rendering.pipeline import run_pipeline
lay, out = Path(sys.argv[1]), Path(sys.argv[2])
cams = [{'name': 'shelf-and-screens', 'position': [9.5, 1.0, 2.6], 'target': [6.0, -5.0, 1.2], 'fov': 70}]
run_pipeline(lay, out, db_path=ROOT / 'data/furniture.sqlite3', room_context=True, rough_room_finish=True, approximate_tint=False, cameras=cams, size=(960, 640))
a = np.asarray(Image.open(out / 'view-01.png').convert('RGB'), float)
B = {'rug (Flooring Mat, Cork Brown)': ((20, 470, 140, 560), (196, 135, 73)), 'round table top (Qiqirn Brown)': ((0, 385, 90, 420), (163, 105, 55)),
     'floor planks (Dark Wood Flooring)': ((420, 520, 640, 600), (132, 81, 58)), 'bookshelf frame': ((190, 200, 205, 420), (112, 92, 71)), 'lattice wood': ((590, 90, 640, 330), (74, 49, 25))}
tot = []
for k, (box, app) in B.items():
    x0, y0, x1, y1 = box; m = np.median(a[y0:y1, x0:x1].reshape(-1, 3), 0); err = np.abs(m - np.array(app)); tot.append(err.mean())
    print(f'{k:36} render {m.round(0)}  app {app}  abs err {err.round(0)}')
print('mean abs error over samples:', round(float(np.mean(tot)), 1))
