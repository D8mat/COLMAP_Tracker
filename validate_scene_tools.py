import sys,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import desktop,numpy as np
from scene_geometry import mesh_geometry,transform_matrix,identity_transform,project_camera,clip_near
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);w=desktop.Window();w.show();deadline=time.monotonic()+90
def check():
    if w.loader is not None or not w.poses:
        if time.monotonic()>deadline:app.exit(1);return
        QTimer.singleShot(200,check);return
    try:
        v=w.viewport;w.slider.setValue(600)
        w.mesh_toggle.setChecked(False);w.cloud_toggle.setChecked(False)
        # Actually click gizmo hit zones, including exact top and bottom views.
        for axis in 'XYZ':
            for sign in (-1,1):
                v.gizmo.repaint();hit=next(h for h in v.gizmo.hits if h[1:]==(axis,sign))
                QTest.mouseClick(v.gizmo,Qt.LeftButton,pos=hit[0].toPoint())
                assert v.orthographic,(axis,sign)
                assert v.pitch==({'X':0,'Y':0,'Z':90*sign}[axis])
                assert not v.grabFramebuffer().isNull()
        v.fit()
        cube=v.add_primitive('Cube');cone=v.add_primitive('Cone')
        vertices,faces=mesh_geometry('Cone');assert np.all(vertices[0]==0) and np.min(vertices[1:,2])==2
        # Place visible test objects directly in front of the solved camera.
        for item,x in [(cube,-.7),(cone,.7)]:
            item['position']=(v.pose[:3,:3]@np.array([x,0,-5])+v.pose[:3,3]).tolist();item['scale']=.35
        v.edited.emit();before=w.image.grab().toImage()
        w.overlay_toggle.setChecked(False);after=w.image.grab().toImage();assert before!=after,'Overlay did not render'
        w.overlay_toggle.setChecked(True)
        original=v.pose.copy();v.scene_transform=dict(position=[2.,-3.,1.],rotation=[20.,30.,40.],scale=1.5)
        root=transform_matrix(v.scene_transform);point=np.append(cube['position'],1)
        assert np.allclose(np.linalg.inv(root@original)@(root@point),np.linalg.inv(original)@point)
        v.selected=-1;v.edited.emit();w.editor.fields['position',0].setValue(4.);assert v.scene_transform['position'][0]==4
        w.show_editor();v.grabFramebuffer();w.grab().save(str(desktop.ROOT/'scene_tools_preview.png'))
        w.start_export(str(desktop.ROOT/'validation/scene_tools.blend'))
        print('PASS axis clicks, tip origin, overlay image difference, whole-scene transform invariance, numeric editing',flush=True)
        QTimer.singleShot(250,export_done)
    except Exception:
        import traceback;traceback.print_exc();app.exit(1)
def export_done():
    if w.export_process:
        QTimer.singleShot(250,export_done);return
    if w.status.text()!='Blender project exported.':print(w.status.text());app.exit(1);return
    print('PASS scene-tools Blender export',flush=True);w.project.mark_saved();w.close();app.exit(0)
QTimer.singleShot(500,check);sys.exit(app.exec())
