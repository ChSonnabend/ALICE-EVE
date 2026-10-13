import os
from alice_renderer import runtime


def test_conda_mesa_override_does_not_hide_system_gpu(tmp_path,monkeypatch):
    prefix=tmp_path/'env';(prefix/'conda-meta').mkdir(parents=True)
    vendor=prefix/'share/glvnd/egl_vendor.d';vendor.mkdir(parents=True)
    monkeypatch.setattr(runtime.sys,'platform','linux')
    monkeypatch.setenv('__EGL_VENDOR_LIBRARY_DIRS',str(vendor))
    assert '__EGL_VENDOR_LIBRARY_DIRS' not in runtime.blender_environment()
    assert os.environ['__EGL_VENDOR_LIBRARY_DIRS']==str(vendor)
    monkeypatch.setenv('__EGL_VENDOR_LIBRARY_DIRS',str(vendor)+os.pathsep+'/custom/vendors')
    assert runtime.blender_environment()['__EGL_VENDOR_LIBRARY_DIRS']=='/custom/vendors'


def test_explicit_nonconda_driver_settings_preserved(monkeypatch):
    monkeypatch.setenv('__EGL_VENDOR_LIBRARY_DIRS','/custom/vendors')
    monkeypatch.setenv('__EGL_VENDOR_LIBRARY_FILENAMES','/custom/driver.json')
    env=runtime.blender_environment()
    assert env['__EGL_VENDOR_LIBRARY_DIRS']=='/custom/vendors'
    assert env['__EGL_VENDOR_LIBRARY_FILENAMES']=='/custom/driver.json'
