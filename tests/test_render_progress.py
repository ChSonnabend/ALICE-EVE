from alice_renderer.render_progress import sample_percent

def test_progress_uses_samples_and_waits_for_success_before_100():
    assert sample_percent('Fra:1 | Sample 64/128')==50
    assert sample_percent('Rendering 10 / 20 samples')==50
    assert sample_percent('Sample 128/128')==99
    assert sample_percent('ALICE_PROGRESS 0')==0
    assert sample_percent('Building BVH') is None
