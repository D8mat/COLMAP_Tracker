import numpy as np
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QPainter,QColor,QPen,QPolygonF
from PySide6.QtWidgets import QLabel
from scene_geometry import object_triangles,clip_near,project_camera


class OverlayImage(QLabel):
    def __init__(self,text,viewport):
        super().__init__(text);self.viewport=viewport;self.camera=None;self.enabled_overlay=True;self.opacity=.65
    def paintEvent(self,event):
        super().paintEvent(event)
        pix=self.pixmap()
        if not self.enabled_overlay or pix is None or pix.isNull() or self.camera is None or self.viewport.pose is None:return
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        width=pix.width()/pix.devicePixelRatio();height=pix.height()/pix.devicePixelRatio()
        left=(self.width()-width)/2;top=(self.height()-height)/2
        painter.setClipRect(QRectF(left,top,width,height))
        # Scene transform is common to the camera and objects, so cancels in projection.
        inv=np.linalg.inv(self.viewport.pose);polys=[]
        for index,item in enumerate(self.viewport.objects):
            for triangle in object_triangles(item):
                cv=triangle@inv[:3,:3].T+inv[:3,3];cv*=np.array([1,-1,-1])
                polygon=clip_near(cv)
                if len(polygon)<3:continue
                uv=project_camera(polygon,self.camera)
                if not np.isfinite(uv).all():continue
                pts=[QPointF(left+float(x)*width/self.camera[1],top+float(y)*height/self.camera[2]) for x,y in uv]
                polys.append((float(np.mean(polygon[:,2])),QPolygonF(pts),item,index))
        for _,poly,item,index in sorted(polys,key=lambda p:-p[0]):
            color=QColor.fromRgbF(*item['color']);color.setAlphaF(self.opacity)
            painter.setBrush(color);painter.setPen(QPen(QColor('#fff1b0') if index==self.viewport.selected else color.darker(135),1))
            painter.drawPolygon(poly)
        painter.end()
