import pytest
from alice_renderer.resolution import percentage_size
from alice_renderer.scene_config import quality_settings
from alice_renderer.model import RenderSettings

@pytest.mark.parametrize('percent,size',[(25,(1920,1080)),(50,(3840,2160)),(100,(7680,4320))])
def test_uhd_milestones(percent,size):
    cfg=quality_settings(RenderSettings(frame_aspect=16/9),'balanced',resolution_percent=percent)
    assert (cfg.width,cfg.height)==size and cfg.samples==128

@pytest.mark.parametrize('aspect',[.05,.75,1,4/3,16/9,2,20])
def test_percentage_preserves_aspect_inside_8k_canvas(aspect):
    w,h=percentage_size(100,aspect);assert w<=7680 and h<=4320
    assert abs(w/h-aspect)<=1/h
    w,h=percentage_size(1,aspect);assert min(w,h)>=64 and w<=7680 and h<=4320

def test_percent_validation_and_no_conflicting_dimensions():
    for value in (0,101,float('nan')):
        with pytest.raises(ValueError):percentage_size(value,16/9)
    with pytest.raises(ValueError):quality_settings(RenderSettings(),resolution_percent=50,width=640)
