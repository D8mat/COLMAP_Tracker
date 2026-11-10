from PySide6.QtCore import Qt,QPointF,QRectF,QSize
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import QLabel
from scene_geometry import transform_matrix
from floor_grid import project_floor
from overlay_renderer import CalibratedRenderer


class OverlayImage(QLabel):
    def __init__(self,text,viewport):
        super().__init__(text);self.viewport=viewport;self.camera=None;self.enabled_overlay=True;self.opacity=.65
        self.enabled_grid=False;self.enabled_points=False;self.enabled_mesh=False
        self.cloud_size=3.;self.cloud_color='RGB';self.renderer=CalibratedRenderer();self.overlay_error=''
    def paintEvent(self,event):
        super().paintEvent(event)
        pix=self.pixmap()
        if not (self.enabled_overlay or self.enabled_grid or self.enabled_points or self.enabled_mesh) or pix is None or pix.isNull() or self.camera is None or self.viewport.pose is None:return
        overlay=None
        if self.enabled_overlay or self.enabled_points or self.enabled_mesh:
            try:
                overlay=self.renderer.render(self.viewport,self.camera,QSize(pix.width(),pix.height()),
                    points=self.enabled_points,mesh=self.enabled_mesh,objects=self.enabled_overlay,
                    point_size=self.cloud_size*pix.devicePixelRatio(),point_color=self.cloud_color)
                self.overlay_error=''
            except Exception as exc:self.overlay_error=str(exc)
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        width=pix.width()/pix.devicePixelRatio();height=pix.height()/pix.devicePixelRatio()
        left=(self.width()-width)/2;top=(self.height()-height)/2
        painter.setClipRect(QRectF(left,top,width,height))
        if self.enabled_grid:
            # Floor is world Z=height, matching the 3D viewport, outside the scene root.
            segments,axes=project_floor(transform_matrix(self.viewport.scene_transform)@self.viewport.pose,self.camera,self.viewport.floor_spacing,self.viewport.floor_height)
            for segment,axis in zip(segments,axes):
                painter.setPen(QPen(QColor(155,177,202,130) if axis==0 else QColor('#ed626b' if axis==1 else '#71d886'),1 if axis==0 else 1.6))
                a,b=segment
                painter.drawLine(QPointF(left+a[0]*width,top+a[1]*height),QPointF(left+b[0]*width,top+b[1]*height))
        if overlay is not None:
            painter.setOpacity(self.opacity);painter.drawImage(QRectF(left,top,width,height),overlay);painter.setOpacity(1.)
        if self.overlay_error:
            painter.setPen(QColor('#ff7b7b'));painter.drawText(QRectF(left+8,top+8,width-16,height-16),Qt.TextWordWrap,'Overlay: '+self.overlay_error)
        painter.end()
