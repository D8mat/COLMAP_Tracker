import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
"""Real mouse scrubbing, live preview, modifiers and atomic history checks."""
import os,sys
from pathlib import Path
import numpy as np
import desktop
from PySide6.QtCore import Qt,QTimer,QPointF,QEvent
from PySide6.QtGui import QSurfaceFormat,QImage,QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from pipeline import read_model
from camera_track import camera_matrix
from scene_geometry import transform_matrix
from manipulation import euler_xyz

folder=desktop.ROOT/'validation/camera_drag';folder.mkdir(parents=True,exist_ok=True)
os.environ['ALIEN_TRACKER_STATE_DIR']=str(folder/'recovery')
(folder/'cameras.txt').write_text('1 PINHOLE 320 240 250 250 160 120\n')
(folder/'images.txt').write_text('1 1 0 0 0 0 0 0 1 frame_000001.jpg\n160 120 101\n2 1 0 0 0 .1 0 0 1 frame_000002.jpg\n165 120 101\n3 1 0 0 0 .2 0 0 1 frame_000003.jpg\n170 120 101\n')
(folder/'points3D.txt').write_text('101 0 0 5 255 255 255 0 1 0 2 0 3 0\n')
for frame in (1,2,3):
    image=QImage(320,240,QImage.Format_RGB32);image.fill(0xff223344);image.save(str(folder/f'frame_{frame:06}.jpg'))
fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);w=desktop.Window();w.show()

def press(axis):
    label=w.camera_editor.drag_labels[axis];start=label.rect().center();QTest.mousePress(label,Qt.LeftButton,pos=start)
    assert w.camera_editor.dragging and w.history.depth==1
    return label,start

def move(label,start,dx,modifiers=Qt.NoModifier):
    local=QPointF(start)+QPointF(dx,0);global_pos=QPointF(label.mapToGlobal(start))+QPointF(dx,0)
    app.sendEvent(label,QMouseEvent(QEvent.MouseMove,local,global_pos,Qt.NoButton,Qt.LeftButton,modifiers));label.flush();app.processEvents()

def release(label,start,dx):QTest.mouseRelease(label,Qt.LeftButton,pos=(QPointF(start)+QPointF(dx,0)).toPoint());app.processEvents()

