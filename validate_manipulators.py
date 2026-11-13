import sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import desktop,numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QSurfaceFormat,QMouseEvent
from PySide6.QtCore import Qt,QPointF,QTimer,QEvent
from PySide6.QtTest import QTest
from scene_geometry import transform_matrix
from manipulation import axis_rotation
f=QSurfaceFormat();f.setVersion(3,3);f.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(f)
app=QApplication([]);v=desktop.Viewport();v.resize(1000,700);v.show()
def repaint():app.processEvents();v.grabFramebuffer();v.manipulator.repaint()
def drag(a,b,cancel=False):
    QTest.mousePress(v,Qt.LeftButton,pos=QPointF(*a).toPoint())
    assert v.drag is not None,'Gizmo not hit'
    event=QMouseEvent(QEvent.MouseMove,QPointF(*b),QPointF(*b),Qt.NoButton,Qt.LeftButton,Qt.NoModifier);app.sendEvent(v,event)
    if cancel:QTest.keyClick(v,Qt.Key_Escape)
    QTest.mouseRelease(v,Qt.LeftButton,pos=QPointF(*b).toPoint());repaint()
def check():
    try:
        v.center[:]=0;v.distance=10;cube=v.add_primitive('Cube');cube['position']=[0.,0.,0.];cube['scale']=.6
        cone=v.add_primitive('Cone');cone['position']=[2.,0.,0.];cone['scale']=.6
        v.set_mode('Orbit');v.selected=-1;repaint()
        point=v.project([0,0,0])[:2];QTest.mouseClick(v,Qt.LeftButton,pos=QPointF(*point).toPoint());repaint();assert v.selected==0
        assert v.mode=='Move'
        # Every visible translation axis changes only its designated world coordinate.
        for axis in range(3):
            repaint();handle=next(h for h in v.handles if h['axis_index']==axis);a=handle['a']*.35+handle['b']*.65
            u=handle['b']-handle['a'];u/=np.linalg.norm(u);before=np.array(cube['position']);drag(a,a+u*40)
            delta=np.array(cube['position'])-before;assert abs(delta[axis])>.01;assert np.linalg.norm(np.delete(delta,axis))<1e-6,delta
        handle=v.handles[0];a=(handle['a']+handle['b'])/2;before=copy.deepcopy(cube);drag(a,a+[25,15],cancel=True);assert cube==before
        # Rotation ring on a face-on Z view: exact quarter turn about the object's origin.
        cube.update(position=[0.,0.,0.],rotation=[0.,0.,0.]);v.center[:]=0;v.axis_view('Z');v.set_mode('Rotate');repaint()
        pivot=v.project([0,0,0])[:2]
        ring=next(h for h in v.handles if h['axis_index']==2 and np.min(np.abs(h['a']-pivot))>25)
        a=(ring['a']+ring['b'])/2;offset=a-pivot;b=pivot+np.array([-offset[1],offset[0]])
        drag(a,b);rotation=transform_matrix(cube)[:3,:3]/cube['scale'];assert abs(rotation[2,2]-1)<1e-5;assert abs(rotation[0,0])<.04,rotation
        # A transformed/scaled parent still allows accurate picking and global-axis movement.
        v.scene_transform=dict(position=[1.,2.,.5],rotation=[15.,20.,35.],scale=2.);root=transform_matrix(v.scene_transform)
        cone_world=root[:3,:3]@np.array(cone['position'])+root[:3,3];v.center=cone_world.copy();v.yaw=-70;v.pitch=25;v.orthographic=False;v.distance=18;v.set_mode('Orbit');repaint()
        click=v.project(root[:3,:3]@(np.array(cone['position'])+np.array([0,0,.8]))+root[:3,3])[:2]
        QTest.mouseClick(v,Qt.LeftButton,pos=QPointF(*click).toPoint());repaint();assert v.selected==1
        handle=next(h for h in v.handles if h['axis_index']==0);a=(handle['a']+handle['b'])/2;u=handle['b']-handle['a'];u/=np.linalg.norm(u);before=np.array(cone['position']);drag(a,a+u*30)
        delta=root[:3,:3]@(np.array(cone['position'])-before);assert abs(delta[0])>.1 and np.linalg.norm(delta[1:])<1e-5
        # Local arrows follow the rotated parent/object, and tip is the gizmo pivot.
        v.gizmo_space='Local';repaint();pivot,basis=v.manipulator_frame();assert np.allclose(pivot,root[:3,:3]@np.array(cone['position'])+root[:3,3])
        assert np.allclose(basis.T@basis,np.eye(3))
        v.grab().save(str(desktop.ROOT/'manipulators_preview.png'))
        # Nearest visible surface wins when objects overlap in screen space.
        v.scene_transform=dict(position=[0.,0.,0.],rotation=[0.,0.,0.],scale=1.)
        cube.update(position=[0.,0.,0.],rotation=[0.,0.,0.],scale=.6)
        cone.update(position=[8.,0.,0.]);near=v.add_primitive('Cube');near.update(position=[0.,0.,3.],scale=.6)
        v.center[:]=0;v.distance=10;v.axis_view('Z');v.set_mode('Orbit');repaint()
        assert v.pick_object(QPointF(*v.project([0,0,0])[:2]))==2
        # Rotation around each global axis, not only Z, remains axis constrained.
        v.selected=0;near['position']=[8.,8.,0.]
        for index,axis in enumerate('XYZ'):
            cube['rotation']=[0.,0.,0.];v.axis_view(axis);v.set_mode('Rotate');repaint()
            pivot=v.project([0,0,0])[:2]
            ring=next(h for h in v.handles if h['axis_index']==index and np.min(np.abs(h['a']-pivot))>25)
            a=(ring['a']+ring['b'])/2;offset=a-pivot;b=pivot+np.array([-offset[1],offset[0]])
            drag(a,b);matrix=transform_matrix(cube)[:3,:3]/cube['scale']
            assert np.allclose(matrix@np.eye(3)[:,index],np.eye(3)[:,index],atol=1e-5)
            assert abs(np.trace(matrix)-1)<.08
        # Uniform scaling preserves the object's origin and works for the complete scene.
        for key,mode in ((Qt.Key_E,'Move'),(Qt.Key_R,'Rotate'),(Qt.Key_T,'Scale')):
            QTest.keyClick(v,key);assert v.mode==mode
        for selection in (0,-1):
            v.selected=selection;v.set_mode('Scale');repaint();item=v.active_transform();before=copy.deepcopy(item)
            h=v.handles[0];a=h['b'];direction=h['b']-h['a'];direction/=np.linalg.norm(direction)
            drag(a,a+direction*40)
            assert item['scale']>before['scale'] and item['position']==before['position'] and item['rotation']==before['rotation']
            h=v.handles[0];a=h['b'];before=copy.deepcopy(item);drag(a,a-direction*30,cancel=True);assert item==before
            repaint();h=v.handles[0];a=h['b'];drag(a,a-direction*40);assert item['scale']<before['scale']
        print('PASS object clicks, XYZ moves/rotations, Esc rollback, parent transforms, E/R/T and uniform object/scene scale with fixed pivots',flush=True)
        v.close();app.exit(0)
    except Exception:
        import traceback;traceback.print_exc();v.close();app.exit(1)
QTimer.singleShot(300,check);sys.exit(app.exec())
