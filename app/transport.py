"""Shared frame controls. Source frames use indexed presentation timestamps, not guessed FPS."""
import bisect,math,time
from pathlib import Path
from PySide6.QtCore import QObject,QProcess,Qt
from PySide6.QtWidgets import QWidget,QHBoxLayout,QLabel,QSpinBox,QComboBox,QCheckBox,QPushButton
from pipeline import CONFIG


class Transport(QObject):
    def __init__(self,w,layout):
        super().__init__(w);self.w=w;self.stamps=[];self.source_path='';self.source_frame=1;self.pending_frame=None;self.ranges={};self.indexer=None
        self.bar=QWidget();row=QHBoxLayout(self.bar);row.setContentsMargins(0,0,0,0)
        def button(text,callback,tip):
            b=QPushButton(text);b.setToolTip(tip);b.clicked.connect(callback);row.addWidget(b);return b
        self.first=button('|◀',lambda:self.go(self.limits()[0]),'First frame (Home)')
        self.prev=button('◀',lambda:self.step(-1),'Previous frame (Left)')
        self.next=button('▶',lambda:self.step(1),'Next frame (Right)')
        self.last=button('▶|',lambda:self.go(self.limits()[1]),'Last frame (End)')
        row.addWidget(QLabel('Frame'));self.number=QSpinBox();self.number.setRange(1,1);self.number.setKeyboardTracking(False);self.number.editingFinished.connect(lambda:self.go(self.number.value()));row.addWidget(self.number)
        self.loop=QCheckBox('Loop');row.addWidget(self.loop)
        self.in_button=button('In',lambda:self.set_bound(0),'Set playback start at current frame (I)')
        self.out_button=button('Out',lambda:self.set_bound(1),'Set playback end at current frame (O)')
        button('Clear',self.clear_range,'Use the full clip');self.label=QLabel('—');row.addWidget(self.label)
        self.speed=QComboBox();self.speed.addItems(['0.25×','0.5×','1×','1.5×','2×']);self.speed.setCurrentIndex(2);self.speed.currentTextChanged.connect(self.speed_changed);row.addWidget(self.speed)
        row.addStretch();layout.addWidget(self.bar)
        self.refresh()

    @property
    def rate(self):return float(self.speed.currentText().replace('×',''))

    def mode(self):return 'source' if self.w.source_mode else 'solved'
    def current(self):
        if self.w.sequence.active:return self.w.sequence.requested
        return self.pending_frame or self.source_frame if self.w.source_mode else self.w.frame
    def limits(self):
        if self.w.sequence.active:return 1,len(self.w.sequence.data['files'])
        if self.w.source_mode:return 1,max(1,len(self.stamps))
        return (self.w.poses[0]['frame'],self.w.poses[-1]['frame']) if self.w.poses else (1,1)
    def bounds(self):
        a,b=self.limits();x,y=self.ranges.get(self.mode(),(a,b));return max(a,min(b,x)),max(a,min(b,y))

    def refresh(self):
        a,b=self.limits();self.number.blockSignals(True);self.number.setRange(a,b);self.number.setValue(max(a,min(b,self.current())));self.number.blockSignals(False)
        lo,hi=self.bounds();self.label.setText(f'{lo}–{hi}')
        ready=self.w.sequence.active or bool(self.stamps if self.w.source_mode else self.w.poses)
        for widget in (self.first,self.prev,self.next,self.last,self.number,self.in_button,self.out_button):widget.setEnabled(ready)

    def go(self,frame):
        w=self.w;w.pause();a,b=self.limits();frame=max(a,min(b,int(frame)))
        if w.sequence.active:w.sequence.request(frame)
        elif w.source_mode:
            if not self.stamps:return
            self.pending_frame=frame;w._pending_video_frame=None
            ts=self.stamps[frame-1];gap=self.stamps[frame]-ts if frame<len(self.stamps) else .03
            w.player.setPosition(round((ts+min(.002,gap/4))*1000))
        elif w.poses:w.seek(frame)
        self.refresh()

    def step(self,delta):self.go(self.current()+delta)
    def set_bound(self,index):
        self.w.pause();a,b=self.bounds();value=self.current()
        self.ranges[self.mode()]=(value,max(value,b)) if index==0 else (min(a,value),value);self.refresh()
    def clear_range(self):self.ranges.pop(self.mode(),None);self.refresh()
    def speed_changed(self):
        w=self.w
        w.sequence.speed_changed()
        if w.playing:w.play_origin=time.perf_counter();w.play_frame=w.frame
        w.player.setPlaybackRate(self.rate)

    def index_source(self,path):
        if self.source_path==path:self.refresh();return
        self.stop_indexer();self.source_path=path;self.stamps=[];self.source_frame=1;self.pending_frame=None;self.ranges.pop('source',None);self.refresh()
        probe=Path(CONFIG['ffmpeg']).with_name('ffprobe.exe')
        if not probe.is_file():self.label.setText('Frame indexing needs ffprobe');return
        process=QProcess(self);self.indexer=process;process.setProgram(str(probe));process.setArguments(['-v','error','-select_streams','v:0','-show_entries','frame=best_effort_timestamp_time','-of','csv=p=0',path])
        process.finished.connect(lambda code,status,p=process,source=path:self.indexed(p,source,code));process.start();self.label.setText('Indexing frames…')

    def indexed(self,process,path,code):
        if process is not self.indexer:return
        stamps=[]
        for line in bytes(process.readAllStandardOutput()).decode('utf-8',errors='replace').splitlines():
            try:value=float(line.split(',')[0])
            except ValueError:continue
            if math.isfinite(value) and (not stamps or value>stamps[-1]):stamps.append(value)
        self.indexer=None;process.deleteLater()
        if path==self.source_path and code==0 and stamps:
            start=stamps[0];self.stamps=[v-start for v in stamps];self.refresh()
        else:self.label.setText('Could not index video frames')

    def frame_at(self,seconds):return max(1,min(len(self.stamps),bisect.bisect_right(self.stamps,seconds+1e-5)))
    def accept_source(self,seconds):
        if not self.stamps:return True
        frame=self.frame_at(seconds)
        if self.pending_frame is not None and frame!=self.pending_frame:return False
        self.pending_frame=None;self.source_frame=frame;self.refresh();return True

    def reset(self):
        self.stop_indexer();self.stamps=[];self.source_path='';self.source_frame=1;self.pending_frame=None;self.ranges={};self.loop.setChecked(False);self.speed.setCurrentIndex(2);self.refresh()
    def stop_indexer(self):
        if self.indexer is not None:
            process=self.indexer;self.indexer=None;process.kill();process.waitForFinished(2000);process.deleteLater()

    def document(self):return dict(ranges={key:list(value) for key,value in self.ranges.items()},loop=self.loop.isChecked(),rate=self.rate)
    def restore(self,data):
        ranges=data.get('ranges',{})
        self.ranges={key:tuple(value) for key,value in ranges.items() if key in ('source','solved') and len(value)==2 and all(isinstance(v,int) and v>=1 for v in value) and value[1]>=value[0]}
        self.loop.setChecked(bool(data.get('loop',False)));rate=data.get('rate',1)
        if rate in (.25,.5,1,1.5,2):self.speed.setCurrentText(f'{rate:g}×')
        self.refresh()
