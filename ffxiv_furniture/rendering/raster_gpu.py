"""GPU rasterizer (OpenGL 3.3 via moderngl, offscreen); the only rasterizer (the CPU reference was removed).

Shading: per-triangle flat shade .32+.68*|n.l|, linear-light texture sampling with a manual bilinear (texel centres at 0..size-1, wrap by fract),
untextured flat_color / grey fallback, optional approximate tint, view-only horizontal mirror (camera['mirror_x']), cutaway enclosure skipping, stair sectioning (cut_stairs_z),
no face culling, near-plane clipping. Outputs (RGB, 16-bit object ids, eye-space depth) go through `finish` in raster.py.
Float32 precision and OpenGL edge rules mean a few edge pixels can land on a neighbouring object id.
"""
from __future__ import annotations
import math
import time
import numpy as np
import moderngl
from .raster import camera_basis, finish

FAR = 200.0
BACKGROUND = (32, 39, 44)

VERTEX = '''
#version 330
uniform vec3 eye; uniform mat3 basis; uniform vec4 proj;   // proj = (fx, fy, A, B)
in vec3 pos; in vec2 uv; in float shade; in vec3 nrm;
out vec2 v_uv; out float v_shade; out float v_depth; out vec3 v_pos; out vec3 v_nrm;
void main(){
    vec3 c = basis * (pos - eye);
    gl_Position = vec4(proj.x * c.x, proj.y * c.y, proj.z * c.z + proj.w, c.z);
    v_uv = uv; v_shade = shade; v_depth = c.z; v_pos = pos; v_nrm = nrm;
}
'''

FRAGMENT = '''
#version 330
uniform sampler2D tex; uniform int cutout; uniform int mode; uniform vec3 base; uniform vec3 tint; uniform int use_tint; uniform ivec2 tsize; uniform int obj_id;
in vec2 v_uv; in float v_shade; in float v_depth; in vec3 v_pos; in vec3 v_nrm;
uniform int lit; uniform vec3 eye_pos; uniform vec3 ambient_lo; uniform vec3 ambient_hi; uniform int n_lights; uniform vec4 light_pos[64]; uniform vec4 light_col[64]; uniform vec3 emissive; uniform float exposure;
layout(location=0) out vec4 o_rgb; layout(location=1) out vec4 o_id; layout(location=2) out float o_depth;
vec3 lin(vec3 v){ return mix(pow((v + 0.055) / 1.055, vec3(2.4)), v / 12.92, lessThanEqual(v, vec3(0.04045))); }
vec3 srgb(vec3 v){ return mix(1.055 * pow(max(v, 0.0), vec3(1.0 / 2.4)) - 0.055, v * 12.92, lessThanEqual(v, vec3(0.0031308))); }
vec3 texel(ivec2 p){ return lin(texelFetch(tex, p, 0).rgb); }
void main(){
    if (cutout == 1 && mode == 0 && texelFetch(tex, ivec2(floor(fract(v_uv) * vec2(tsize - 1) + 0.5)), 0).a < 0.5) discard;
    vec3 col;
    if (lit == 1) {
        vec3 alb;
        if (mode == 0) {
            vec2 t = fract(v_uv) * vec2(tsize - 1);
            ivec2 i0 = ivec2(floor(t)); vec2 f = t - vec2(i0); ivec2 i1 = min(i0 + 1, tsize - 1);
            alb = (texel(i0) * (1.0 - f.x) + texel(ivec2(i1.x, i0.y)) * f.x) * (1.0 - f.y) + (texel(ivec2(i0.x, i1.y)) * (1.0 - f.x) + texel(i1) * f.x) * f.y;
            if (use_tint == 1) alb *= tint;
        } else if (mode == 1) alb = base; else alb = lin(vec3(base.x));
        vec3 N = normalize(v_nrm); vec3 V = normalize(eye_pos - v_pos); if (dot(N, V) < 0.0) N = -N;
        vec3 irr = mix(ambient_lo, ambient_hi, 0.5 + 0.5 * N.z);
        for (int i = 0; i < n_lights; i++) {
            vec3 d = light_pos[i].xyz - v_pos; float dist = length(d); float R = light_pos[i].w;
            float wrap = clamp((dot(N, d / max(dist, 1e-4)) + 0.35) / 1.35, 0.0, 1.0);
            float att = 1.0 / (1.0 + (dist * dist) / (R * R)); float cut = clamp(1.0 - dist / (4.0 * R), 0.0, 1.0);
            irr += light_col[i].rgb * wrap * att * cut;
        }
        vec3 c = alb * irr + emissive * alb;
        c = 1.0 - exp(-c * exposure);
        col = srgb(c);
    } else if (mode == 0) {
        vec2 t = fract(v_uv) * vec2(tsize - 1);
        ivec2 i0 = ivec2(floor(t)); vec2 f = t - vec2(i0); ivec2 i1 = min(i0 + 1, tsize - 1);
        vec3 c = (texel(i0) * (1.0 - f.x) + texel(ivec2(i1.x, i0.y)) * f.x) * (1.0 - f.y) + (texel(ivec2(i0.x, i1.y)) * (1.0 - f.x) + texel(i1) * f.x) * f.y;
        if (use_tint == 1) c *= tint;
        col = srgb(c * v_shade);
    } else if (mode == 1) col = srgb(base * v_shade);       // base = linear(flat_color)
    else col = base * v_shade;                                // grey fallback is applied in display space
    o_rgb = vec4(clamp(col, 0.0, 1.0), 1.0);
    o_id = vec4(float(obj_id & 255) / 255.0, float(obj_id >> 8) / 255.0, 0.0, 1.0);
    o_depth = v_depth;
}
'''


