import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
"""Rendered signed XYZ curves, axis isolation, selection and cache invalidation."""
import sys
from pathlib import Path
import numpy as np
import desktop
from PySide6.QtCore import Qt,QPointF,QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from camera_editor import CameraEditor
from test_camera_track import pose_from_matrix,matrix
from ui_theme import STYLE

app=QApplication([]);e=CameraEditor();e.setStyleSheet(STYLE);e.resize(1100,480);e.show()
poses=[pose_from_matrix(i,matrix(p)) for i,p in enumerate(([0,0,0],[1,-2,3],[3,-6,9],[6,-12,18]),1)]
e.set_track(poses);selected=[];e.selected.connect(selected.append)

def pixels():
    image=e.graph.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
    return np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width(),:3].copy()

def color_counts(data):
    return [int(np.count_nonzero(np.linalg.norm(data.astype(float)-rgb,axis=2)<25)) for rgb in ([240,48,77],[129,205,0],[47,117,189])]

def run():
    try:
        assert e.channel.currentText()=='Translation XYZ' and e.graph.channel==3
        data=pixels();assert all(n>50 for n in color_counts(data)),color_counts(data)
        key=e.graph.plot_cache.cacheKey();e.set_frame(2);pixels();assert e.graph.plot_cache.cacheKey()==key
        for axis in range(3):
            e.axis_filter.setCurrentIndex(axis+1);data=pixels();counts=color_counts(data)
            assert counts[axis]>50 and all(n==0 for i,n in enumerate(counts) if i!=axis),counts
        e.axis_filter.setCurrentIndex(0);e.channel.setCurrentIndex(3);pixels()
        assert e.graph.channel==1 and not e.axis_filter.isEnabled()
        e.channel.setCurrentIndex(1);assert e.axis_filter.isEnabled()
        data=pixels();key=e.graph.plot_cache.cacheKey();e.track.set_matrix(2,matrix([1,-5,3]));e.notify();changed=pixels()
        assert e.graph.plot_cache.cacheKey()!=key and not np.array_equal(data,changed)
        rect=e.graph.plot_rect();QTest.mouseClick(e.graph,Qt.LeftButton,pos=QPointF(rect.left()+rect.width()*2/3,rect.center().y()).toPoint())
        assert selected[-1]==3
        folder=desktop.ROOT/'validation/translation_graph';folder.mkdir(parents=True,exist_ok=True)
        e.grab().save(str(folder/'translation_xyz.png'));e.close()
        print('PASS signed XYZ raster curves, per-axis isolation, total fallback, frame selection and graph cache invalidation',flush=True);app.exit(0)
    except Exception:
        import traceback;traceback.print_exc();app.exit(1)

QTimer.singleShot(100,run);sys.exit(app.exec())
