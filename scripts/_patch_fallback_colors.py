from pathlib import Path
R = Path(__file__).resolve().parents[1]
def patch(rel, pairs):
    p = R / rel; s = p.read_text(encoding='utf-8')
    for a, b in pairs:
        assert a in s, (rel, a[:80]); s = s.replace(a, b, 1)
    p.write_text(s, encoding='utf-8')

patch('ffxiv_furniture/rendering/assets.py', [
("class Assets:\n    def __init__(self,records,cache_dir,dyes=None):\n        self.dyes=dyes or {};", "class Assets:\n    def __init__(self,records,cache_dir,dyes=None,fallback_colours=None):\n        self.dyes=dyes or {};self.fallback_colours=fallback_colours or {}   # item_id -> '#rrggbb' estimated colour for meshes whose material carries no texture"),
("            except (ValueError,KeyError,struct.error,IndexError,OSError) as error:entry['warning']=str(error)\n            decoded.append(entry)", "            except (ValueError,KeyError,struct.error,IndexError,OSError) as error:entry['warning']=str(error)\n            if entry['texture'] is None:\n                fb=self.fallback_colours.get(item_id)\n                if fb: entry['flat_color']=((int(fb[1:3],16)/255, int(fb[3:5],16)/255, int(fb[5:7],16)/255))\n            decoded.append(entry)"),
])
patch('ffxiv_furniture/rendering/pipeline.py', [
("        assets=Assets(records,ROOT/'outputs/render-pipeline/cache',dyes=dyes)", """        fallback={}
        try:
            for iid,hx in db.execute(\"SELECT item_id,c1_hex FROM item_colors WHERE c1_hex IS NOT NULL\"): fallback[iid]=hx   # measured where available, estimated (est_from) for untextured meshes; never a neutral grey
        except sqlite3.OperationalError:pass
        assets=Assets(records,ROOT/'outputs/render-pipeline/cache',dyes=dyes,fallback_colours=fallback)"""),
])
patch('ffxiv_furniture/design/resolve.py', [
("try: col = c.execute('SELECT hue_name,c1_hex,c2_hex FROM item_colors WHERE item_id=?', (x['item_id'],)).fetchone()", "try: col = c.execute('SELECT hue_name,c1_hex,c2_hex,est_from FROM item_colors WHERE item_id=?', (x['item_id'],)).fetchone()"),
("'colour': ({'name': col[0], 'main': col[1], 'second': col[2]} if col and col[0] else None)", "'colour': ({'name': col[0], 'main': col[1], 'second': col[2], 'estimated': bool(col[3])} if col and col[0] else None)"),
])
print('ok')
