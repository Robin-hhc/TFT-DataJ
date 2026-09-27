"""DataJ dark placement gradient, verified against public hex page 2026-09-27.

Good 4.0, bad 4.8; linear RGB interpolation with floor, same displayed rule.
"""
import math

def placement_color(value):
    pct=max(-1.0,min(1.0,2*(float(value)-4.0)/(.8)-1))
    start,end=((191,254,127),(255,223,128)) if pct<0 else ((255,223,128),(255,90,100))
    factor=pct+1 if pct<0 else pct
    rgb=[math.floor(a+(b-a)*factor) for a,b in zip(start,end)]
    return 'rgb('+','.join(map(str,rgb))+')'
