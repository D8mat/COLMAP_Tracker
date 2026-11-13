"""Bounded, latest-request-first frame prefetch. Qt images are decoded off the UI thread."""
from collections import OrderedDict
import bisect
import threading
from pathlib import Path
from PySide6.QtCore import QObject,Signal,QSize,Qt
from PySide6.QtGui import QImage,QImageReader


class FrameCache(QObject):
    ready=Signal(int,int)

    def __init__(self,parent=None,budget=96*1024*1024,ahead=24):
        super().__init__(parent);self.budget=budget;self.ahead=ahead;self.condition=threading.Condition()
        self.generation=0;self.paths={};self.frames=[];self.size=(0,0);self.cache=OrderedDict();self.bytes=0
        self.todo=[];self.requested=None;self.stopping=False
        self.thread=threading.Thread(target=self.run,name='Solved-frame preview',daemon=True);self.thread.start()

    def configure(self,folder,poses):
        with self.condition:
            self.generation+=1;self.paths={p['frame']:str(Path(folder)/p['name']) for p in poses} if folder else {}
            self.frames=sorted(self.paths);self.cache.clear();self.bytes=0;self.todo=[];self.requested=None
            self.condition.notify()

    def request(self,frame,size):
        with self.condition:
            target=(max(1,size.width()),max(1,size.height()))
            if self.size!=target:
                self.size=target;self.generation+=1;self.cache.clear();self.bytes=0;self.todo=[]
            self.requested=frame
            index=bisect.bisect_left(self.frames,frame)
            ahead=min(self.ahead,max(1,self.budget//(target[0]*target[1]*4)-2))
            self.todo=[f for f in [frame]+self.frames[index:index+ahead+1] if f in self.paths and f not in self.cache]
            self.todo=list(dict.fromkeys(self.todo));self.condition.notify()
            return self.get_locked(frame)

    def get_locked(self,frame):
        image=self.cache.get(frame)
        if image is not None:self.cache.move_to_end(frame)
        return image

    def get(self,frame):
        with self.condition:return self.get_locked(frame)

    @staticmethod
    def decode(path,size):
        if not path:return QImage()
        reader=QImageReader(path);target=reader.size()
        if target.isValid():
            if target.width()>size[0] or target.height()>size[1]:target.scale(QSize(*size),Qt.KeepAspectRatio)
            reader.setScaledSize(target)
        return reader.read()

    def store_locked(self,frame,image):
        if frame in self.cache:self.bytes-=self.cache.pop(frame).sizeInBytes()
        self.cache[frame]=image;self.bytes+=image.sizeInBytes()
        while len(self.cache)>48 or (self.bytes>self.budget and len(self.cache)>1):
            oldest=next(key for key in self.cache if key!=self.requested)
            old=self.cache.pop(oldest);self.bytes-=old.sizeInBytes()

    def load_now(self,frame):
        with self.condition:
            image=self.get_locked(frame)
            if image is not None:return image
            generation,path,size=self.generation,self.paths.get(frame),self.size
        image=self.decode(path,size)
        with self.condition:
            if generation==self.generation:self.store_locked(frame,image)
        return image

    def run(self):
        while True:
            with self.condition:
                while not self.todo and not self.stopping:self.condition.wait()
                if self.stopping:return
                frame=self.todo.pop(0)
                if frame in self.cache:continue
                generation,path,size=self.generation,self.paths.get(frame),self.size
            try:image=self.decode(path,size)
            except Exception:image=QImage()
            with self.condition:
                if self.stopping:return
                if generation!=self.generation:continue
                self.store_locked(frame,image);notify=frame==self.requested
            if notify:self.ready.emit(generation,frame)

    def close(self):
        with self.condition:self.stopping=True;self.todo=[];self.condition.notify()
        self.thread.join(timeout=1)
