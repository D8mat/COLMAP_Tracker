"""Native sequence playback on the source timeline, with asynchronous frame decode."""
import copy
import time
from pathlib import Path
from PySide6.QtCore import QObject,QTimer,Qt,QUrl,QSize,QThread,Signal
from PySide6.QtGui import QImageReader,QImage,QPixmap
from preview_cache import FrameCache
from image_sequence import scan_sequence,exr_png
from pipeline import CONFIG


def first_size(folder,data):
    path=Path(folder)/data['files'][0]
    image=QImage.fromData(exr_png(path,CONFIG['ffmpeg']),'PNG') if path.suffix.lower()=='.exr' else QImageReader(str(path)).read()
    if image.isNull():raise ValueError('Cannot read the first sequence image: '+path.name)
    return image.size().width(),image.size().height()


class SequenceLoader(QThread):
    loaded=Signal(object);failed=Signal(str)
    def __init__(self,folder,fps):super().__init__();self.folder=folder;self.fps=fps
    def run(self):
        try:
            data=scan_sequence(self.folder,self.fps);data['size']=first_size(self.folder,data)
            self.loaded.emit((self.folder,data))
        except Exception as exc:self.failed.emit(str(exc))


class SequencePreview(QObject):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.folder='';self.data=None;self.frame=1;self.requested=1;self.playing=False
        self.cache=FrameCache(self);self.cache.ready.connect(self.ready)
        self.timer=QTimer(self);self.timer.setTimerType(Qt.PreciseTimer);self.timer.timeout.connect(self.advance)

    @property
    def selected(self):return bool(self.data and self.w.video.text()==self.folder)
    @property
    def active(self):return self.selected and self.w.source_mode

    def configure(self,folder,data):
        self.clear();self.folder=str(Path(folder).resolve());self.data=copy.deepcopy(data)
        self.w.video.setText(self.folder);self.w.video.setReadOnly(True)
        self.cache.configure(self.folder,[dict(frame=i,name=name) for i,name in enumerate(data['files'],1)])

    def clear(self):
        self.stop();self.folder='';self.data=None;self.frame=1;self.requested=1;self.cache.configure(None,[])
        self.w.video.setReadOnly(False)

    def show(self):
        w=self.w;w.pause();w.source_mode=True;w.player.setSource(QUrl());w._pending_video_frame=None;w._source_image=None
        w.image_stack.setCurrentWidget(w.video_widget);w.video_widget.set_native_size(QSize(*self.data['size']))
        w.transport.stop_indexer();w.transport.stamps=[];w.transport.source_path=''
        w.slider.setRange(1,len(self.data['files']));self.request(self.frame);w.transport.refresh()

    def request(self,frame):
        if not self.active:return
        self.requested=max(1,min(len(self.data['files']),int(frame)))
        image=self.cache.request(self.requested,self.w.video_widget.decode_size())
        if image is not None:self.present(self.requested,image)

    def ready(self,generation,frame):
        if self.active and generation==self.cache.generation and frame==self.requested:
            image=self.cache.get(frame)
            if image is not None:self.present(frame,image)

    def present(self,frame,image):
        w=self.w;self.frame=frame;w.transport.source_frame=frame
        w.slider.blockSignals(True);w.slider.setValue(frame);w.slider.blockSignals(False)
        name=self.data['files'][frame-1]
        w.image_title.setText('IMAGE SEQUENCE · '+name)
        w.time_label.setText(f'Frame {frame} / {len(self.data["files"])} · {(frame-1)/self.data["fps"]:.2f} s · {self.data["fps"]:g} fps')
        if image.isNull():
            w.video_widget.clear();w.video_widget.setText('Cannot read image: '+name);w.status.setText('Cannot read sequence image: '+name);self.stop()
        else:w.video_widget.setPixmap(QPixmap.fromImage(image))
        # Camera and image always use the same presented timestamp.
        if getattr(w,'model_video','')==self.folder:
            solved=1+round((frame-1)/self.data['fps']*w.model_fps);pose=w.pose_by_frame.get(solved)
            w.viewport.set_pose(pose);w.video_widget.camera=w.source_cameras.get(pose['camera']) if pose else None;w.camera_editor.set_frame(solved)
        else:w.viewport.set_pose(None);w.video_widget.camera=None;w.camera_editor.set_frame(-1)
        w.transport.refresh();w.video_widget.update()

    def stop(self):
        self.playing=False;self.timer.stop()
        if hasattr(self.w,'play'):self.w.play.setText('▶ Play')

    def toggle(self):
        if self.playing:self.stop();return
        lo,hi=self.w.transport.bounds()
        start=self.frame if lo<=self.frame<hi else lo
        self.request(start);self.playing=True;self.origin=time.perf_counter();self.start_frame=start
        self.w.play.setText('Ⅱ Pause');self.timer.start(max(1,round(1000/(self.data['fps']*self.w.transport.rate))))

    def speed_changed(self):
        if self.playing:
            self.origin=time.perf_counter();self.start_frame=self.frame
            self.timer.start(max(1,round(1000/(self.data['fps']*self.w.transport.rate))))

    def advance(self):
        if not self.active:self.stop();return
        target=self.start_frame+int((time.perf_counter()-self.origin)*self.data['fps']*self.w.transport.rate)
        lo,hi=self.w.transport.bounds()
        if target>hi:
            if self.w.transport.loop.isChecked():self.origin=time.perf_counter();self.start_frame=lo;target=lo
            else:self.stop();self.request(hi);return
        # Keep the in-flight request until it presents, so slow EXRs cannot starve playback.
        if self.requested==self.frame and target!=self.frame:self.request(target)

    def close(self):self.stop();self.cache.close()