def _lin(v):
    v = np.asarray(v, float); return np.where(v <= .04045, v / 12.92, ((v + .055) / 1.055) ** 2.4)


class _Gpu:
    ctx = None
    prog = None
    cache = {}     # (id(meshes), len(meshes)) -> prepared per-mesh buffers; only the latest scene is kept
    ref = None     # strong reference to that scene so its id() cannot be reused by a different scene
    texture_pool = {}  # texture-array identity + opacity mode; owned once per scene

    @classmethod
    def context(cls):
        if cls.ctx is None:
            cls.ctx = moderngl.create_standalone_context(require=330); cls.prog = cls.ctx.program(vertex_shader=VERTEX, fragment_shader=FRAGMENT)
        return cls.ctx, cls.prog


LIGHT = np.array([.3, -.4, .85]); LIGHT = LIGHT / np.linalg.norm(LIGHT)


def _prepare(ctx, prog, mesh, cut, texture_pool=None):
    world = np.asarray(mesh['vertices'], np.float64); tri = np.asarray(mesh['triangles'], np.int64).reshape(-1, 3)
    if cut is not None and len(tri): tri = tri[world[tri][:, :, 2].min(axis=1) <= cut]
    if not len(tri): return None
    p, q, r = world[tri[:, 0]], world[tri[:, 1]], world[tri[:, 2]]; nrm = np.cross(q - p, r - p); norm = np.linalg.norm(nrm, axis=1)
    shade = np.where(norm > 1e-8, .32 + .68 * np.abs(nrm @ LIGHT) / np.maximum(norm, 1e-30), .32).astype('f4')
    uv = mesh.get('uv'); uvs = np.asarray(uv, 'f4')[tri].reshape(-1, 2) if uv is not None else np.zeros((len(tri) * 3, 2), 'f4')
    fn = (nrm / np.maximum(norm, 1e-30)[:, None]).astype('f4')
    data = np.concatenate([world[tri].reshape(-1, 3).astype('f4'), uvs, np.repeat(shade, 3)[:, None], np.repeat(fn, 3, axis=0)], axis=1).astype('f4')
    vbo = ctx.buffer(data.tobytes()); vao = ctx.vertex_array(prog, [(vbo, '3f 2f 1f 3f', 'pos', 'uv', 'shade', 'nrm')])
    material = mesh.get('material') or {}; tex = material.get('texture'); texture = None; tsize = (1, 1)
    if tex is not None:
        co = bool(material.get('cutout')); tsize = (tex.shape[1], tex.shape[0]); tk=(id(tex),co)
        texture=texture_pool.get(tk) if texture_pool is not None else None
        if texture is None:
            arr = np.ascontiguousarray(np.asarray(tex)[:, :, :4 if co else 3].astype(np.uint8))
            texture = ctx.texture(tsize, 4 if co else 3, arr.tobytes(), alignment=1); texture.filter = (moderngl.NEAREST, moderngl.NEAREST); texture.repeat_x = texture.repeat_y = False
            if texture_pool is not None:texture_pool[tk]=texture
    tint = material.get('tint')
    if texture is not None: mode, base = 0, (1, 1, 1)
    elif mesh.get('flat_color') is not None: mode, base = 1, tuple(float(x) for x in _lin(mesh['flat_color']))
    else: mode, base = 2, (185 / 255,) * 3
    return {'vao': vao, 'vbo': vbo, 'texture': texture, 'tsize': tsize, 'mode': mode, 'base': base, 'tint': tuple(float(x) for x in tint[:3]) if tint is not None else None, 'cutout': bool(material.get('cutout')) and texture is not None, 'id': int(mesh['id']), 'triangles': len(tri), 'tri': tri.astype(np.int32), 'world': world}


