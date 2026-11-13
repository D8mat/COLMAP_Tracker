"""One project-level undo history for scene, floor and camera edits."""
import copy
from PySide6.QtCore import QObject
from PySide6.QtGui import QAction,QKeySequence


class EditHistory(QObject):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.applying=False;self.depth=0;self.undo_stack=[];self.redo_stack=[]
        menu=w.menuBar().addMenu('&Edit')
        self.undo_action=QAction('Undo',w);self.undo_action.setShortcut(QKeySequence('Ctrl+Z'));self.undo_action.triggered.connect(self.undo);menu.addAction(self.undo_action)
        self.redo_action=QAction('Redo',w);self.redo_action.setShortcut(QKeySequence('Ctrl+Shift+Z'));self.redo_action.triggered.connect(self.redo);menu.addAction(self.redo_action)
        w.viewport.edited.connect(self.observe);w.camera_editor.changed.connect(self.observe)
        for widget in (w.floor_height,w.floor_spacing,w.floor_toggle):
            (widget.toggled if hasattr(widget,'toggled') else widget.valueChanged).connect(self.observe)
        w.camera_editor.undo_button.clicked.disconnect();w.camera_editor.undo_button.clicked.connect(self.undo)
        w.camera_editor.shared_history=self
        w.floor_panel.undo.clicked.disconnect();w.floor_panel.undo.clicked.connect(self.undo)
        w.floor_panel.undo.setText('Undo last edit')
        self.reset()

    def snapshot(self):
        w=self.w
        return copy.deepcopy(dict(layout=w.editor.snapshot(),corrections=w.camera_editor.track.edits() if w.camera_editor.track else {},
            floor=[w.floor_spacing.value(),w.floor_height.value(),w.floor_toggle.isChecked()]))

    def reset(self):
        self.undo_stack=[];self.redo_stack=[];self.current=self.snapshot();self.update_actions()

    def observe(self,*args):
        self.capture()

    def begin(self):
        self.capture();self.depth+=1

    def end(self):
        self.depth-=1;self.capture()

    def capture(self):
        if self.applying or self.depth or self.w.viewport.drag or self.w.project.restoring:return
        state=self.snapshot()
        if state!=self.current:
            self.undo_stack.append(self.current);self.undo_stack=self.undo_stack[-100:]
            self.current=state;self.redo_stack=[]
        self.update_actions()

    def update_actions(self):
        self.undo_action.setEnabled(bool(self.undo_stack));self.redo_action.setEnabled(bool(self.redo_stack))
        self.w.camera_editor.undo_button.setEnabled(bool(self.undo_stack));self.w.floor_panel.undo.setEnabled(bool(self.undo_stack))

    def apply(self,state):
        w=self.w;w.pause();self.applying=True
        try:
            state=copy.deepcopy(state);v=w.viewport;v.scene_transform=state['layout']['scene'];v.objects=state['layout']['objects']
            v.selected=min(v.selected,len(v.objects)-1);w.floor_panel.previous=None
            w.floor_spacing.setValue(state['floor'][0]);w.floor_height.setValue(state['floor'][1]);w.floor_toggle.setChecked(state['floor'][2])
            if w.camera_editor.track:
                w.camera_editor.track.replace(state['corrections'],remember=False);w.camera_editor.notify()
            w.editor.refresh();w.refresh_overlay();self.current=self.snapshot();w.project.update_title()
        finally:self.applying=False
        self.update_actions()

    def undo(self):
        if self.w.viewport.drag or self.w.camera_editor.dragging or not self.w.project.available():return
        self.capture()
        if self.undo_stack:self.redo_stack.append(self.current);self.apply(self.undo_stack.pop())

    def redo(self):
        if self.w.viewport.drag or self.w.camera_editor.dragging or not self.w.project.available():return
        self.capture()
        if self.redo_stack:self.undo_stack.append(self.current);self.apply(self.redo_stack.pop())
