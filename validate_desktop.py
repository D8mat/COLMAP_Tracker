import sys,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import desktop
from PySide6.QtCore import QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication
fmt=QSurfaceFormat(); fmt.setVersion(3,3); fmt.setProfile(QSurfaceFormat.CoreProfile); fmt.setDepthBufferSize(24); QSurfaceFormat.setDefaultFormat(fmt)
print('creating app',flush=True)
app=QApplication([])
print('creating window',flush=True)
window=desktop.Window()
print('showing window',flush=True)
window.show()
print('shown',flush=True)
deadline=time.monotonic()+60
def check():
    if window.loader is not None or not window.poses:
        if time.monotonic()>deadline: print('LOAD TIMEOUT',flush=True); app.exit(1); return
        QTimer.singleShot(200,check); return
    try:
        assert len(window.poses)==1349
        assert window.viewport.ready,window.viewport.gpu_error
        assert window.viewport.isValid()
        assert not window.image.pixmap().isNull()
        window.slider.setValue(600)
        assert window.frame==600
        assert window.viewport.pose is not None
        window.viewport.grabFramebuffer().save(str(desktop.ROOT/'desktop_viewport.png'))
        window.grab().save(str(desktop.ROOT/'desktop_preview.png'))
        window.toggle_points(False); window.toggle_path(False); window.viewport.grabFramebuffer()
        window.toggle_points(True); window.toggle_path(True)
        print('PASS: standalone OpenGL, 1349 poses, Z-up, frame 600 image and camera, point/path toggles.',flush=True)
        window.project.mark_saved(); window.close(); app.exit(0)
    except Exception:
        import traceback; traceback.print_exc(); app.exit(1)
def check_startup():
    try:
        assert window.loader is None and window.model_folder is None
        assert not window.poses and not window.video.text() and not len(window.viewport.points)
        assert not window.viewport.objects and window.viewport.mesh is None
        assert window.project.path is None and window.project.signature()==window.project.baseline
        print('PASS: empty startup with a configured sample; sample requires an explicit click.',flush=True)
        window.sample_button.click()
        QTimer.singleShot(200,check)
    except Exception:
        import traceback;traceback.print_exc();app.exit(1)
QTimer.singleShot(700,check_startup)
sys.exit(app.exec())
