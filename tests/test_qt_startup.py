"""Exercise the entry point in a fresh process, before Qt is initialized."""
import os
import subprocess
import sys


def test_entry_point_initializes_qt_without_plugin_path_workaround(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    env.pop('QT_QPA_PLATFORM_PLUGIN_PATH', None)
    env.pop('QT_PLUGIN_PATH', None)
    result = subprocess.run(
        [sys.executable, '-c', '''
from pathlib import Path
import sys
from alice_renderer import app
app.ROOT = Path(sys.argv[1])
original = app.QApplication
class TimedApplication(original):
    def __init__(self, *args):
        super().__init__(*args)
        app.QTimer.singleShot(100, self.quit)
app.QApplication = TimedApplication
raise SystemExit(app.main())
''', str(tmp_path)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