def run():
    try:
        w.pending=(folder,folder,30.);w.model_loaded(read_model(folder));w.error_toggle.setChecked(True);w.floor_toggle.setChecked(False)
        w.project.mark_saved();w.history.reset();app.processEvents();e=w.camera_editor
        original=camera_matrix(w.poses[0]).copy();base_rotation=euler_xyz(original[:3,:3])
        for axis in range(6):
            label,start=press(axis)
            for dx in (15,25,40):move(label,start,dx)
            assert len(w.history.undo_stack)==0,'Intermediate mouse updates entered Undo'
            assert not np.allclose(w.viewport.pose,original),'No live preview before mouse release'
            expected=original.copy()
            if axis<3:expected[axis,3]+=40*e.drag_translation_step
            else:
                rotation=base_rotation.copy();rotation[axis-3]+=4
                expected[:3,:3]=transform_matrix(dict(position=[0,0,0],rotation=rotation,scale=1))[:3,:3]
            np.testing.assert_allclose(w.viewport.pose,expected,atol=1e-10)
            release(label,start,40);assert len(w.history.undo_stack)==1 and w.history.depth==0 and not e.dragging
            w.history.undo();np.testing.assert_allclose(w.viewport.pose,original,atol=1e-10)
            assert w.project.signature()==w.project.baseline
            w.history.redo();np.testing.assert_allclose(w.viewport.pose,expected,atol=1e-10);w.history.undo();w.history.reset()
        # Shift is incremental fine motion; changing the modifier must not jump.
        label,start=press(0);move(label,start,20);move(label,start,40,Qt.ShiftModifier)
        assert abs(w.viewport.pose[0,3]-original[0,3]-22*e.drag_translation_step)<1e-10
        w.project.recovery.discard();w.project.recovery.autosave();assert not w.project.recovery.path.exists()
        assert w.project.save() is False,'Saved an unfinished drag'
        QTest.keyClick(label,Qt.Key_Escape);assert not e.dragging and w.history.depth==0 and not w.history.undo_stack
        np.testing.assert_allclose(w.viewport.pose,original,atol=1e-10);release(label,start,40)
        # Clicking without dragging does not dirty the project.
        label,start=press(0);release(label,start,0);assert w.project.signature()==w.project.baseline and not w.history.undo_stack
        label,start=press(0);release(label,start,40)
        assert abs(w.viewport.pose[0,3]-original[0,3]-40*e.drag_translation_step)<1e-10
        w.history.undo();w.history.reset()
        # Focus loss and frame changes both roll back the in-progress edit.
        label,start=press(1);move(label,start,40);app.sendEvent(w,QEvent(QEvent.WindowDeactivate))
        assert not e.dragging and w.history.depth==0;np.testing.assert_allclose(w.viewport.pose,original,atol=1e-10)
        label,start=press(2);move(label,start,40);w.select_camera_frame(2)
        assert not e.dragging and w.frame==e.frame==2 and w.history.depth==0 and not e.track.edits()
        np.testing.assert_allclose(w.viewport.pose,camera_matrix(w.poses[1]),atol=1e-10)
        w.select_camera_frame(1);e.drag_speed.setCurrentText('10×');label,start=press(0);move(label,start,40);release(label,start,40)
        assert abs(w.viewport.pose[0,3]-original[0,3]-400*e.drag_translation_step)<1e-10
        w.history.undo();e.drag_speed.setCurrentText('1×');w.history.reset()
        # Pressing an axis pauses playback; global shortcuts cannot move frames mid-drag.
        w.toggle_play();assert w.playing;label,start=press(0);assert not w.playing
        QTest.keyClick(label,Qt.Key_Right);QTest.keyClick(label,Qt.Key_Space);assert w.frame==1 and not w.playing
        release(label,start,0)
        # A pinned camera frame cannot accidentally redirect edits to a neighbour.
        baseline=e.track.matrices().copy();w.history.reset();w.select_camera_frame(2)
        e.frame_lock.setChecked(True);assert e.locked_frame==2 and e.can_edit_frame()
        label,start=press(5);move(label,start,40);release(label,start,40)
        assert set(e.track.edits())=={'2'}
        np.testing.assert_array_equal(e.track.matrices()[[0,2]],baseline[[0,2]])
        kept=e.track.document();w.select_camera_frame(1)
        assert not e.can_edit_frame() and not e.fields[0].isEnabled() and not e.drag_labels[0].isEnabled()
        assert not e.apply.isEnabled() and not e.interpolate_button.isEnabled() and not e.reset_button.isEnabled()
        e.apply_pose();e.reset();e.interpolate();e.begin_drag(0);assert not e.dragging and e.track.document()==kept
        e.goto_frame_button.click();assert w.frame==e.frame==2 and e.can_edit_frame()
        w.history.undo();np.testing.assert_array_equal(e.track.matrices(),baseline)
        w.history.redo();assert e.track.document()==kept
        w.select_camera_frame(3);e.use_frame_button.click();assert e.locked_frame==3 and e.can_edit_frame()
        e.fields[0].setValue(e.fields[0].value()+.25);e.apply.click()
        assert set(e.track.edits())=={'2','3'} and e.track.edits()['2']==kept['cameras']['2']
        np.testing.assert_array_equal(e.track.matrices()[0],baseline[0])
        e.frame_lock.setChecked(False);w.select_camera_frame(1);assert e.can_edit_frame()
        e.frame_lock.setChecked(True)
        w.grab().save(str(folder/'camera_drag.png'));w.project.mark_saved();w.close()
        print('PASS live axes, atomic history, cancellation, save/playback guards, chosen-frame lock, untouched neighbours and explicit retargeting',flush=True);app.exit(0)
    except Exception:
        import traceback;traceback.print_exc();w.frame_cache.close();app.exit(1)

QTimer.singleShot(100,run);sys.exit(app.exec())
