"""Extract native thumbnails and build a traceable candidate manifest.

This is NOT a verified placeable-item list or Item ID import. Unknown IDs remain null.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def decode_thumbnail(path):
    from PIL import Image
    b=path.read_bytes()
    if len(b)<140 or b[-4:]!=bytes.fromhex('c1832a9e'):
        raise ValueError('Unsupported package footer')
    match=re.search(rb'PF_(DXT1|B8G8R8A8)\x00',b[:180])
    if not match:
        raise ValueError('Unsupported pixel format')
    w,h,depth=struct.unpack_from('<III',b,len(b)-28)
    if not (0<w<=4096 and 0<h<=4096 and depth==1):
        raise ValueError('Invalid single-mip dimensions')
    if struct.unpack_from('<III',b,match.start()-16)!=(w,h,1):
        raise ValueError('Platform/trailer dimensions mismatch')
    fmt=match.group()[:-1].decode()
    size=((w+3)//4)*((h+3)//4)*8 if fmt=='PF_DXT1' else w*h*4
    end=len(b)-28
    start=end-size
    expected=(113,) if fmt=='PF_DXT1' else (117,120)
    if start not in expected or start<match.end():
        raise ValueError(f'Unsupported inline/mipmap layout: offset {start}')
    payload=b[start:end]
    if fmt=='PF_DXT1':
        flags=0x1|0x2|0x4|0x1000|0x80000
        header=struct.pack('<7I',124,flags,h,w,size,0,1)+bytes(44)
        header+=struct.pack('<II4s5I',32,4,b'DXT1',0,0,0,0,0)
        header+=struct.pack('<5I',0x1000,0,0,0,0)
        assert len(header)==124
        image=Image.open(io.BytesIO(b'DDS '+header+payload)).convert('RGBA')
    else:
        image=Image.frombytes('RGBA',(w,h),payload,'raw','BGRA')
    image.load()
    return image,{'format':fmt,'width':w,'height':h,'payload_offset':start,'source_sha256':hashlib.sha256(b).hexdigest()}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog',required=True)
    p.add_argument('--legacy-dir',default=str(ROOT/'data/thumbnail-legacy'))
    p.add_argument('--image-dir',default=str(ROOT/'data/thumbnails'))
    p.add_argument('--manifest',default=str(ROOT/'data/classification-manifest.jsonl'))
    p.add_argument('--extract',action='store_true')
    p.add_argument('--retoc')
    p.add_argument('--paks')
    a=p.parse_args(argv)
    legacy=Path(a.legacy_dir).resolve()
    if a.extract:
        if not a.retoc or not a.paks:
            p.error('--extract needs --retoc and --paks')
        subprocess.run([a.retoc,'to-legacy','--filter','_T','--no-shaders',a.paks,str(legacy)],check=True)
    catalog=json.loads(Path(a.catalog).read_text(encoding='utf-8'))
    if not isinstance(catalog,list):
        raise ValueError('Catalog must be a JSON list')
    image_dir=Path(a.image_dir).resolve();image_dir.mkdir(parents=True,exist_ok=True)
    manifest=Path(a.manifest).resolve();manifest.parent.mkdir(parents=True,exist_ok=True)
    rows=[];failures=[];formats=collections.Counter();strata=collections.Counter();keys=set()
    for entry in sorted(catalog,key=lambda x:x['asset_folder']):
        key=entry['asset_folder']
        if key in keys:
            raise ValueError('Duplicate asset key: '+key)
        keys.add(key)
        src=legacy/(key+'/'+entry['name_key_candidate']+'_T.uexp')
        dest=image_dir/(hashlib.sha256(key.encode()).hexdigest()[:24]+'.png')
        try:
            image,meta=decode_thumbnail(src)
            image.save(dest)
            from PIL import Image
            with Image.open(dest) as check: check.verify()
            row={'asset_key':key,'item_id':entry.get('item_id'),
                 'name':entry.get('display_name_candidate'),
                 'source_category':entry['category'],'scope':entry['scope'],
                 'patch':None,'image_path':str(dest),
                 'image_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
                 'source_thumbnail':str(src),'thumbnail_metadata':meta,
                 'metadata_status':'asset-folder candidate; placeability and Item ID unverified'}
            rows.append(row);formats[meta['format']]+=1;strata[(row['scope'],row['source_category'])]+=1
        except (ValueError,OSError,struct.error) as exc:
            failures.append({'asset_key':key,'source':str(src),'error':str(exc)})
    # Replace only after the complete batch has been examined.
    stage=manifest.with_suffix('.staging.jsonl')
    stage.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    stage.replace(manifest)
    report={'candidate_count':len(catalog),'decoded_count':len(rows),'failed_count':len(failures),
            'unique_image_count':len({r['image_sha256'] for r in rows}),
            'confirmed_item_ids':sum(r['item_id'] is not None for r in rows),
            'formats':dict(formats),'strata':[{'scope':s,'category':c,'count':n} for (s,c),n in sorted(strata.items())],
            'failures':failures,'manifest':str(manifest),'all_game_patches_included':True}
    manifest.with_suffix('.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if rows else 1


if __name__=='__main__':
    sys.exit(main())
