"""Embedded OpenGL point-cloud viewer. Z is always the orbit up axis."""
import math
import numpy as np
from PySide6.QtCore import Qt,Signal,QPointF,QRectF
from PySide6.QtGui import QMatrix4x4, QVector3D, QPainter, QColor,QPen,QPolygonF
from PySide6.QtWidgets import QWidget
from scene_geometry import identity_transform,transform_matrix,object_triangles
from manipulation import ray_triangle,axis_parameter,plane_vector,axis_rotation,euler_xyz,segment_distance
import copy
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtOpenGL import QOpenGLFunctions_3_3_Core, QOpenGLShaderProgram, QOpenGLShader, QOpenGLBuffer, QOpenGLVertexArrayObject

from camera_track import WORLD,camera_matrix
from mesh_data import triangle_buffer
from overlay_renderer import primitive_mesh


class AxisGizmo(QWidget):
    def __init__(self,view):
        super().__init__(view);self.view=view;self.setFixedSize(126,126);self.hits=[]
        self.setToolTip('Click ±X / ±Y / ±Z for an orthographic view. Drag the viewport to orbit.')
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.setPen(Qt.NoPen);p.setBrush(QColor(24,32,44,220));p.drawEllipse(4,4,118,118)
        yaw,pitch=np.radians([self.view.yaw,self.view.pitch]);back=np.array([np.cos(pitch)*np.cos(yaw),np.cos(pitch)*np.sin(yaw),np.sin(pitch)])
        right=np.array([-np.sin(yaw),np.cos(yaw),0]);up=np.cross(back,right);center=QPointF(63,63);self.hits=[]
        axes=[]
        for i,(name,color) in enumerate(zip('XYZ',['#ed626b','#71d886','#6aa5ff'])):
            for sign in (-1,1):
                v=np.eye(3)[i]*sign;dx=float(v@right)*43;dy=-float(v@up)*43
                if dx*dx+dy*dy<100:dx=sign*17;dy=0
                axes.append((float(v@back),name,sign,color,QPointF(63+dx,63+dy)))
        for depth,name,sign,color,pt in sorted(axes,key=lambda a:a[0]):
            c=QColor(color);c=c if sign>0 else c.darker(155)
            p.setPen(QPen(c,2));p.drawLine(center,pt);p.setBrush(c);p.drawEllipse(pt,12,12)
            p.setPen(QColor('#ffffff'));p.drawText(QRectF(pt.x()-13,pt.y()-12,26,24),Qt.AlignCenter,('' if sign>0 else '−')+name)
            self.hits.append((pt,name,sign))
        p.end()
    def mousePressEvent(self,event):
        for point,name,sign in reversed(self.hits):
            if (point-event.position()).manhattanLength()<19:self.view.axis_view(name,sign);return


class ManipulatorOverlay(QWidget):
    def __init__(self,view):
        super().__init__(view);self.view=view
        self.setAttribute(Qt.WA_TransparentForMouseEvents);self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet('background: transparent;')
    def paintEvent(self,event):
        v=self.view;painter=QPainter(self);painter.setPen(QColor('#a8bacf'))
        painter.drawText(16,26,'3D SCENE   /   Z UP')
        target='whole scene' if v.selected<0 else v.objects[v.selected]['name']
        action='Click: select · Drag background: orbit' if v.mode=='Orbit' else v.mode+' '+target+' · Drag an axis handle'
        painter.drawText(16,self.height()-16,action+' · Esc: cancel')
        v.draw_manipulator(painter)
        if v.gpu_error:painter.drawText(16,58,'OpenGL error: '+v.gpu_error[:100])
        painter.end()


