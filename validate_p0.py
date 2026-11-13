"""Interactive integration checks for P0 transport, scene list, history and recovery."""
import sys,time,copy,json,subprocess,os
from pathlib import Path
import numpy as np
import desktop
from PySide6.QtCore import Qt,QTimer,QPointF,QLockFile
from PySide6.QtGui import QSurfaceFormat,QImage,QColor,QMouseEvent
from PySide6.QtWidgets import QApplication,QInputDialog,QFileDialog,QMessageBox
from PySide6.QtTest import QTest
from pipeline import CONFIG,read_model
from project_io import read_project,write_project
from test_camera_track import pose_from_matrix,matrix
from scene_geometry import transform_matrix

fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
folder=desktop.ROOT/'validation/p0';folder.mkdir(parents=True,exist_ok=True);os.environ['ALIEN_TRACKER_STATE_DIR']=str(folder/'recovery')
app=QApplication([]);w=desktop.Window();w.show()
video=folder/'transport.mp4'
subprocess.run([CONFIG['ffmpeg'],'-v','error','-y','-f','lavfi','-i','testsrc=size=160x120:rate=30000/1001','-t','2','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
(folder/'cameras.txt').write_text('1 PINHOLE 320 240 250 250 160 120\n')
(folder/'points3D.txt').write_text('1 0 0 0 255 255 255 0\n2 1 0 0 255 100 0 0\n')
lines=[]
for frame in range(1,13):
    pose=pose_from_matrix(frame,matrix([frame*.1,-5,3],[59,0,0]));lines+=[' '.join(map(str,[frame,*pose['q'],*pose['t'],1,pose['name']])),'']
    image=QImage(320,240,QImage.Format_RGB32);image.fill(QColor(frame*15,40,70));image.save(str(folder/pose['name']))
(folder/'images.txt').write_text('\n'.join(lines)+'\n')
original_question=QMessageBox.question;original_get=QFileDialog.getOpenFileName;original_text=QInputDialog.getText
stage=0;started=0;deadline=time.perf_counter()+35;crash_path=None;source_tests=[8,9,7,59,1];seek_index=0

def flush():app.processEvents();w.history.capture()

def check():
    global stage,started,crash_path,seek_index
    try:
        assert time.perf_counter()<deadline,('P0 timeout',stage,w.transport.pending_frame,w.transport.source_frame)
        if stage==0:
            w.pending=(folder,folder,30000/1001);w.model_loaded(read_model(folder));w.show_editor();w.project.mark_saved();w.history.reset()
            v=w.viewport;e=w.editor
            v.add_primitive('Cube');flush();v.add_primitive('Cone');flush();assert len(e.rows)==3
            e.tree.setCurrentItem(e.rows[0]);assert v.selected==0
            QInputDialog.getText=lambda *a,**k:('Test cube',True);e.rename();flush();assert v.objects[0]['name']=='Test cube'
            e.tree.setCurrentItem(e.rows[0]);e.rows[0].setCheckState(1,Qt.Unchecked);flush();assert not v.objects[0]['visible']
            w.history.undo();assert v.objects[0].get('visible',True);w.history.redo();assert not v.objects[0]['visible'];w.history.undo()
            e.rows[0].setCheckState(2,Qt.Checked);flush();before=copy.deepcopy(v.objects[0]);e.set_value('scale',None,5);e.remove();assert v.objects[0]==before
            e.rows[0].setCheckState(2,Qt.Unchecked);flush();e.duplicate();flush();assert len(v.objects)==3 and e.tree.currentItem().data(0,Qt.UserRole)==2
            e.remove();flush();assert len(v.objects)==2;w.history.undo();assert len(v.objects)==3;w.history.redo();assert len(v.objects)==2
            # A complete gizmo drag produces one undo entry; cancel produces none.
            v.selected=0;v.set_mode('Scale');v.center=np.array(v.objects[0]['position']);v.distance=8;v.grabFramebuffer();v.manipulator.repaint();flush()
            h=v.handles[0];a=QPointF(*h['b']);count=len(w.history.undo_stack);scale=v.objects[0]['scale']
            QTest.mousePress(v,Qt.LeftButton,pos=a.toPoint())
            for dx in (10,20,30):
                b=a+QPointF(dx,-dx);app.sendEvent(v,QMouseEvent(QMouseEvent.MouseMove,b,b,Qt.NoButton,Qt.LeftButton,Qt.NoModifier));app.processEvents()
            QTest.mouseRelease(v,Qt.LeftButton,pos=b.toPoint());flush();assert len(w.history.undo_stack)==count+1
            w.history.undo();assert abs(v.objects[0]['scale']-scale)<1e-9
            # Interleaved floor / camera edits undo in their actual order.
            w.project.mark_saved();w.history.reset();w.floor_height.setValue(2);flush()
            corrected=v.pose.copy();corrected[0,3]+=.2;w.camera_editor.track.set_matrix(w.frame,corrected);w.camera_editor.notify();flush()
            w.history.undo();assert not w.camera_editor.track.edits() and w.floor_height.value()==2
            w.history.undo();assert w.project.signature()==w.project.baseline
            w.history.redo();assert w.floor_height.value()==2;w.history.undo()
            # Both layers use precisely the same image rectangle after zoom and pan.
            w.image.actual_size();rect=w.image.image_rect();assert abs(rect.width()*w.image.devicePixelRatioF()-320)<.01
            before=w.image.pixmap().toImage();w.image.pan=QPointF(20,15);w.image.update();assert w.image.pixmap().toImage()==before
            w.image.fit_image();w.transport.go(3);w.transport.set_bound(0);w.transport.go(6);w.transport.set_bound(1);w.transport.loop.setChecked(True)
            w.transport.speed.setCurrentText('2×');w.transport.go(3);w.toggle_play();started=time.perf_counter();stage=1
        elif stage==1 and time.perf_counter()-started>.4:
            assert w.playing and 3<=w.frame<=6;w.pause();w.transport.loop.setChecked(False);w.transport.go(3);w.toggle_play();stage=2
        elif stage==2 and not w.playing:
            assert w.frame==6;w.transport.clear_range();w.transport.speed.setCurrentText('1×')
            # Autosave is separate from the user's main file and active sessions are excluded.
            p=w.project;p.path=folder/'manual.tracker.json';assert p.save();manual=p.path.read_bytes()
            w.viewport.add_primitive('Cube');flush();p.recovery.autosave();assert p.recovery.path.is_file() and p.path.read_bytes()==manual
            saved,_=read_project(p.recovery.path);assert len(saved['layout']['objects'])==3
            crash_path=p.recovery.folder/'p0_test_crash.tracker.json';write_project(crash_path,p.snapshot())
            lock=QLockFile(str(crash_path)+'.lock');assert lock.tryLock(0);assert crash_path not in p.recovery.candidates();lock.unlock();assert crash_path in p.recovery.candidates()
            QMessageBox.question=lambda *a,**k:QMessageBox.Discard
            assert p.open_path(crash_path,recovery=True);stage=3
        elif stage==3 and w.loader is None:
            assert len(w.viewport.objects)==3 and w.project.signature()!=w.project.baseline
            # Missing source media can be relinked without rewriting the original file.
            data=w.project.snapshot();data['assets']['video']=str(folder/'moved.mp4');data['assets']['model_video']=str(folder/'moved.mp4')
            broken=folder/'relink.tracker.json';write_project(broken,data);raw=broken.read_bytes()
            QMessageBox.question=lambda *a,**k:QMessageBox.Yes if 'Missing' in str(a) else QMessageBox.Discard
            QFileDialog.getOpenFileName=lambda *a,**k:(str(video),'Video')
            assert w.project.open_path(broken,relink=True);assert broken.read_bytes()==raw;stage=4
        elif stage==4 and w.loader is None:
            assert Path(w.video.text())==video and w.project.signature()!=w.project.baseline
            w.model_fps=6. # Source remains 29.97 fps; overlays use the solve's independent rate.
            w.preview_source();stage=5
        elif stage==5 and w.transport.stamps:
            assert len(w.transport.stamps)==60,len(w.transport.stamps)
            w.transport.go(source_tests[0]);stage=6
        elif stage==6 and w.transport.pending_frame is None:
            assert w.transport.source_frame==source_tests[seek_index]
            expected=1+round(w.transport.stamps[w.transport.source_frame-1]*w.model_fps)
            assert w.camera_editor.frame==expected
            seek_index+=1
            if seek_index<len(source_tests):w.transport.go(source_tests[seek_index])
            else:
                w.transport.go(8);w.transport.set_bound(0);w.transport.go(12);w.transport.set_bound(1);w.transport.loop.setChecked(True);w.toggle_play();started=time.perf_counter();stage=7
        elif stage==7 and time.perf_counter()-started>.8:
            assert w.player.playbackState()==desktop.QMediaPlayer.PlayingState
            assert 8<=w.transport.source_frame<=12,w.transport.source_frame
            w.pause();w.transport.loop.setChecked(False);w.transport.go(8);w.toggle_play();stage=8
        elif stage==8 and w.player.playbackState()!=desktop.QMediaPlayer.PlayingState and w.transport.pending_frame is None:
            assert w.transport.source_frame==12,w.transport.source_frame
            w.transport.clear_range();w.transport.loop.setChecked(True);w.transport.go(58);w.toggle_play();started=time.perf_counter();stage=9
        elif stage==9 and time.perf_counter()-started>.5:
            assert w.player.playbackState()==desktop.QMediaPlayer.PlayingState and w.transport.source_frame<30,'Whole-source loop did not restart'
            w.pause();w.transport.loop.setChecked(False)
            w.preview_solved();w.graph_toggle.setChecked(False);w.show_editor();w.viewport.fit();app.processEvents();w.grab().save(str(folder/'p0_theme.png'))
            w.project.mark_saved();w.close();crash_path.unlink(missing_ok=True)
            print('PASS P0 list/select/hide/lock/duplicate, grouped undo/redo, camera/floor history, exact 29.97fps source seeks, In/Out/loop/rate, zoom, autosave isolation, recovery and relink',flush=True);app.exit(0);return
        QTimer.singleShot(30,check)
    except Exception:
        import traceback;traceback.print_exc();w.transport.stop_indexer();w.frame_cache.close();w.project.recovery.close()
        if crash_path:crash_path.unlink(missing_ok=True)
        app.exit(1)
QTimer.singleShot(300,check);sys.exit(app.exec())
