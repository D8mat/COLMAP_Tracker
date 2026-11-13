"""Small vector icons drawn at multiple resolutions for the scene inspector."""
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QIcon,QPixmap,QPainter,QPen,QColor,QPainterPath,QPolygonF

_icons={}

def scene_icon(kind):
    if kind in _icons:return _icons[kind]
    icon=QIcon()
    color={'Cube':'#df9457','Cone':'#df9457','Point cloud':'#00c597',
           'Surface mesh':'#00c597','Camera path':'#7cadf0','Load':'#d4b467'}.get(kind,'#d7d7d7')
    for size in (16,20,24,32,48,64):
        pix=QPixmap(size,size);pix.fill(Qt.transparent);p=QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing);p.scale(size/24,size/24)
        p.setPen(QPen(QColor(color),1.6,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));p.setBrush(Qt.NoBrush)
        def line(x,y,a,b):p.drawLine(QPointF(x,y),QPointF(a,b))
        def rect(x,y,w,h):p.drawRect(QRectF(x,y,w,h))
        if kind=='Cube':
            p.drawPolygon(QPolygonF([QPointF(12,2),QPointF(21,7),QPointF(21,17),QPointF(12,22),QPointF(3,17),QPointF(3,7)]))
            line(3,7,12,12);line(12,12,21,7);line(12,12,12,22);line(12,2,12,12)
        elif kind=='Cone':
            p.drawEllipse(QRectF(3,3,18,6));line(3,6,12,22);line(21,6,12,22)
            p.setBrush(QColor(color));p.drawEllipse(QPointF(12,22),1.3,1.3)
        elif kind=='Point cloud':
            p.setBrush(QColor(color))
            for x,y in ((4,7),(11,4),(19,8),(8,12),(15,13),(4,19),(12,20),(21,18)):p.drawEllipse(QPointF(x,y),1.3,1.3)
        elif kind=='Surface mesh':
            p.drawPolygon(QPolygonF([QPointF(2,17),QPointF(8,4),QPointF(18,5),QPointF(22,18),QPointF(10,21)]))
            for a,b,c,d in ((2,17,13,12),(8,4,13,12),(18,5,13,12),(22,18,13,12),(10,21,13,12)):line(a,b,c,d)
        elif kind=='Camera path':
            rect(3,6,12,10);p.drawPolygon(QPolygonF([QPointF(15,9),QPointF(21,6),QPointF(21,17),QPointF(15,14)]));line(6,20,15,20)
        elif kind=='Whole scene':
            rect(9,2,6,5);line(12,7,12,12);line(5,12,19,12);line(5,12,5,16);line(19,12,19,16);rect(2,16,6,5);rect(16,16,6,5)
        elif kind=='Show':
            path=QPainterPath(QPointF(2,12));path.quadTo(12,0,22,12);path.quadTo(12,24,2,12);p.drawPath(path);p.drawEllipse(QPointF(12,12),3,3)
        elif kind=='Lock':
            rect(5,10,14,11);p.drawArc(QRectF(8,2,8,14),0,180*16);line(12,14,12,17)
        elif kind=='Duplicate':rect(3,3,13,13);rect(8,8,13,13)
        elif kind=='Rename':
            p.drawPolygon(QPolygonF([QPointF(4,16),QPointF(16,4),QPointF(20,8),QPointF(8,20),QPointF(3,21)]));line(14,6,18,10)
        elif kind=='Frame':
            for x,y,sx,sy in ((3,3,1,1),(21,3,-1,1),(3,21,1,-1),(21,21,-1,-1)):
                line(x,y,x+sx*5,y);line(x,y,x,y+sy*5)
            p.drawEllipse(QPointF(12,12),3,3)
        elif kind=='Remove':rect(6,7,12,14);line(4,7,20,7);line(9,3,15,3);line(10,11,10,17);line(14,11,14,17)
        elif kind=='Reset':p.drawArc(QRectF(4,4,16,16),-40*16,290*16);line(3,3,3,9);line(3,9,9,9)
        elif kind=='Save':rect(3,3,18,18);rect(7,3,10,7);rect(7,15,10,6)
        elif kind=='Load':
            p.drawPolygon(QPolygonF([QPointF(3,20),QPointF(3,4),QPointF(10,4),QPointF(13,7),QPointF(21,7),QPointF(21,20)]));line(3,11,21,11)
        p.end();icon.addPixmap(pix)
    _icons[kind]=icon
    return icon
