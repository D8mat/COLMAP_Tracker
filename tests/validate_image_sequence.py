import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
"""Native PNG/JPG/EXR/TIFF input, timing, project reopening and real tracking preparation."""
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import desktop
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QImage,QColor,QSurfaceFormat
from PySide6.QtWidgets import QApplication,QFileDialog,QInputDialog,QMessageBox
from PySide6.QtTest import QTest
from pipeline import CONFIG,Job,read_model
from image_sequence import scan_sequence
from project_io import write_project,read_project
from sequence_preview import first_size
from test_camera_track import pose_from_matrix,matrix

folder=desktop.ROOT/'validation/image_sequence';folder.mkdir(parents=True,exist_ok=True)
os.environ['ALIEN_TRACKER_STATE_DIR']=str(folder/'recovery')
source=folder/'images with spaces';source.mkdir(exist_ok=True)
for name,color in [('take_1.png','#d02020'),('take_2.jpg','#20d020'),('take_4.PNG','#2020d0'),('take_10.jpeg','#d0d020')]:
    image=QImage(160,120,QImage.Format_RGB32);image.fill(QColor(color));assert image.save(str(source/name))
result=subprocess.run([CONFIG['ffmpeg'],'-v','error','-nostdin','-y','-i',str(source/'take_4.PNG'),'-frames:v','1','-pix_fmt','gbrpf32le',str(source/'take_3.exr')],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
assert result.returncode==0,result.stderr.decode(errors='replace')
for name,pixel_format in [('take_11.tif','rgb24'),('take_12.TIFF','rgb48le')]:
    result=subprocess.run([CONFIG['ffmpeg'],'-v','error','-nostdin','-y','-i',str(source/'take_4.PNG'),'-frames:v','1','-pix_fmt',pixel_format,str(source/name)],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode==0,result.stderr.decode(errors='replace')
assert QImage(str(source/'take_12.TIFF')).depth()==64,'16-bit RGB TIFF did not decode at full depth'
original={p.name:p.read_bytes() for p in source.iterdir() if p.is_file()}
fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.CoreProfile);QSurfaceFormat.setDefaultFormat(fmt)
app=QApplication([]);w=desktop.Window();w.show()

def until(condition,seconds=10):
    deadline=time.perf_counter()+seconds
    while not condition() and time.perf_counter()<deadline:app.processEvents();QTest.qWait(10)
    assert condition(),'Timed out waiting for sequence'

def run():
    try:
        # Exercise the real File-menu callback, asynchronous import, and FPS dialog.
        directory,rate=QFileDialog.getExistingDirectory,QInputDialog.getDouble
        QFileDialog.getExistingDirectory=lambda *a,**k:str(source)
        QInputDialog.getDouble=lambda *a,**k:(24.,True)
        try:w.project.actions['Open image sequence…'].trigger()
        finally:QFileDialog.getExistingDirectory=directory;QInputDialog.getDouble=rate
        until(lambda:w.loader is None and w.sequence.active and w.video_widget.pixmap() is not None)
        assert w.sequence.data['files']==['take_1.png','take_2.jpg','take_3.exr','take_4.PNG','take_10.jpeg','take_11.tif','take_12.TIFF']
        assert w.slider.minimum()==1 and w.slider.maximum()==7
        for frame in (2,3,5,6,7,1):
            w.transport.go(frame);until(lambda:w.sequence.frame==frame)
            assert not w.video_widget.pixmap().isNull()
        w.transport.go(7);until(lambda:w.sequence.frame==7)
        w.video_widget.setFocus();QTest.keyClick(w.video_widget,Qt.Key_Space)
        assert w.sequence.playing and w.sequence.requested==1
        until(lambda:not w.sequence.playing and w.sequence.frame==7)
        w.transport.ranges['source']=(2,4);w.transport.loop.setChecked(True);w.toggle_play();QTest.qWait(450)
        assert w.sequence.playing and 2<=w.sequence.frame<=4
        w.pause();assert not w.sequence.playing
        w.transport.loop.setChecked(False);w.transport.clear_range()
        w.transport.go(3);until(lambda:w.sequence.frame==3)
        w.video_widget.actual_size();until(lambda:w.video_widget.pixmap().width()==160)
        # Reopen a sequence-only project using its saved ordered manifest.
        target=folder/'sequence.tracker.json';write_project(target,w.project.snapshot())
        w.project.mark_saved();assert w.project.open_path(target)
        until(lambda:w.loader is None and w.sequence.frame==3)
        assert w.sequence.data['fps']==24 and w.sequence.active
        # Invalid input fails before replacing the already-open project.
        broken=folder/'broken';broken.mkdir(exist_ok=True);(broken/'001.png').write_bytes(b'not an image')
        baseline=w.project.snapshot();warnings=[];warning=QMessageBox.warning
        QFileDialog.getExistingDirectory=lambda *a,**k:str(broken);QInputDialog.getDouble=lambda *a,**k:(24.,True)
        QMessageBox.warning=lambda *a,**k:warnings.append(a[2])
        try:
            w.project.open_sequence();until(lambda:w.loader is None)
            assert warnings and w.project.snapshot()==baseline
        finally:
            QFileDialog.getExistingDirectory=directory;QInputDialog.getDouble=rate;QMessageBox.warning=warning
        # A solved camera overlays the matching source frame, and the association persists.
        model=folder/'model';model.mkdir(exist_ok=True)
        (model/'cameras.txt').write_text('1 PINHOLE 160 120 100 100 80 60\n');(model/'points3D.txt').write_text('1 0 0 0 255 255 255 0\n')
        lines=[]
        for f in range(1,6):
            p=pose_from_matrix(f,matrix([f*.1,-5,3],[59,0,0]))
            # Use numeric solved names independently from source names.
            p['name']=f'frame_{f:06d}.png'
            image=QImage(160,120,QImage.Format_RGB32);image.fill(QColor('#303030'));image.save(str(model/p['name']))
            lines.extend([' '.join(map(str,[f,*p['q'],*p['t'],1,p['name']])), ''])
        (model/'images.txt').write_text('\n'.join(lines)+'\n')
        w.pending=(model,model,24.);w.model_loaded(read_model(model));w.preview_source();w.transport.go(3);until(lambda:w.sequence.frame==3)
        assert w.video_widget.camera and w.camera_editor.frame==3 and w.viewport.pose is not None
        w.viewport.add_primitive('Cube');app.processEvents();assert w.video_widget.overlay_error==''
        write_project(target,w.project.snapshot());w.project.mark_saved();w.project.open_path(target)
        until(lambda:w.loader is None and w.sequence.active and w.video_widget.camera is not None)
        assert w.model_video==str(source.resolve())
        # Run actual first pipeline stage, not a substitute conversion implementation.
        settings=dict(CONFIG,video=str(source),sequence=w.sequence.data,output=str(folder/'jobs'),fps=24.,duration=0,size=640,overlap=5,gpu=False,solver='COLMAP',mask='')
        job=Job(settings);job.tick();until(lambda:job.process.poll() is not None,30)
        assert job.process.returncode==0,(job.folder/'tracking.log').read_text()
        prepared=sorted((job.folder/'images').iterdir());assert len(prepared)==7
        assert prepared[2].name=='frame_000003.png' and not QImage(str(prepared[2])).isNull()
        for index in (5,6):
            assert prepared[index].suffix=='.png'
            actual=QImage(str(prepared[index]));expected=QImage(str(source/w.sequence.data['files'][index]))
            assert actual.size()==expected.size() and actual.pixelColor(80,60)==expected.pixelColor(80,60)
        assert QImage(str(prepared[6])).depth()==64,'16-bit TIFF precision was lost in the PNG working copy'
        job.cancel()
        assert original=={p.name:p.read_bytes() for p in source.iterdir() if p.is_file()}
        w.grab().save(str(folder/'sequence.png'));w.project.mark_saved();w.close()
        print('PASS PNG/JPG/EXR/TIFF import (8/16-bit TIFF), ordering, async preview, Space replay, loop, 100%, project reopen, camera overlay, tracking preparation and unchanged originals',flush=True);app.exit(0)
    except Exception:
        import traceback;traceback.print_exc();app.exit(1)

QTimer.singleShot(300,run);sys.exit(app.exec())
