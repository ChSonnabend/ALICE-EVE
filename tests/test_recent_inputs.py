from alice_renderer.scene_library import SceneLibrary


def test_recent_inputs_persist_deduplicate_and_limit(tmp_path):
    lib=SceneLibrary(tmp_path/'library.sqlite')
    for i in range(15):lib.remember_input(tmp_path/f'data-{i}')
    assert len(lib.recent_inputs())==12
    lib.remember_input(tmp_path/'data-5')
    paths=SceneLibrary(lib.path).recent_inputs()
    assert paths[0]==str(tmp_path/'data-5')
    assert len(paths)==len(set(paths))==12
    lib.clear_recent_inputs()
    assert lib.recent_inputs()==[]
