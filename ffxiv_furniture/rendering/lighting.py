"""Shared approximate light classification, moods and the shader's bounded budget."""
import re

MOODS = {
    'day': dict(lo=(.45,.44,.42), hi=(.75,.78,.85), exposure=1.3, scale=.5),
    'dusk': dict(lo=(.10,.09,.10), hi=(.22,.22,.28), exposure=1.25, scale=1.0),
    'night': dict(lo=(.04,.04,.07), hi=(.08,.09,.15), exposure=1.4, scale=1.2),
}


def resolve_mood(lighting):
    if isinstance(lighting, dict):
        return lighting
    name = 'dusk' if lighting is True or lighting == 'warm' else lighting
    if not isinstance(name, str) or name not in MOODS:
        raise ValueError('Unknown lighting mood')
    return MOODS[name].copy()


def emitter_light(name, has_emissive_material=False):
    """Conservative name heuristic; a flame-themed name alone is not an emitter."""
    nm = name.lower()
    if not has_emissive_material and not re.search(
        r'\b(lamps?|lampposts?|cosmolamp|lanterns?|chandeliers?|candles?|candlestands?|candlelit|braziers?|fireplaces?|campfires?|cookfires?|bonfires?|torch(?:es)?|sconces?|hearths?|stoves?|pendant wall light|wall lights?|path lights?|studio lights?|illuminated|neon|lighting)\b|\bfire pit\b', nm
    ):
        return None
    if re.search(r'fireplace|campfire|fire pit|brazier|hearth|bonfire|stove', nm):
        col, intensity, radius = (1.0,.55,.25), 2.2, 1.9
    elif re.search(r'chandelier|pendant', nm):
        col, intensity, radius = (1.0,.82,.55), 2.2, 3.2
    elif 'candle' in nm:
        col, intensity, radius = (1.0,.7,.4), .7, 1.0
    elif 'wall' in nm or 'sconce' in nm:
        col, intensity, radius = (1.0,.75,.45), 1.4, 1.7
    else:
        col, intensity, radius = (1.0,.78,.5), 1.3, 1.5
    return dict(color=list(col), intensity=intensity, radius=radius)


def apply_light_budget(lights, meshes, cap=64):
    ranked = sorted(lights, key=lambda light: -light['intensity'] * light['radius'])
    kept, dropped = ranked[:cap], ranked[cap:]
    dropped_ids = {light['id'] for light in dropped if 'id' in light}
    kept_ids = {light['id'] for light in kept if 'id' in light}
    for mesh in meshes:
        if mesh['id'] in dropped_ids - kept_ids:
            mesh.pop('emissive', None)
    message = f'Light budget: kept {len(kept)}, dropped {len(dropped)} point lights; dropped emitters have no glow.' if dropped else None
    return kept, dropped, message
