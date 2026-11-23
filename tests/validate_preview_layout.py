"""Media dimensions and Retina scaling must not resize the application layout."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import desktop
from types import SimpleNamespace
from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QStackedWidget
from image_overlay import OverlayImage

app=QApplication([]);window=QWidget();layout=QVBoxLayout(window);stack=QStackedWidget();layout.addWidget(stack)
canvases=[OverlayImage('',SimpleNamespace(pose=None)) for _ in range(2)]
for canvas in canvases:stack.addWidget(canvas)
window.resize(640,480);window.show();app.processEvents();original=window.size();canvas_size=stack.size()
for canvas in canvases:
    stack.setCurrentWidget(canvas)
    for width,height,dpr in ((320,240,1),(3840,2160,1),(2160,3840,2),(7680,4320,2),(640,480,1)):
        canvas.set_native_size(QSize(width,height));pix=QPixmap(width,height);pix.fill();pix.setDevicePixelRatio(dpr)
        canvas.setPixmap(pix);app.processEvents()
        for action in (canvas.fit_image,canvas.actual_size):
            action();app.processEvents()
            assert window.size()==original,(window.size(),original)
            assert stack.size()==canvas_size,(stack.size(),canvas_size)
            assert canvas.minimumSizeHint()==QSize(0,0)
canvas=canvases[-1];canvas.set_native_size(QSize(3840,2160));canvas.preview_limit=720;canvas.actual_size()
assert max(canvas.decode_size().width(),canvas.decode_size().height())<=720
canvas.preview_limit=0;assert canvas.decode_size().width()==3840
import numpy as np
canvas.viewport=SimpleNamespace(pose=np.eye(4),objects=[],points=np.empty((0,6)),mesh=None)
canvas.camera=('PINHOLE',3840,2160,[3000,3000,1920,1080])
def unexpected(*args,**kwargs):raise AssertionError('Empty overlay invoked GPU rendering')
canvas.renderer.render=unexpected;canvas.grab();assert canvas.overlay_error==''
window.close();print('PASS stable preview layout, quality cap, full-resolution inspection and empty-overlay bypass')