def render_gpu(meshes, camera, path, *, size=(960, 640), near=.1, approximate_tint=False, display_gamma=1.0, labels=False, debug_buffers=False):
    start = time.perf_counter(); width, height = size; fov = camera.get('fov', 70)
    if not 1 < fov < 175 or near <= 0 or min(size) < 32: raise ValueError('Invalid camera projection')
    sx = -1 if camera.get('mirror_x') else 1
    eye, basis = camera_basis(camera); focal = width / (2 * math.tan(math.radians(fov) / 2))
    ctx, prog = _Gpu.context()
    key = (id(meshes), len(meshes))
    if key not in _Gpu.cache:
        for old in _Gpu.cache.values():
            for m in old.values():
                if m: m['vbo'].release(); m['vao'].release()
        for texture in _Gpu.texture_pool.values():texture.release()
        _Gpu.texture_pool={}
        _Gpu.cache = {key: {}}; _Gpu.ref = meshes
    prepared = _Gpu.cache[key]
    fbo = ctx.framebuffer([ctx.texture(size, 4, dtype='f1'), ctx.texture(size, 4, dtype='f1'), ctx.texture(size, 1, dtype='f4')], ctx.depth_texture(size))
    fbo.use(); fbo.clear(0.0, 0.0, 0.0, 0.0, 1.0); ctx.enable(moderngl.DEPTH_TEST); ctx.disable(moderngl.CULL_FACE); ctx.depth_func = '<'
    A = (FAR + near) / (FAR - near); B = -2 * FAR * near / (FAR - near)
    prog['eye'].value = tuple(float(x) for x in eye); prog['basis'].write(np.ascontiguousarray(basis.T, dtype='f4').tobytes())
    prog['proj'].value = (sx * 2 * focal / width, 2 * focal / height, A, B)
    lighting = camera.get('lighting'); L = lighting.get('lights', [])[:64] if lighting else []
    prog['lit'].value = int(bool(lighting)); prog['eye_pos'].value = tuple(float(x) for x in eye); prog['exposure'].value = float(lighting.get('exposure', 1.0)) if lighting else 1.0
    prog['ambient_lo'].value = tuple(float(x) for x in _lin(lighting.get('ambient_lo', (.05, .05, .06)))) if lighting else (0, 0, 0)
    prog['ambient_hi'].value = tuple(float(x) for x in _lin(lighting.get('ambient_hi', (.1, .1, .12)))) if lighting else (0, 0, 0)
    prog['n_lights'].value = len(L)
    if L:
        lp = np.zeros((64, 4), 'f4'); lc = np.zeros((64, 4), 'f4')
        for k, l in enumerate(L): lp[k] = [*l['pos'], l.get('radius', 3.0)]; lc[k, :3] = np.asarray(l['color'], float) * l.get('intensity', 1.0)
        prog['light_pos'].write(lp.tobytes()); prog['light_col'].write(lc.tobytes())
    input_faces = 0; clipped = 0
    for index, mesh in enumerate(meshes):
        if camera.get('cutaway') and mesh.get('role') in ('enclosure', 'upper_enclosure'): continue
        if mesh.get('role') == 'void' and not camera.get('cutaway'): continue   # walled-off floor marker: plan cutaways only
        ha = camera.get('hide_above_z'); hb = camera.get('hide_below_z')
        if ha is not None or hb is not None:
            zz = np.asarray(mesh['vertices'])[:, 2]
            if ha is not None and zz.min() >= ha: continue
            if hb is not None and zz.max() <= hb: continue
        if not 0 < mesh['id'] < 65536: raise ValueError('Object ID exceeds lossless16-bit output')
        cut = camera.get('cut_stairs_z') if mesh.get('role') == 'stair' else None
        pk = (index, cut)
        if pk not in prepared: prepared[pk] = _prepare(ctx, prog, mesh, cut, texture_pool=_Gpu.texture_pool)
        m = prepared[pk]
        if m is None: continue
        input_faces += m['triangles']
        zc = (m['world'] - eye) @ basis[2]; zt = zc[m['tri']]; clipped += int(((zt.min(axis=1) < near) & (zt.max(axis=1) >= near)).sum())   # statistic only; the GPU does the clipping
        prog['emissive'].value = tuple(float(x) for x in mesh.get('emissive', (0, 0, 0))) if lighting else (0, 0, 0)
        prog['cutout'].value = int(m['cutout']); prog['mode'].value = m['mode']; prog['base'].value = m['base']; prog['obj_id'].value = m['id']; prog['tsize'].value = m['tsize']
        use_tint = bool(approximate_tint and m['tint'] is not None); prog['use_tint'].value = int(use_tint); prog['tint'].value = m['tint'] if use_tint else (1.0, 1.0, 1.0)
        if m['texture'] is not None: m['texture'].use(0); prog['tex'].value = 0
        m['vao'].render(moderngl.TRIANGLES)
    rgba = np.frombuffer(fbo.read(components=4, attachment=0, dtype='f1'), np.uint8).reshape(height, width, 4)[::-1]
    idc = np.frombuffer(fbo.read(components=4, attachment=1, dtype='f1'), np.uint8).reshape(height, width, 4)[::-1]
    depth = np.frombuffer(fbo.read(components=1, attachment=2, dtype='f4'), np.float32).reshape(height, width)[::-1]
    for t in fbo.color_attachments: t.release()
    fbo.depth_attachment.release(); fbo.release()
    ids = (idc[:, :, 0].astype(np.uint16) | (idc[:, :, 1].astype(np.uint16) << 8)); covered = ids > 0
    rgb = np.array(rgba[:, :, :3]); rgb[~covered] = BACKGROUND
    zbuf = np.where(covered, depth.astype(np.float64), np.inf)
    return finish(rgb, np.ascontiguousarray(ids), zbuf, meshes, camera, __import__('pathlib').Path(path), size, near, display_gamma, start, input_faces, clipped, int(covered.sum()), int(covered.sum()), labels=labels, debug_buffers=debug_buffers)
