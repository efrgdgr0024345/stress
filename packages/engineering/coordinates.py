"""Explicit engineering axes; page coordinates and unlabelled values are rejected."""
from decimal import localcontext
import re
from packages.engineering import dimension_mm

DIRECTIONS={'E':('X',1),'EAST':('X',1),'EASTING':('X',1),
            'W':('X',-1),'WEST':('X',-1),'WESTING':('X',-1),
            'N':('Y',1),'NORTH':('Y',1),'NORTHING':('Y',1),
            'S':('Y',-1),'SOUTH':('Y',-1),'SOUTHING':('Y',-1),
            'EL':('Z',1),'ELEV':('Z',1),'ELEVATION':('Z',1),'Z':('Z',1),
            'X':('X',1),'Y':('Y',1)}


def coordinate_value(source,axis=None,source_format='STANDARD'):
    """E/N/EL are positive; W/S are their opposite signed directions.

    A signed magnitude is algebraic: S -2 in is +50.8 mm North. The
    original direction and signed text are retained rather than normalized away.
    Explicit units are required for both prefixed and ordinary axis inputs.
    """
    match=re.fullmatch(r'\s*([A-Za-z]+)\.?\s*[:=]?\s*([+-]?\s*\d.*)\s*',source)
    direction=match[1].upper() if match else None
    if direction and direction not in DIRECTIONS:raise ValueError('Unknown engineering direction. Use E/W, N/S or EL with explicit units.')
    selected,sign=DIRECTIONS[direction] if direction else (axis,1)
    if selected not in ('X','Y','Z'):raise ValueError('Select an explicit engineering axis.')
    if axis and selected!=axis:raise ValueError('Source direction conflicts with the selected engineering axis.')
    raw=match[2] if match else source
    if source_format=='ISO_FT_IN_DOT_FRACTION':
        # This interpretation is explicitly selected by the engineer. A dot
        # separator is not silently treated as a fraction in standard input.
        printed=raw.strip().replace('′',"'").replace('″','"')
        fraction=re.fullmatch(r'([+-]?\s*\d+)\s*\'\s*(\d+)\.(\d+)/(\d+)\s*"',printed)
        if not fraction:raise ValueError('Selected ISO format requires explicit feet and inch fractions such as 3\'10.3/8".')
        feet,inches,numerator,denominator=fraction.groups()
        if int(denominator)==0 or not 0<=int(inches)<12 or not 0<int(numerator)<int(denominator):
            raise ValueError('ISO inch/fraction fields are invalid; source values were not normalized by guessing.')
        raw=f'{feet}\' {inches} {numerator}/{denominator}"'
    elif source_format!='STANDARD':raise ValueError('Unsupported source dimension convention.')
    with localcontext() as context:
        context.prec=50
        value=dimension_mm(raw)*sign
    return {'axis':selected,'value_mm':str(value),'source_text':source,'source_direction':direction,'source_format':source_format}
