"""Image canvas: one transform for video, grid, geometry and loupe."""
import math
from PySide6.QtCore import Qt,QPointF,QRectF,QSize,Signal
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import QLabel
from scene_geometry import transform_matrix
from floor_grid import project_floor
from overlay_renderer import CalibratedRenderer
from reprojection_overlay import ReprojectionOverlay


class OverlayImage(QLabel):
    view_changed=Signal()
    def __init__(self,text,viewport):
        super().__init__(text);self.viewport=viewport;self.camera=None;self.enabled_overlay=True;self.opacity=.65
        self.enabled_grid=False;self.enabled_points=False;self.enabled_mesh=False
        self.cloud_size=3.;self.cloud_color='RGB';self.renderer=CalibratedRenderer();self.overlay_error=''
        self.reprojection=ReprojectionOverlay()
        self.native_size=QSize();self.zoom=None;self.pan=QPointF();self.pan_start=None;self.loupe=False;self.hide_overlays=False;self.cursor_point=None
        self.setMouseTracking(True);self.setToolTip('Wheel: zoom at cursor · Middle/right drag: pan · Fit / 100% in toolbar')

    def set_native_size(self,size):self.native_size=QSize(size)

    def scale_factor(self):
        size=self.native_size
        if not size.isValid():return 1.
        return self.zoom if self.zoom is not None else min(self.width()/size.width(),self.height()/size.height())

    def image_rect(self):
        size=self.native_size if self.native_size.isValid() else (self.pixmap().size() if self.pixmap() else QSize(1,1))
        width,height=size.width()*self.scale_factor(),size.height()*self.scale_factor()
        return QRectF((self.width()-width)/2+self.pan.x(),(self.height()-height)/2+self.pan.y(),width,height)

    def decode_size(self):
        if not self.native_size.isValid():return self.size()
        scale=max(self.scale_factor()*self.devicePixelRatioF(),1. if self.loupe else 0.)
        return self.native_size*min(1.,scale)

    def fit_image(self):
        self.zoom=None;self.pan=QPointF();self.view_changed.emit();self.update()

    def actual_size(self):
        self.zoom=1./self.devicePixelRatioF();self.pan=QPointF();self.view_changed.emit();self.update()

    def wheelEvent(self,event):
        if not self.native_size.isValid():return
        anchor=event.position();center=QPointF(self.width()/2,self.height()/2);old=self.scale_factor()
        self.zoom=max(.02,min(8.,old*math.exp(event.angleDelta().y()/120*.15)))
        self.pan=anchor-center-(anchor-center-self.pan)*(self.zoom/old)
        self.view_changed.emit();self.update();event.accept()

    def mousePressEvent(self,event):
        if event.button() in (Qt.MiddleButton,Qt.RightButton):self.pan_start=event.position();self.setCursor(Qt.ClosedHandCursor)
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        self.cursor_point=event.position()
        if self.pan_start is not None:self.pan+=event.position()-self.pan_start;self.pan_start=event.position()
        self.update()

    def mouseReleaseEvent(self,event):self.pan_start=None;self.unsetCursor()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.zoom is None:self.view_changed.emit()

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#171717'));pix=self.pixmap()
        if pix is None or pix.isNull():
            painter.setPen(QColor('#d7d7d7'));painter.drawText(self.rect(),Qt.AlignCenter|Qt.TextWordWrap,self.text());painter.end();return
        rect=self.image_rect();overlay=None;grid=None
        if not self.hide_overlays:self.reprojection.prepare(self.camera,self.viewport.pose,rect)
        if not self.hide_overlays and self.camera is not None and self.viewport.pose is not None:
            if self.enabled_overlay or self.enabled_points or self.enabled_mesh:
                try:
                    # Bound the distortion-map allocation when inspecting a full-resolution image.
                    render_size=pix.size().scaled(QSize(1600,1600),Qt.KeepAspectRatio) if max(pix.width(),pix.height())>1600 else pix.size()
                    overlay=self.renderer.render(self.viewport,self.camera,render_size,points=self.enabled_points,mesh=self.enabled_mesh,objects=self.enabled_overlay,point_size=self.cloud_size,point_color=self.cloud_color);self.overlay_error=''
                except Exception as exc:self.overlay_error=str(exc)
            if self.enabled_grid:grid=project_floor(transform_matrix(self.viewport.scene_transform)@self.viewport.pose,self.camera,self.viewport.floor_spacing,self.viewport.floor_height)
        def draw_content():
            painter.save();painter.setClipRect(rect,Qt.IntersectClip);painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(rect,pix,QRectF(pix.rect()))
            if grid is not None:
                for segment,axis in zip(*grid):
                    painter.setPen(QPen(QColor(155,177,202,130) if axis==0 else QColor('#f0304d' if axis==1 else '#81cd00'),1 if axis==0 else 1.6))
                    a,b=segment;painter.drawLine(QPointF(rect.left()+a[0]*rect.width(),rect.top()+a[1]*rect.height()),QPointF(rect.left()+b[0]*rect.width(),rect.top()+b[1]*rect.height()))
            if overlay is not None:painter.setOpacity(self.opacity);painter.drawImage(rect,overlay);painter.setOpacity(1.)
            if not self.hide_overlays:self.reprojection.draw(painter,rect)
            painter.restore()
        draw_content()
        if self.loupe and self.cursor_point is not None and rect.contains(self.cursor_point):
            lens=QRectF(self.width()-162,12,150,150);painter.save();painter.setClipRect(lens);painter.fillRect(lens,QColor('#171717'))
            painter.translate(lens.center());painter.scale(3,3);painter.translate(-self.cursor_point);draw_content();painter.restore()
            painter.setPen(QPen(QColor('#7cadf0'),2));painter.drawRect(lens)
        if self.overlay_error:
            painter.setPen(QColor('#d7d7d7'));painter.drawText(self.rect().adjusted(8,8,-8,-8),Qt.TextWordWrap,'Overlay: '+self.overlay_error)
        if not self.hide_overlays:self.reprojection.legend(painter,self.rect())
        painter.end()
