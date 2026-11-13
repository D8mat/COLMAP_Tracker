"""Cached error paths drawn with the same image rectangle as video/grid/geometry."""
import numpy as np
from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QPainterPath,QColor,QPen,QPainter
from reprojection import ResidualCache,display_indices


class ReprojectionOverlay:
    def __init__(self):
        self.tracks=None;self.frame=None;self.enabled=False;self.original=False
        self.minimum=0.;self.limit=1000;self.source=False
        self.cache=ResidualCache();self.path_key=None;self.paths=[];self.message=''

    def clear(self):
        self.tracks=None;self.frame=None;self.cache.clear();self.path_key=None;self.paths=[];self.message=''

    def prepare(self,camera,pose,rect):
        self.message=''
        if not self.enabled:self.paths=[];self.path_key=None;return
        if self.source:
            self.message='Track error: use Solved frames for measured observations.';self.paths=[];self.path_key=None;return
        if self.tracks is None or self.frame not in self.tracks.image_by_frame or camera is None or pose is None:
            self.message='Track error: no measured data for this frame.';self.paths=[];self.path_key=None;return
        try:
            result=self.cache.get(self.tracks,self.frame,camera,pose,self.original)
            key=(self.cache.key,rect.width(),rect.height(),self.minimum,self.limit)
            if key!=self.path_key:
                indices=display_indices(result,self.minimum,self.limit);self.marker_count=len(indices)
                sx,sy=rect.width()/camera[1],rect.height()/camera[2]
                measured=result.measured[indices]*[sx,sy];projected=result.projected[indices]*[sx,sy]
                errors=result.errors[indices];self.paths=[]
                safe=(np.abs(measured).max(axis=1)<1e6)&(np.abs(projected).max(axis=1)<1e6)
                self.outside_draw=int(np.count_nonzero(~safe));self.marker_count-=self.outside_draw
                for color,mask in (('#81cd00',errors<=1),('#edba18',(errors>1)&(errors<=3)),('#f0304d',errors>3)):
                    rows=np.flatnonzero(mask&safe)
                    # Keep strokes small: one huge overlapping path is expensive
                    # for Qt's antialiased raster stroker.
                    for start in range(0,len(rows),32):
                        path=QPainterPath()
                        for row in rows[start:start+32]:
                            a,b=measured[row],projected[row]
                            path.moveTo(QPointF(*a));path.lineTo(QPointF(*b))
                            path.addEllipse(QRectF(a[0]-3,a[1]-3,6,6))
                            path.moveTo(b[0]-3,b[1]-3);path.lineTo(b[0]+3,b[1]+3)
                            path.moveTo(b[0]-3,b[1]+3);path.lineTo(b[0]+3,b[1]-3)
                        self.paths.append((color,path))
                self.path_key=key
            mode='original solve' if self.original else 'current camera'
            self.message=f'Track error · {mode} · {self.marker_count:,}/{len(result.errors):,} markers (highest errors)'
            if result.unprojectable:self.message+=f' · {result.unprojectable:,} not projectable'
            if self.outside_draw:self.message+=f' · {self.outside_draw:,} beyond drawing range'
        except (ValueError,KeyError,np.linalg.LinAlgError) as exc:
            self.paths=[];self.path_key=None;self.message='Track error unavailable: '+str(exc)

    def draw(self,painter,rect):
        if not self.enabled:return
        painter.save();painter.translate(rect.topLeft());painter.setRenderHint(QPainter.Antialiasing);painter.setBrush(Qt.NoBrush)
        for color,path in self.paths:
            painter.setPen(QPen(QColor(color),1.2));painter.drawPath(path)
        painter.restore()

    def legend(self,painter,bounds):
        if not self.enabled or not self.message:return
        text=self.message
        if not self.source and self.paths:text+='\n○ measured  × projected · green ≤1 · yellow ≤3 · red >3 px (model image)'
        rect=bounds.adjusted(8,8,-8,-8)
        box=painter.boundingRect(rect,Qt.TextWordWrap,text).adjusted(-4,-3,4,3)
        painter.fillRect(box,QColor(20,20,20,225));painter.setPen(QColor('#e6e6e6'))
        painter.drawText(rect,Qt.TextWordWrap,text)
