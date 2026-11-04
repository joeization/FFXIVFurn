"""Pure, approximate palette matching; all HSV components use the 0..1 scale.

Targets are dictionaries with h/s/v ranges and an HSV target. Hue ranges may
wrap through zero. Unknown colour descriptions raise ValueError, not a silent
fallback. Multiple colours are alternatives: a dominant colour matching any
requested colour contributes zero distance.
"""
import colorsys
import math
import re

# centre HSV, half-widths HSV (hue is circular)
_COLORS = {
    'red': ((0., .8, .75), (.045, .3, .25)),
    'crimson': ((.98, .85, .65), (.035, .25, .25)),
    'orange': ((.075, .85, .85), (.045, .3, .2)),
    'amber': ((.105, .8, .9), (.04, .35, .2)),
    'yellow': ((.155, .8, .9), (.04, .35, .2)),
    'green': ((.33, .65, .65), (.11, .35, .3)),
    'jade': ((.40, .65, .65), (.065, .3, .25)),
    'cyan': ((.50, .7, .8), (.065, .3, .2)),
    'blue': ((.63, .75, .7), (.075, .3, .3)),
    'purple': ((.76, .65, .65), (.075, .35, .3)),
    'pink': ((.91, .4, .95), (.065, .35, .15)),
    'brown': ((.075, .6, .40), (.055, .35, .22)),
    'cream': ((.13, .13, .97), (.09, .13, .10)),
    'ivory': ((.13, .07, .98), (.10, .07, .08)),
    'white': ((0., .025, .97), (.5, .055, .10)),
    'grey': ((0., .03, .5), (.5, .09, .3)),
    'black': ((0., .02, .055), (.5, .98, .055)),
    'charcoal': ((0., .03, .20), (.5, .10, .12)),
    'beige': ((.10, .23, .82), (.07, .18, .16)),
    'oak': ((.09, .45, .6), (.06, .3, .25)),
}


def palette_names_to_hsv_ranges(names):
    """Map English descriptions to [{name, target, h, s, v}].

    Examples: dark brown, cream, warm amber, jade green, crimson, ivory,
    charcoal. Specific words (jade) take precedence over generic ones (green).
    h=(low,high) wraps if low>high; unrestricted hue is (0,1).
    """
    if isinstance(names, str):
        names = [names]
    result = []
    for name in names:
        words = set(re.findall(r'[a-z]+', name.lower().replace('gray', 'grey')))
        key = next((k for k in ('jade', 'crimson', 'ivory', 'charcoal', 'cream', 'amber') if k in words), None)
        key = key or next((k for k in _COLORS if k in words), None)
        if key is None:
            raise ValueError(f'Unknown palette colour: {name!r}')
        (h, s, v), (dh, ds, dv) = _COLORS[key]
        if 'dark' in words:
            v *= .60
            dv *= .65
        elif 'light' in words or 'pale' in words:
            v = min(1., v + .22)
            s *= .6
        if 'muted' in words:
            s *= .55
        result.append({'name': name, 'target': (h, s, v),
                       'h': (0., 1.) if dh == .5 else ((h-dh) % 1., (h+dh) % 1.),
                       's': (max(0., s-ds), min(1., s+ds)),
                       'v': (max(0., v-dv), min(1., v+dv))})
    return result


def _range_gap(value, bounds, circular=False):
    lo, hi = bounds
    if (lo <= value <= hi) or (circular and lo > hi and (value >= lo or value <= hi)):
        return 0.
    if circular:
        return 2 * min(abs(value-lo), 1-abs(value-lo), abs(value-hi), 1-abs(value-hi))
    return min(abs(value-lo), abs(value-hi))


def color_distance(item_row, targets):
    """Weighted dominant-colour distance to nearest target, bounded to [0,1].

    Accept dict or sqlite3.Row. Missing colours score 1; an empty palette
    imposes no constraint (0). Mean HSV is a fallback for rows without c1..c3.
    Low saturation suppresses hue, so white/grey are not falsely red.
    """
    if not targets:
        return 0.
    keys = set(item_row.keys())
    colors = []
    for i in (1, 2, 3):
        value = item_row[f'c{i}_hex'] if f'c{i}_hex' in keys else None
        if value:
            rgb = tuple(int(value[j:j+2], 16)/255 for j in (1, 3, 5))
            fraction = item_row[f'c{i}_frac'] if f'c{i}_frac' in keys else 1.
            colors.append((colorsys.rgb_to_hsv(*rgb), float(fraction or 0.)))
    if not colors and all(k in keys and item_row[k] is not None for k in ('mean_h', 'mean_s', 'mean_v')):
        colors = [(tuple(float(item_row[k]) for k in ('mean_h', 'mean_s', 'mean_v')), 1.)]
    total = sum(w for _, w in colors)
    if total <= 0:
        return 1.
    def distance(hsv, target):
        h, s, v = hsv
        hg = _range_gap(h, target['h'], True) * min(s, target['target'][1])
        sg = _range_gap(s, target['s'])
        vg = _range_gap(v, target['v'])
        return min(1., math.sqrt((2*hg*hg + sg*sg + vg*vg)/4))
    return max(0., min(1., sum(w * min(distance(c, t) for t in targets) for c, w in colors)/total))
