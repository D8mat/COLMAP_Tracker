"""Playback clock, frame/pose pairing, seeking and source-frame coalescing."""
import sys,time
import numpy as np
import desktop
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QSurfaceFormat,QImage,QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QVideoFrame
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from camera_track import camera_matrix

fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);w=desktop.Window();w.show();deadline=time.perf_counter()+40;stage=0;origin=None;cache_key=None;source_path=None
w.sample()

def paired():
    np.testing.assert_allclose(w.viewport.pose,camera_matrix(w.pose_by_frame[w.frame]))
    expected=w.frame_cache.get(w.frame);assert expected is not None
    actual=w.image.pixmap().toImage();assert actual==expected.convertToFormat(actual.format()),'Displayed image is from a different frame'

def check():
    global stage,origin,cache_key,source_path
    try:
        assert time.perf_counter()<deadline,('Timeout',stage)
        if stage==0 and w.poses and w.loader is None:
            source_path=w.video.text()
            w.slider.setFocus()
            for key,mode in ((Qt.Key_E,'Move'),(Qt.Key_R,'Rotate'),(Qt.Key_T,'Scale')):
                QTest.keyClick(w.slider,key);assert w.viewport.mode==mode and w.edit_mode.currentText()==mode
            w.video.setFocus();QTest.keyClick(w.video,Qt.Key_E);assert w.viewport.mode=='Scale';w.video.setText(source_path)
            w.slider.setFocus();QTest.keyClick(w.slider,Qt.Key_R,Qt.ControlModifier);assert w.viewport.mode=='Scale'
            w.mesh_toggle.setChecked(True);w.cloud_toggle.setChecked(True);w.select_camera_frame(300)
            w.camera_editor.graph.repaint();cache_key=w.camera_editor.graph.plot_cache.cacheKey()
            w.toggle_play();origin=w.play_origin;stage=1
        elif stage==1 and time.perf_counter()-origin>3:
            assert w.play_origin==origin,'Playback clock was unexpectedly restarted'
            target=300+int((time.perf_counter()-origin)*w.model_fps)
            assert abs(w.frame-target)<=3,(w.frame,target)
            paired();assert w.camera_editor.graph.plot_cache.cacheKey()==cache_key,'Unchanged graph was rebuilt'
            # Rapid direction changes must settle on the most recent requested frame.
            for frame in (800,100,1000,402):w.seek(frame)
            w.pause();assert w.frame==402;paired()
            correction=w.viewport.pose.copy();correction[0,3]+=.1
            w.camera_editor.track.set_matrix(402,correction);w.camera_editor.notify();w.camera_editor.graph.repaint()
            assert w.camera_editor.graph.plot_cache.cacheKey()!=cache_key,'Graph did not invalidate on edit'
            w.camera_editor.track.reset(402);w.camera_editor.notify()
            w.select_camera_frame(w.poses[-1]['frame']-1);w.toggle_play();stage=2
        elif stage==2 and not w.playing:
            assert w.frame==w.poses[-1]['frame'];paired()
            w.slider.setFocus();QTest.keyClick(w.slider,Qt.Key_Space)
            assert w.playing and w.play_frame==w.poses[0]['frame'],'Solved playback did not restart'
            w.pause()
            w.project.clear();w.source_mode=True
            for number in range(10):
                image=QImage(64,64,QImage.Format_RGB32);image.fill(QColor(number*20,30,50))
                frame=QVideoFrame(image);frame.setStartTime(number*33333);w.source_frame(frame)
            assert w._source_scheduled;stage=3
        elif stage==3 and not w._source_scheduled:
            image=w.video_widget.pixmap().toImage();assert image.pixelColor(1,1).red()==180,'Source backlog showed an old video frame'
            assert w._pending_video_frame is None and w.viewport.pose is None
            assert not w.poses and not w.frame_cache.paths,'Project reset retained preview data'
            w.video.setText(source_path);w.preview_source();stage=4
        elif stage==4 and w.player.duration()>0:
            w.player.setPosition(w.player.duration()-400);w.player.play();stage=5
        elif stage==5 and w.player.mediaStatus()==QMediaPlayer.EndOfMedia:
            assert w.play.text()=='▶ Play','End-of-video button still says Pause'
            w.slider.setFocus();QTest.keyClick(w.slider,Qt.Key_Space);stage=6
        elif stage==6 and w.player.playbackState()==QMediaPlayer.PlayingState and 0<w.player.position()<w.player.duration()/2:
            QTest.keyClick(w.slider,Qt.Key_Space);assert w.player.playbackState()==QMediaPlayer.PausedState
            w.project.mark_saved();w.close();assert not w.frame_cache.thread.is_alive()
            print('PASS E/R/T input guards, real-time clock, frame/pose pairing, latest seek, graph caching, Space restart at end for solved/source video, source coalescing and shutdown',flush=True)
            app.exit(0);return
        QTimer.singleShot(30,check)
    except Exception:
        import traceback;traceback.print_exc();w.frame_cache.close();app.exit(1)
QTimer.singleShot(500,check);sys.exit(app.exec())
