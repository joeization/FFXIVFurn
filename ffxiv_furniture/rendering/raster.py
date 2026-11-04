"""Shared render helpers (camera basis, colour curves, image/labels/ID/depth output) and the `render` entry point, which is GPU-only (raster_gpu.py)."""
import math
from pathlib import Path
import time
import numpy as np
from PIL import Image,ImageDraw,ImageFont


def linear(v):return np.where(v<=.04045,v/12.92,((v+.055)/1.055)**2.4)
def srgb(v):return np.where(v<=.0031308,v*12.92,1.055*np.maximum(v,0)**(1/2.4)-.055)


def camera_basis(camera):
    eye=np.asarray(camera['position'],float);target=np.asarray(camera['target'],float)
    if not np.isfinite([*eye,*target]).all():raise ValueError('Nonfinite camera')
    forward=target-eye
    if np.linalg.norm(forward)<1e-8:raise ValueError('Coincident camera/target')
    forward/=np.linalg.norm(forward);right=np.cross(forward,[0,0,1])
    if np.linalg.norm(right)<1e-8:right=np.cross(forward,[0,1,0])
    right/=np.linalg.norm(right);up=np.cross(right,forward)
    return eye,np.array([right,up,forward])


def finish(rgb,ids,zbuf,meshes,camera,path,size,near,display_gamma,start,input_faces,clipped_faces,updates,textured_updates,*,labels=False,debug_buffers=False):
    """Write only the requested image; ID/depth files are explicit debug outputs."""
    width,height=size
    if display_gamma!=1.0:   # display lift fitted to app screenshot samples: dark/mid tones are brighter in the app (not a physical lighting model)
        covered=np.isfinite(zbuf);rgb[covered]=np.clip(255*(rgb[covered]/255.0)**display_gamma,0,255).astype(np.uint8)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);image=Image.fromarray(rgb);draw=ImageDraw.Draw(image)
    draw.rectangle((0,0,width,40),fill='#182029')
    try:font=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',16)
    except OSError:font=ImageFont.load_default()
    draw.text((10,10),'Native mesh / Base texture preview - approximate lighting, NOT app render',font=font,fill='white')
    artifacts={}
    if labels:
        draw_labels=ImageDraw.Draw(image)
        for object_id in {m['id'] for m in meshes if m.get('role')=='furniture'}:
            ys,xs=np.where(ids==object_id)
            if len(xs)>=30:
                x,y=int(np.median(xs)),int(np.median(ys))
                if y>42:draw_labels.text((x,y),str(object_id),fill='#ffe274',stroke_width=2,stroke_fill='black')
        path=path.with_name(path.stem+'-labeled.png')
        artifacts['labeled']=str(path.resolve())
    image.save(path)
    if debug_buffers:
        stem=path.stem.removesuffix('-labeled')
        id_path=path.with_name(stem+'-ids.png');depth_path=path.with_name(stem+'-depth.npy')
        Image.fromarray(ids).save(id_path);np.save(depth_path,zbuf.astype(np.float32))
        artifacts.update(ids=str(id_path.resolve()),depth=str(depth_path.resolve()))
    return {'image':str(path.resolve()),**artifacts,'seconds':time.perf_counter()-start,
        'input_triangles':input_faces,'near_clipped_triangles':clipped_faces,'visible_triangle_updates':updates,
        'textured_triangle_updates':textured_updates,'visible_object_pixels':{str(i):int(n) for i,n in zip(*np.unique(ids,return_counts=True)) if i},
        'camera':camera,'size':list(size),'near_plane':near}


def render(meshes,camera,path,**kw):
    """OpenGL (moderngl) offscreen rasterizer. The old pure-Python CPU rasterizer was removed (too slow, and it misled code reading); there is no fallback."""
    from .raster_gpu import render_gpu
    return render_gpu(meshes,camera,path,**kw)
