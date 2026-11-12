"""Real sample: generation, GPU shading, overlays and mesh persistence."""
import sys,time,json
from pathlib import Path
import desktop
from PySide6.QtWidgets import QApplication,QFileDialog
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtTest import QTest
from mesh_data import read_ply
fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);w=desktop.Window();w.show();deadline=time.monotonic()+90;stage=0

def check():
    global stage
    try:
        assert time.monotonic()<deadline,'Mesh test timeout'
        if stage==0 and w.loader is None and w.poses:
            w.select_camera_frame(600);w.mesh_panel.limit.setValue(60000)
            w.show_shading();app.processEvents()
            QTest.mouseClick(w.mesh_panel.build_button,Qt.LeftButton);assert w.mesh_panel.running
            stage=1
        elif stage==1 and not w.mesh_panel.running:
            assert w.viewport.mesh is not None,w.mesh_panel.status.text()
            panel=w.mesh_panel
            w.floor_toggle.setChecked(False);w.overlay_toggle.setChecked(False);w.mesh_toggle.setChecked(False)
            blank=w.image.grab().toImage()
            w.cloud_toggle.setChecked(True);rgb=w.image.grab().toImage()
            assert not w.image.overlay_error,w.image.overlay_error
            assert rgb!=blank,'Point cloud overlay missing'
            panel.point_color.setCurrentText('Depth');depth=w.image.grab().toImage();assert depth!=rgb
            panel.point_size.setValue(6);assert w.image.grab().toImage()!=depth
            w.cloud_toggle.setChecked(False);w.mesh_toggle.setChecked(True)
            results=[]
            for mode in ('Solid','Vertex color','Wireframe','Solid + wire','Normals'):
                panel.shading.setCurrentText(mode);result=w.image.grab().toImage()
                assert not w.image.overlay_error,w.image.overlay_error
                assert result!=blank,mode+' missing'
                assert all(result!=other for other in results),mode+' did not change shading'
                results.append(result)
                assert not w.viewport.grabFramebuffer().isNull()
            panel.shading.setCurrentText('Solid');smooth=w.image.grab().toImage();panel.smooth.setChecked(False);assert w.image.grab().toImage()!=smooth
            w.overlay_alpha.setValue(0);assert w.image.grab().toImage()==blank
            w.overlay_alpha.setValue(75);panel.smooth.setChecked(True);panel.shading.setCurrentText('Vertex color')
            # Reconstruction + camera share the root: overlay must stay aligned.
            before=w.image.grab().toImage();w.viewport.scene_transform['position']=[1.,2.,3.];w.refresh_overlay()
            assert w.image.grab().toImage()==before
            path=desktop.ROOT/'validation/mesh_overlay_export.ply'
            saved=QFileDialog.getSaveFileName;QFileDialog.getSaveFileName=lambda *a,**k:(str(path),'PLY (*.ply)')
            try:panel.export()
            finally:QFileDialog.getSaveFileName=saved
            exported=read_ply(path);assert len(exported['faces'])==len(w.viewport.mesh['faces'])
            import numpy as np
            np.testing.assert_allclose(exported['vertices'],w.viewport.mesh['vertices']+[1,2,3],atol=1e-5)
            w.viewport.scene_transform['position']=[0.,0.,0.];w.refresh_overlay()
            w.graph_toggle.setChecked(False);w.show_shading();app.processEvents();w.seek(600);w.viewport.fit();w.viewport.grabFramebuffer()
            w.grab().save(str(desktop.ROOT/'validation/mesh_overlay.png'))
            old_path=w.viewport.mesh_path;panel.start();QTest.qWait(200);assert panel.running
            panel.cancel();assert not panel.running and w.viewport.mesh_path==old_path
            assert not (panel.folder/'surface.npz').exists(),'Cancelled job unexpectedly completed'
            w.start_export(str(desktop.ROOT/'validation/mesh_overlay.blend'));stage=2
            print('PASS COLMAP surface build, points RGB/depth/size, five mesh modes, smooth/flat, opacity, root alignment and PLY export',flush=True)
        elif stage==2 and w.export_process is None:
            assert w.status.text()=='Blender project exported.',w.status.text()
            print('PASS mesh process-tree cancellation and Blender mesh export',flush=True)
            w.preview_source();w.player.play();stage=3
        elif stage==3 and w.player.position()>400 and w.video_widget.camera:
            w.pause();w.mesh_toggle.setChecked(False);w.cloud_toggle.setChecked(False);blank=w.video_widget.grab().toImage()
            w.mesh_toggle.setChecked(True);mesh=w.video_widget.grab().toImage();assert mesh!=blank,'Source mesh overlay missing'
            w.cloud_toggle.setChecked(True);assert w.video_widget.grab().toImage()!=mesh,'Source point overlay missing'
            assert not w.video_widget.overlay_error,w.video_widget.overlay_error
            e=w.camera_editor;frame=e.frame;pose=w.viewport.pose.copy();pose[0,3]+=.2
            before=w.video_widget.grab().toImage();e.track.set_matrix(frame,pose);e.notify()
            assert w.video_widget.grab().toImage()!=before,'Camera correction did not move source overlays'
            e.track.reset(frame);e.notify();assert not e.track.dirty
            print('PASS original-video mesh/points playback and camera correction alignment',flush=True);w.project.mark_saved();w.close();app.exit(0);return
        QTimer.singleShot(100,check)
    except Exception:
        import traceback;traceback.print_exc();app.exit(1)
QTimer.singleShot(500,check);sys.exit(app.exec())
