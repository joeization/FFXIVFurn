"""Backfill item_colors for items whose mesh carries no usable material/texture: estimated approximate colour =
mean of measured c1_hex of sibling items (same name keyword + same source category). Honest label: est_from set,
c*_frac left null, and the selector treats est colours as 'colour unknown' so design decisions stay on measured colours."""
import math, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture import FurnitureDB


def hue_name(r, g, b):
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if v < 0.12: return 'black'
    if s < 0.12: return 'white' if v > 0.75 else 'grey'
    d = h * 360
    if 15 <= d < 45 and v < 0.62 and s < 0.75: return 'brown'
    for name, lo, hi in (('red', -10, 15), ('orange', 15, 45), ('yellow', 45, 70), ('green', 70, 165), ('cyan', 165, 195), ('blue', 195, 255), ('purple', 255, 290), ('pink', 290, 350)):
        lo = lo % 360; hi = hi % 360
        if (lo <= hi and lo <= d < hi) or (lo > hi and (d >= lo or d < hi)): return name
    return 'red'


def main():
    with FurnitureDB(ROOT / 'data/furniture.sqlite3') as db:
        c = db.connection
        cols = [r[1] for r in c.execute('pragma table_info(item_colors)')]
        if 'est_from' not in cols: c.execute('ALTER TABLE item_colors ADD COLUMN est_from TEXT')
        rows = c.execute("select item_id from item_colors where hue_name is null").fetchall()
        done = skipped = 0
        for (item_id,) in rows:
            f = c.execute('select name from furniture where id=?', (item_id,)).fetchone()
            cat = c.execute('select source_category from candidate_assets where item_id=?', (item_id,)).fetchone()
            if not f: skipped += 1; continue
            kw = (f['name'].lower().split() or [''])[0]
            sib = c.execute("""select ic.c1_hex from item_colors ic join furniture f on f.id=ic.item_id
                join candidate_assets ca on ca.item_id=ic.item_id
                where lower(f.name) like ? and coalesce(ic.est_from,'')='' and ic.hue_name is not null and ic.c1_hex is not null limit 200""", (kw + '%',)).fetchall()
            if len(sib) < 3 and cat:
                sib = c.execute("""select ic.c1_hex from item_colors ic join candidate_assets ca on ca.item_id=ic.item_id
                    where ca.source_category=? and coalesce(ic.est_from,'')='' and ic.hue_name is not null and ic.c1_hex is not null limit 200""", (cat['source_category'],)).fetchall()
            if len(sib) < 3: skipped += 1; print(f'  item {item_id} ({f["name"]}): fewer than 3 siblings, left NULL'); continue
            px = [(int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)) for h in (r[0] for r in sib)]
            m = tuple(round(sum(p[i] for p in px) / len(px)) for i in range(3))
            hx = '#%02x%02x%02x' % m
            c.execute("update item_colors set c1_hex=?, hue_name=?, mean_h=?, mean_s=?, mean_v=?, c1_frac=null, est_from=? where item_id=?",
                      (hx, hue_name(*m), *rgb_to_hsv(*m), f'approx:{kw}:{len(sib)} siblings', item_id))
            done += 1; print(f'  item {item_id} ({f["name"]}): est {hx} from {len(sib)} siblings')
        c.commit()
        print(f'estimated {done}, left NULL {skipped}')
    return 0


def rgb_to_hsv(r, g, b):
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255); return round(h, 3), round(s, 3), round(v, 3)


if __name__ == '__main__':
    sys.exit(main())
