"""Linear resolution scaling inside the UHD 8K canvas, retaining scene aspect."""
import math

MAX_WIDTH=7680
MAX_HEIGHT=4320
PRESET_PERCENT={'draft':100/12,'balanced':25.,'final':50.,'publication':100.,'custom':25.}

def maximum_size(aspect):
    if not math.isfinite(aspect) or aspect<=0:raise ValueError('Invalid frame aspect')
    return (MAX_WIDTH,round(MAX_WIDTH/aspect)) if aspect>=MAX_WIDTH/MAX_HEIGHT else (round(MAX_HEIGHT*aspect),MAX_HEIGHT)

def minimum_percent(aspect):return max(1.,100*64/min(maximum_size(aspect)))

def percentage_size(percent,aspect):
    if not math.isfinite(percent) or not 0<percent<=100:raise ValueError('Resolution percentage must be above 0 and at most 100')
    w,h=maximum_size(aspect);factor=max(percent,minimum_percent(aspect))/100
    return max(64,round(w*factor)),max(64,round(h*factor))
