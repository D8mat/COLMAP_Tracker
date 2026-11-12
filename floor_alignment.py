"""Fit a manually selected floor and align the scene with world Z up."""
import copy
import numpy as np
from scene_geometry import transform_matrix
from manipulation import euler_xyz


def align_floor(points, scene):
    points=np.asarray(points,dtype=float)
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<3 or not np.isfinite(points).all():
        raise ValueError('Select at least three different floor points.')
    root=transform_matrix(scene);world=points@root[:3,:3].T+root[:3,3]
    center=world.mean(axis=0);_,singular,vectors=np.linalg.svd(world-center,full_matrices=False)
    if singular[0]<1e-8 or singular[1]<singular[0]*.001:
        raise ValueError('Selected points lie on a line. Pick points spread across the floor.')
    normal=vectors[-1]
    if normal[2]<0:normal=-normal
    rms=float(np.sqrt(np.mean(((world-center)@normal)**2)))
    if rms>singular[0]/np.sqrt(len(points))*.05:
        raise ValueError('Selected points do not form a sufficiently flat floor.')
    target=np.array([0.,0.,1.]);axis=np.cross(normal,target);c=float(normal@target)
    x,y,z=axis;k=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
    rotation=np.eye(3)+k+k@k/(1+c)
    adjustment=np.eye(4);adjustment[:3,:3]=rotation
    adjustment[:3,3]=np.array([center[0],center[1],0.])-rotation@center
    result=adjustment@root
    return dict(position=result[:3,3].tolist(),rotation=euler_xyz(result[:3,:3]/scene['scale']),scale=scene['scale']),rms


def make_panel(window):
    from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPushButton,QCheckBox,QMessageBox
    class FloorPanel(QWidget):
        def __init__(self):
            super().__init__();self.previous=None;self.visibility=None
            layout=QVBoxLayout(self)
            label=QLabel('Pick at least 3 points spread across the same floor.\nClick a selected point to remove it. Drag empty space to orbit; use the corner axes for side/top views.');label.setWordWrap(True);layout.addWidget(label)
            self.pick=QCheckBox('Pick floor points');self.pick.toggled.connect(self.set_pick);layout.addWidget(self.pick)
            self.info=QLabel('0 points selected');self.info.setWordWrap(True);layout.addWidget(self.info)
            self.apply_button=QPushButton('Align floor to Z = 0');self.apply_button.clicked.connect(self.apply);layout.addWidget(self.apply_button)
            clear=QPushButton('Clear points');clear.clicked.connect(self.clear);layout.addWidget(clear)
            self.undo=QPushButton('Undo floor alignment');self.undo.clicked.connect(self.restore);self.undo.setEnabled(False);layout.addWidget(self.undo)
            layout.addStretch();window.viewport.floor_selection_changed.connect(self.refresh)
            window.viewport.floor_pick_cancelled.connect(lambda:self.pick.setChecked(False));self.refresh()
        def set_pick(self,enabled):
            v=window.viewport;v.floor_pick=enabled;v.handles=[]
            if enabled:
                window.pause();self.visibility=(window.points_toggle.isChecked(),window.mesh_panel.show_mesh.isChecked())
                window.points_toggle.setChecked(True);window.mesh_panel.show_mesh.setChecked(False);v.setFocus()
            elif self.visibility:
                points,mesh=self.visibility;self.visibility=None
                window.points_toggle.setChecked(points);window.mesh_panel.show_mesh.setChecked(mesh)
            v.update();self.refresh()
        def refresh(self):
            n=len(window.viewport.floor_indices);self.info.setText(f'{n} floor points selected');self.apply_button.setEnabled(n>=3)
        def clear(self):
            window.viewport.floor_indices=[];window.viewport.update();self.refresh()
        def reset(self):
            self.pick.setChecked(False);self.clear();self.previous=None;self.undo.setEnabled(False)
        def apply(self):
            v=window.viewport
            try:scene,rms=align_floor(v.points[v.floor_indices,:3],v.scene_transform)
            except ValueError as exc:QMessageBox.warning(self,'Cannot align floor',str(exc));return
            self.previous=(copy.deepcopy(v.scene_transform),window.floor_height.value())
            v.scene_transform=scene;window.floor_height.setValue(0);window.floor_toggle.setChecked(True)
            self.pick.setChecked(False);v.edited.emit();v.fit();self.undo.setEnabled(True)
            self.info.setText(f'Floor aligned · fitting error {rms:.4g} units')
        def restore(self):
            if self.previous is None:return
            scene,height=self.previous;self.previous=None;self.undo.setEnabled(False)
            window.viewport.scene_transform=scene;window.floor_height.setValue(height);window.viewport.edited.emit();window.viewport.fit();self.refresh()
    return FloorPanel()
