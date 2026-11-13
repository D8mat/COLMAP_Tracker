import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
"""Image registration, corrected-pose diagnostics and real-clip playback."""
import sys,os,time,json
from pathlib import Path
import numpy as np
import desktop
from PySide6.QtCore import QTimer,QPointF
from PySide6.QtGui import QSurfaceFormat,QImage
from PySide6.QtWidgets import QApplication
from pipeline import read_model
from camera_track import WORLD,camera_matrix
from project_io import write_project,read_project
from image_overlay import OverlayImage

folder=desktop.ROOT/'validation/reprojection';folder.mkdir(parents=True,exist_ok=True)
os.environ['ALIEN_TRACKER_STATE_DIR']=str(folder/'recovery')
(folder/'cameras.txt').write_text('7 PINHOLE 320 240 250 250 160 120\n')
(folder/'images.txt').write_text('37 1 0 0 0 0 0 0 7 frame_000001.jpg\n170 120 101 210.5 120 201 162 170 301\n')
(folder/'points3D.txt').write_text('101 0 0 5 255 255 255 0 37 0\n201 1 0 5 255 255 255 0 37 1\n301 0 1 5 255 255 255 0 37 2\n')
image=QImage(320,240,QImage.Format_RGB32);image.fill(0);image.save(str(folder/'frame_000001.jpg'))
fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
record=False;paint_times=[];original_paint=OverlayImage.paintEvent
def timed_paint(self,event):
    start=time.perf_counter();original_paint(self,event)
    if record and self.reprojection.enabled:paint_times.append((time.perf_counter()-start)*1000)
OverlayImage.paintEvent=timed_paint
app=QApplication([]);w=desktop.Window();w.show();stage=0;deadline=time.monotonic()+90;started=None

def pixels(image):
    image=image.convertToFormat(QImage.Format_RGBA8888)
    return np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width()].copy()

def check():
    global stage,record,started
    try:
        assert time.monotonic()<deadline,('Reprojection timeout',stage)
        if stage==0:
            w.pending=(folder,folder,30.);w.model_loaded(read_model(folder));w.floor_toggle.setChecked(False);w.overlay_toggle.setChecked(False)
            w.graph_toggle.setChecked(False);w.error_toggle.setChecked(True);canvas=w.image
            for zoom,pan in ((None,QPointF()),(1.,QPointF(12,10))):
                canvas.zoom=zoom;canvas.pan=pan;app.processEvents();raster=pixels(canvas.grab().toImage());rect=canvas.image_rect()
                for u,v in ((170,120),(160,120)):
                    x=round((rect.left()+u/320*rect.width())*canvas.devicePixelRatioF());y=round((rect.top()+v/240*rect.height())*canvas.devicePixelRatioF())
                    patch=raster[y-6:y+7,x-6:x+7];assert np.any((patch[:,:,0]>180)&(patch[:,:,1]<110)&(patch[:,:,2]<140)),'Measured/projected marker lost registration'
            canvas.fit_image();w.project.mark_saved();w.history.reset()
            first=canvas.grab().toImage();w.hide_overlay_toggle.setChecked(True);assert first!=canvas.grab().toImage();w.hide_overlay_toggle.setChecked(False)
            w.error_toggle.setChecked(False);assert first!=canvas.grab().toImage();w.error_toggle.setChecked(True);assert canvas.grab().toImage()==first,'Re-enabled overlay stayed empty'
            np.testing.assert_allclose(canvas.reprojection.cache.result.errors,[10,.5,2])
            corrected=w.viewport.pose.copy();corrected[:3,3]+=WORLD@np.array([1.,0,0]);w.camera_editor.track.set_matrix(1,corrected);w.camera_editor.notify()
            canvas.grab();np.testing.assert_allclose(canvas.reprojection.cache.result.errors,[60,50.5,52])
            w.error_pose.setCurrentText('Original solve');canvas.grab();np.testing.assert_allclose(canvas.reprojection.cache.result.errors,[10,.5,2])
            w.error_pose.setCurrentText('Current camera');w.history.undo();canvas.grab();np.testing.assert_allclose(canvas.reprojection.cache.result.errors,[10,.5,2])
            cached=canvas.reprojection.cache.result;w.viewport.scene_transform['position']=[1,2,3];w.viewport.edited.emit();canvas.grab();assert canvas.reprojection.cache.result is cached
            canvas.reprojection.source=True;canvas.grab();assert not canvas.reprojection.paths and 'Solved frames' in canvas.reprojection.message
            w.refresh_reprojection();canvas.reprojection.frame=99;canvas.grab();assert not canvas.reprojection.paths
            canvas.reprojection.frame=1
            w.track_data_panel.minimum_error.setValue(4);w.track_data_panel.marker_limit.setValue(200);w.error_pose.setCurrentText('Original solve')
            path=folder/'display.tracker.json';write_project(path,w.project.snapshot());doc,model=read_project(path)
            assert doc['diagnostics']==dict(enabled=True,original=True,minimum=4.,limit=200)
            w.project.restore_controls({k:v for k,v in doc.items() if k!='diagnostics'});assert not w.error_toggle.isChecked()
            w.project.restore_controls(doc);canvas.grab();assert canvas.reprojection.marker_count==1
            w.project.clear();assert not w.error_toggle.isChecked() and canvas.reprojection.tracks is None and canvas.reprojection.cache.result is None
            w.sample();stage=1
        elif stage==1 and w.loader is None:
            assert w.track_data is not None,w.status.text()
            w.graph_toggle.setChecked(False);w.error_toggle.setChecked(True);w.floor_toggle.setChecked(False);w.overlay_toggle.setChecked(False)
            w.select_camera_frame(300);w.image.grab();result=w.image.reprojection.cache.result
            assert result is not None and len(result.errors)>1000 and np.median(result.errors)<3
            w.toggle_play();started=time.perf_counter();record=True;stage=2
        elif stage==2 and time.perf_counter()-started>4:
            record=False;elapsed=time.perf_counter()-started
            assert abs(w.frame-(300+int(elapsed*w.model_fps)))<=4,(w.frame,elapsed)
            np.testing.assert_allclose(w.viewport.pose,camera_matrix(w.pose_by_frame[w.frame]))
            assert w.image.reprojection.frame==w.frame
            w.pause();w.image.grab();assert not w.image.reprojection.message.startswith('Track error unavailable')
            result=dict(elapsed=elapsed,paints=len(paint_times),mean_paint_ms=float(np.mean(paint_times)),p95_paint_ms=float(np.percentile(paint_times,95)))
            (folder/'playback.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
            w.grab().save(str(folder/'reprojection.png'));w.project.mark_saved();w.close()
            print('PASS measured/projected pixels at Fit/100%/pan, toggles, original/current camera, Undo, scene-root invariance, source/gap guards, settings persistence and real-clip playback',flush=True);app.exit(0);return
        QTimer.singleShot(40,check)
    except Exception:
        import traceback;traceback.print_exc();w.frame_cache.close();app.exit(1)

QTimer.singleShot(100,check);sys.exit(app.exec())