class Viewport(QOpenGLWidget):
    floor_spacing=1.
    floor_height=0.
    edited=Signal()
    mode_changed=Signal(str)
    def __init__(self):
        super().__init__()
        self.setMinimumSize(320,300)
        self.center = np.zeros(3); self.distance = 12.; self.yaw = -70.; self.pitch = 25.
        self.points = np.empty((0,6),np.float32); self.path = np.empty((0,6),np.float32)
        self.pose = None; self.show_points = True; self.show_path = True
        self.point_size = 2.; self.dirty = True; self.gpu_error = ''; self.ready = False
        self.camera_scale = .3
        self.scene_transform=identity_transform();self.objects=[];self.selected=-1;self.mode='Orbit';self.orthographic=False
        self.manipulator=ManipulatorOverlay(self);self.gizmo=AxisGizmo(self)
        self.setMouseTracking(True);self.setFocusPolicy(Qt.StrongFocus)
        self.view_projection=None;self.handles=[];self.drag=None;self.hover_axis=None
        self.gizmo_space='Global';self.press_point=None;self.press_hit=None;self.orbit_drag=False
        self.cancelled_drag=False
        self.mesh=None;self.mesh_path=None;self.show_mesh=True;self.shading='Vertex color';self.smooth_mesh=True;self._mesh_preview=None;self._mesh_preview_key=None

    def set_mesh(self,mesh):
        self.mesh=mesh;self.mesh_path=mesh.get('path') if mesh else None;self._mesh_preview=None;self._mesh_preview_key=None;self.update()

    def mesh_preview(self):
        key=(id(self.mesh),self.shading,self.smooth_mesh)
        if key!=self._mesh_preview_key:
            self._mesh_preview=triangle_buffer(self.mesh,self.shading,self.smooth_mesh);self._mesh_preview_key=key
        return self._mesh_preview

    def set_mode(self,mode):
        self.mode=mode;self.handles=[];self.update()

    def project(self,point):
        if self.view_projection is None:return None
        clip=self.view_projection@np.append(point,1.)
        if clip[3]<=1e-8:return None
        ndc=clip[:3]/clip[3]
        if ndc[2]<-1 or ndc[2]>1:return None
        return np.array([(ndc[0]+1)*self.width()/2,(1-ndc[1])*self.height()/2,ndc[2]])

    def ray(self,point):
        x,y=(point.x(),point.y()) if hasattr(point,'x') else point[:2]
        inv=np.linalg.inv(self.view_projection);ndc=[2*x/self.width()-1,1-2*y/self.height()]
        a=inv@np.array([*ndc,-1,1]);b=inv@np.array([*ndc,1,1]);a=a[:3]/a[3];b=b[:3]/b[3]
        d=b-a;return a,d/np.linalg.norm(d)

    def pick_object(self,point):
        if self.view_projection is None:return None
        origin,direction=self.ray(point);root=transform_matrix(self.scene_transform);best=(float('inf'),None)
        for index,item in enumerate(self.objects):
            for triangle in object_triangles(item):
                world=triangle@root[:3,:3].T+root[:3,3];hit=ray_triangle(origin,direction,world)
                if hit is not None and hit<best[0]:best=(hit,index)
        return best[1]

    def manipulator_frame(self):
        item=self.active_transform();root=transform_matrix(self.scene_transform)
        if self.selected>=0:
            pivot=root[:3,:3]@np.array(item['position'])+root[:3,3]
            rotation=root[:3,:3]/self.scene_transform['scale']@ (transform_matrix(item)[:3,:3]/item['scale'])
        else:pivot=np.array(item['position']);rotation=root[:3,:3]/item['scale']
        return pivot,(rotation if self.gizmo_space=='Local' else np.eye(3))

    def draw_manipulator(self,painter):
        self.handles=[]
        if self.mode not in ('Move','Rotate') or self.view_projection is None:return
        pivot,basis=self.manipulator_frame();screen=self.project(pivot)
        if screen is None:return
        # Match a fixed screen size in perspective and orthographic views, in logical pixels.
        inv=np.linalg.inv(self.view_projection)
        def unproject(x):
            v=inv@np.array([2*x/self.width()-1,1-2*screen[1]/self.height(),screen[2],1]);return v[:3]/v[3]
        length=max(1e-5,np.linalg.norm(unproject(screen[0]+85)-unproject(screen[0])))
        painter.setRenderHint(QPainter.Antialiasing)
        for index,color in enumerate(['#f06470','#73dc8c','#72adff']):
            axis=basis[:,index];active=self.hover_axis==index or (self.drag and self.drag['axis_index']==index)
            painter.setPen(QPen(QColor('#ffe392') if active else QColor(color),4 if active else 3))
            painter.setBrush(QColor('#ffe392') if active else QColor(color))
            if self.mode=='Move':
                tip=self.project(pivot+axis*length)
                if tip is None or np.linalg.norm(tip[:2]-screen[:2])<14:continue
                a,b=screen[:2],tip[:2];u=(b-a)/np.linalg.norm(b-a);side=np.array([-u[1],u[0]])
                painter.drawLine(QPointF(*a),QPointF(*b))
                painter.drawPolygon(QPolygonF([QPointF(*b),QPointF(*(b-u*14+side*6)),QPointF(*(b-u*14-side*6))]))
                painter.drawText(QPointF(*(b+side*13)),'XYZ'[index])
                self.handles.append(dict(axis_index=index,axis=axis.copy(),pivot=pivot.copy(),a=a+u*13,b=b,length=length))
            else:
                u=basis[:,(index+1)%3];v=basis[:,(index+2)%3];radius=length*.82
                for t0,t1 in zip(np.linspace(0,2*np.pi,97)[:-1],np.linspace(0,2*np.pi,97)[1:]):
                    a=self.project(pivot+radius*(u*math.cos(t0)+v*math.sin(t0)));b=self.project(pivot+radius*(u*math.cos(t1)+v*math.sin(t1)))
                    if a is None or b is None:continue
                    painter.drawLine(QPointF(*a[:2]),QPointF(*b[:2]))
                    self.handles.append(dict(axis_index=index,axis=axis.copy(),pivot=pivot.copy(),a=a[:2],b=b[:2],length=length,tangent=(b[:2]-a[:2])/(t1-t0)))
        painter.setPen(QPen(QColor('#fff1bd'),2));painter.setBrush(QColor('#293544'));painter.drawEllipse(QPointF(*screen[:2]),5,5)

    def handle_at(self,point):
        p=np.array([point.x(),point.y()]);best=None;distance=9.
        for handle in self.handles:
            d,_=segment_distance(p,handle['a'],handle['b'])
            if d<distance:best=handle;distance=d
        return best

    def begin_drag(self,handle,point):
        origin,direction=self.ray(point)
        self.drag=dict(handle,mode=self.mode,item=self.active_transform(),before=copy.deepcopy(self.active_transform()),
                       start=np.array([point.x(),point.y()]),total=0.,parent=transform_matrix(self.scene_transform))
        self.drag['parameter']=axis_parameter(origin,direction,handle['pivot'],handle['axis'])
        self.drag['vector']=plane_vector(origin,direction,handle['pivot'],handle['axis'])
        self.drag['selected']=self.selected;self.setCursor(Qt.ClosedHandCursor)

    def update_drag(self,point):
        d=self.drag;origin,direction=self.ray(point);before=d['before'];item=d['item'];axis=d['axis']
        if d['mode']=='Move':
            parameter=axis_parameter(origin,direction,d['pivot'],axis)
            if parameter is None or d['parameter'] is None:return
            delta=axis*(parameter-d['parameter'])
            if d['selected']>=0:delta=np.linalg.solve(d['parent'][:3,:3],delta)
            item['position']=(np.array(before['position'])+delta).tolist()
        else:
            vector=plane_vector(origin,direction,d['pivot'],axis)
            if vector is not None and d['vector'] is not None:
                d['total']+=math.atan2(float(axis@np.cross(d['vector'],vector)),float(np.clip(d['vector']@vector,-1,1)));d['vector']=vector
            else:
                tangent=d['tangent'];delta=np.array([point.x(),point.y()])-d['start'];d['total']=float(delta@tangent)/max(float(tangent@tangent),1e-5)
            parent=d['parent'][:3,:3]/self.scene_transform['scale'] if d['selected']>=0 else np.eye(3)
            old=transform_matrix(before)[:3,:3]/before['scale']
            item['rotation']=euler_xyz(parent.T@axis_rotation(axis,d['total'])@parent@old)
        self.edited.emit();self.update()

    def resizeEvent(self,event):
        super().resizeEvent(event);self.manipulator.setGeometry(self.rect());self.manipulator.raise_();self.gizmo.move(self.width()-self.gizmo.width()-10,10);self.gizmo.raise_()

    def axis_view(self,axis,sign=1):
        self.yaw,self.pitch={'X':(0 if sign>0 else 180,0),'Y':(90 if sign>0 else -90,0),'Z':(-90,90 if sign>0 else -90)}[axis]
        self.orthographic=True;self.gizmo.update();self.update()

    def active_transform(self):return self.objects[self.selected] if 0<=self.selected<len(self.objects) else self.scene_transform

    def add_primitive(self,kind):
        item=dict(identity_transform(),kind=kind,name=f'{kind} {len(self.objects)+1}',color=[.9,.58,.18] if kind=='Cone' else [.25,.65,.92])
        # Place at the current orbit center in reconstruction coordinates.
        inv=np.linalg.inv(transform_matrix(self.scene_transform));item['position']=(inv[:3,:3]@self.center+inv[:3,3]).tolist()
        item['scale']=max(.05,self.distance*.025)
        self.objects.append(item);self.selected=len(self.objects)-1;self.set_mode('Move');self.mode_changed.emit('Move');self.edited.emit();self.update()
        return item

    def initializeGL(self):
        try:
            self.gl = QOpenGLFunctions_3_3_Core(); self.gl.initializeOpenGLFunctions()
            self.program = QOpenGLShaderProgram()
            vertex = '''#version 330 core
layout(location=0) in vec3 position; layout(location=1) in vec3 color;
uniform mat4 mvp; uniform float size; out vec3 rgb;
void main(){gl_Position=mvp*vec4(position,1);gl_PointSize=size;rgb=color;}'''
            fragment = '''#version 330 core
in vec3 rgb; out vec4 frag; void main(){frag=vec4(rgb,1);}'''
            if not self.program.addShaderFromSourceCode(QOpenGLShader.Vertex, vertex):
                raise RuntimeError(self.program.log())
            if not self.program.addShaderFromSourceCode(QOpenGLShader.Fragment, fragment) or not self.program.link():
                raise RuntimeError(self.program.log())
            self.vao = QOpenGLVertexArrayObject(); self.vao.create()
            self.buffers = {}
            for key in ('points','path','lines','camera','objects','surface'):
                b = QOpenGLBuffer(); b.create(); self.buffers[key] = b
            self.ready = True
            self.context().aboutToBeDestroyed.connect(self.cleanup)
        except Exception as exc:
            self.gpu_error = str(exc)

    def cleanup(self):
        self.makeCurrent()
        for b in getattr(self, 'buffers', {}).values(): b.destroy()
        if hasattr(self,'vao'): self.vao.destroy()
        self.ready = False
        self.doneCurrent()

    def set_model(self, points, poses):
        sample = points[::max(1, math.ceil(len(points)/200000))]
        xyz = np.array([p[0] for p in sample],np.float32).reshape(-1,3) @ WORLD.T
        colors = np.array([p[1] for p in sample],np.float32).reshape(-1,3)
        self.points = np.ascontiguousarray(np.concatenate((xyz,colors),axis=1),np.float32)
        positions = np.array([camera_matrix(p)[:3,3] for p in poses])
        self.path = np.ascontiguousarray(np.column_stack((positions,np.tile([.2,.75,1],(len(poses),1)))),np.float32)
        self.dirty = True
        self.fit()

    def fit(self):
        if len(self.points):
            matrix=transform_matrix(self.scene_transform)
            self.center = matrix[:3,:3]@np.median(self.points[:,:3],axis=0)+matrix[:3,3]
            radius = np.percentile(np.linalg.norm(self.points[:,:3]-np.median(self.points[:,:3],axis=0),axis=1),85)*self.scene_transform['scale']
            self.distance = max(1.,float(radius)*3)
            self.camera_scale = max(.03, float(radius)*.035)
        self.yaw = -70.; self.pitch = 25.; self.orthographic=False;self.gizmo.update();self.update()

    def set_pose(self, pose):
        self.pose = camera_matrix(pose) if pose else None
        self.update()

    def update_camera_path(self,poses):
        self.path[:,:3]=np.array([camera_matrix(p)[:3,3] for p in poses])
        self.dirty=True
        self.update()

    def draw_buffer(self, key, data, mode, upload=True):
        self.vao.bind(); b = self.buffers[key]; b.bind()
        if upload:
            raw = np.ascontiguousarray(data,np.float32).tobytes(); b.allocate(raw,len(raw))
        self.program.enableAttributeArray(0); self.program.enableAttributeArray(1)
        self.program.setAttributeBuffer(0,0x1406,0,3,24)
        self.program.setAttributeBuffer(1,0x1406,12,3,24)
        self.gl.glDrawArrays(mode,0,len(data))
        b.release(); self.vao.release()

    def paintGL(self):
        if self.ready:
            g=self.gl; g.glClearColor(.055,.065,.085,1); g.glClear(0x4000|0x0100)
            g.glEnable(0x0B71); g.glEnable(0x8642)
            yaw,pitch = math.radians(self.yaw),math.radians(self.pitch)
            offset = np.array([math.cos(pitch)*math.cos(yaw), math.cos(pitch)*math.sin(yaw), math.sin(pitch)])*self.distance
            eye = self.center+offset
            view=QMatrix4x4();view.lookAt(QVector3D(*eye),QVector3D(*self.center),QVector3D(0,1 if self.pitch>0 else -1,0) if abs(self.pitch)==90 else QVector3D(0,0,1))
            proj=QMatrix4x4();aspect=max(.1,self.width()/max(1,self.height()))
            if self.orthographic:proj.ortho(-self.distance*.45*aspect,self.distance*.45*aspect,-self.distance*.45,self.distance*.45,.001,max(1000.,self.distance*100))
            else:proj.perspective(48.,aspect,max(.001,self.distance/10000),max(1000.,self.distance*100))
            self.view_projection=np.array((proj*view).copyDataTo(),dtype=float).reshape(4,4)
            self.program.bind(); self.program.setUniformValue(self.program.uniformLocation('mvp'),proj*view)
            g.glUniform1f(self.program.uniformLocation('size'),float(self.point_size*self.devicePixelRatioF()))
            extent = self.floor_spacing
            lines=[]
            def segment(a,b,c): lines.extend([list(a)+list(c),list(b)+list(c)])
            for i in range(-10,11):
                segment((i*extent,-10*extent,self.floor_height),(i*extent,10*extent,self.floor_height),(.16,.19,.23))
                segment((-10*extent,i*extent,self.floor_height),(10*extent,i*extent,self.floor_height),(.16,.19,.23))
            segment((-10*extent,0,self.floor_height),(10*extent,0,self.floor_height),(.95,.3,.3))
            segment((0,-10*extent,self.floor_height),(0,10*extent,self.floor_height),(.3,.85,.45))
            segment((0,0,0),(0,0,extent*3),(.3,.55,1))
            self.draw_buffer('lines',lines,0x0001)
            root=QMatrix4x4(*transform_matrix(self.scene_transform).reshape(-1).tolist())
            self.program.setUniformValue(self.program.uniformLocation('mvp'),proj*view*root)
            if self.show_mesh and self.mesh is not None:
                surface=self.mesh_preview()
                if self.shading!='Wireframe':
                    g.glEnable(0x8037);g.glPolygonOffset(1.,1.);self.draw_buffer('surface',surface,0x0004);g.glDisable(0x8037)
                if self.shading in ('Wireframe','Solid + wire'):
                    g.glPolygonMode(0x0408,0x1B01);self.draw_buffer('surface',surface,0x0004);g.glPolygonMode(0x0408,0x1B02)
            lines=[]
            if self.pose is not None:
                s=self.camera_scale
                local=np.array([[0,0,0],[-s,-s*.6,-s*1.5],[s,-s*.6,-s*1.5],[s,s*.6,-s*1.5],[-s,s*.6,-s*1.5]])
                verts=local@self.pose[:3,:3].T+self.pose[:3,3]
                for a,b in ((0,1),(0,2),(0,3),(0,4),(1,2),(2,3),(3,4),(4,1)):
                    segment(verts[a],verts[b],(1,.7,.2))
            self.draw_buffer('camera',lines,0x0001)
            triangles=[]
            for index,item in enumerate(self.objects):
                data=triangle_buffer(primitive_mesh(item),self.shading,self.smooth_mesh)
                if index==self.selected:data[:,3:]=np.minimum(1,data[:,3:]+.12)
                triangles.append(data)
            if triangles:
                data=np.concatenate(triangles)
                if self.shading!='Wireframe':
                    g.glEnable(0x8037);g.glPolygonOffset(1.,1.);self.draw_buffer('objects',data,0x0004);g.glDisable(0x8037)
                if self.shading in ('Wireframe','Solid + wire'):
                    g.glPolygonMode(0x0408,0x1B01);self.draw_buffer('objects',data,0x0004);g.glPolygonMode(0x0408,0x1B02)
            if self.show_path and len(self.path): self.draw_buffer('path',self.path,0x0003,self.dirty)
            if self.show_points and len(self.points): self.draw_buffer('points',self.points,0x0000,self.dirty)
            # Upload hidden layers too on first use so toggles never reference an empty buffer.
            if self.dirty:
                for key,data in (('path',self.path),('points',self.points)):
                    b=self.buffers[key]; b.bind(); raw=data.tobytes(); b.allocate(raw,len(raw)); b.release()
            self.dirty=False; self.program.release(); g.glDisable(0x0B71)
        self.manipulator.update()

    def mousePressEvent(self,event):
        self.cancelled_drag=False
        self.setFocus();self.last=event.position();self.press_point=event.position();self.orbit_drag=False;self.press_hit=None
        if event.button()==Qt.LeftButton:
            handle=self.handle_at(event.position())
            if handle:self.begin_drag(handle,event.position());return
            self.press_hit=self.pick_object(event.position())
            if self.press_hit is not None:
                self.selected=self.press_hit
                if self.mode=='Orbit':self.set_mode('Move');self.mode_changed.emit('Move')
                self.edited.emit();self.update()
    def mouseMoveEvent(self,event):
        if self.drag:self.update_drag(event.position());return
        if not event.buttons():
            handle=self.handle_at(event.position());self.hover_axis=handle['axis_index'] if handle else None
            self.setCursor(Qt.OpenHandCursor if handle else Qt.ArrowCursor);self.update();return
        delta=event.position()-self.last; self.last=event.position()
        if event.buttons() & Qt.LeftButton and self.press_hit is None:
            if self.press_point is None or (event.position()-self.press_point).manhattanLength()<4:return
            self.orbit_drag=True
            self.orthographic=False
            self.yaw-=delta.x()*.4; self.pitch=max(-89,min(89,self.pitch+delta.y()*.4))
        elif event.buttons() & (Qt.RightButton|Qt.MiddleButton):
            yaw=math.radians(self.yaw); right=np.array([-math.sin(yaw),math.cos(yaw),0])
            self.center += (-right*delta.x()+np.array([0,0,1])*delta.y())*self.distance*.0015
        self.gizmo.update();self.update()
    def mouseReleaseEvent(self,event):
        if self.cancelled_drag:
            self.cancelled_drag=False;self.press_point=None;self.press_hit=None;return
        if self.drag:
            self.update_drag(event.position());self.drag=None;self.unsetCursor();self.update()
        elif event.button()==Qt.LeftButton and not self.orbit_drag and self.press_hit is None:
            self.selected=-1;self.edited.emit();self.update()
        self.press_point=None;self.press_hit=None

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape and self.drag:
            self.drag['item'].update(self.drag['before']);self.drag=None;self.cancelled_drag=True;self.unsetCursor();self.edited.emit();self.update();return
        if not self.drag and event.key() in (Qt.Key_G,Qt.Key_R):
            mode='Move' if event.key()==Qt.Key_G else 'Rotate';self.set_mode(mode);self.mode_changed.emit(mode);return
        super().keyPressEvent(event)
    def wheelEvent(self,event):
        if self.drag:return
        self.distance=max(.01,min(1e7,self.distance*math.exp(-event.angleDelta().y()/120*.12))); self.update()
