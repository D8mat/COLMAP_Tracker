"""Surface generation process and shading controls."""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLabel, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton, QProgressBar, QFileDialog, QMessageBox, QSizePolicy)
from pipeline import ROOT, CONFIG
from mesh_data import load_mesh, write_ply
from scene_geometry import transform_matrix


class MeshPanel(QWidget):
    def __init__(self, window):
        super().__init__(); self.window=window; self.process=None; self.log=None; self.log_offset=0
        layout=QVBoxLayout(self)
        form=QFormLayout();layout.addLayout(form)
        self.shading=QComboBox();self.shading.addItems(['Solid','Vertex color','Wireframe','Solid + wire','Normals']);self.shading.setCurrentText('Vertex color');form.addRow('Mesh / objects',self.shading)
        self.smooth=QCheckBox('Smooth normals');self.smooth.setChecked(True);form.addRow(self.smooth)
        self.show_mesh=QCheckBox('Show mesh in 3D viewport');self.show_mesh.setChecked(True);form.addRow(self.show_mesh)
        self.point_color=QComboBox();self.point_color.addItems(['RGB','Solid','Depth']);form.addRow('Video point color',self.point_color)
        self.point_size=QSpinBox();self.point_size.setRange(1,12);self.point_size.setValue(3);self.point_size.setSuffix(' px');form.addRow('Video point size',self.point_size)
        for signal in (self.shading.currentTextChanged,self.smooth.toggled,self.show_mesh.toggled,self.point_color.currentTextChanged,self.point_size.valueChanged):signal.connect(self.refresh)
        note=QLabel('Surface from sparse points\nApproximate Poisson reconstruction. Missing surfaces are inferred; this is not a dense solve.');note.setWordWrap(True);note.setMinimumWidth(1);note.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);layout.addWidget(note)
        options=QFormLayout();layout.addLayout(options)
        self.depth=QSpinBox();self.depth.setRange(6,10);self.depth.setValue(8);options.addRow('Mesh detail',self.depth)
        self.limit=QSpinBox();self.limit.setRange(1000,200000);self.limit.setSingleStep(10000);self.limit.setValue(80000);options.addRow('Max input points',self.limit)
        self.trim=QDoubleSpinBox();self.trim.setRange(0,10);self.trim.setValue(6);self.trim.setSingleStep(.5);self.trim.setToolTip('Higher values remove more weakly supported surface. Lower if the mesh is missing large areas.');options.addRow('Density trim',self.trim)
        self.build_button=QPushButton('Build surface mesh');self.build_button.clicked.connect(self.start);layout.addWidget(self.build_button)
        self.cancel_button=QPushButton('Cancel mesh');self.cancel_button.clicked.connect(self.cancel);self.cancel_button.setEnabled(False);layout.addWidget(self.cancel_button)
        self.progress=QProgressBar();self.progress.setRange(0,1);self.progress.setValue(0);layout.addWidget(self.progress)
        self.status=QLabel('No mesh loaded');self.status.setWordWrap(True);self.status.setMinimumWidth(1);self.status.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);layout.addWidget(self.status)
        self.load_button=QPushButton('Load saved mesh…');self.load_button.clicked.connect(self.choose_mesh);layout.addWidget(self.load_button)
        self.export_button=QPushButton('Export mesh .ply…');self.export_button.clicked.connect(self.export);self.export_button.setEnabled(False);layout.addWidget(self.export_button)
        layout.addStretch()
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(100)

    @property
    def running(self):return self.process is not None

    def refresh(self,*args):
        view=self.window.viewport;view.shading=self.shading.currentText();view.smooth_mesh=self.smooth.isChecked();view.show_mesh=self.show_mesh.isChecked();view.update()
        for widget in (self.window.image,self.window.video_widget):
            widget.cloud_color=self.point_color.currentText();widget.cloud_size=self.point_size.value();widget.update()

    def accept_mesh(self,path):
        track=self.window.camera_editor.track
        if track is None:raise ValueError('Load a reconstruction first.')
        mesh=load_mesh(path,track.fingerprint);self.window.viewport.set_mesh(mesh)
        self.window.mesh_toggle.setChecked(True);self.export_button.setEnabled(True)
        self.status.setText(f'{len(mesh["vertices"]):,} vertices / {len(mesh["faces"]):,} triangles\nSparse surface approximation')
        self.refresh();self.window.refresh_overlay()

    def model_changed(self):
        self.window.viewport.set_mesh(None);self.export_button.setEnabled(False);self.status.setText('No mesh loaded')
        track=self.window.camera_editor.track
        manifest=ROOT/'projects/meshes'/track.fingerprint/'latest.json'
        if manifest.is_file():
            try:self.accept_mesh(json.loads(manifest.read_text(encoding='utf-8'))['path'])
            except Exception as exc:self.status.setText('Saved mesh unavailable: '+str(exc))

    def start(self):
        if self.running:return
        w=self.window
        if w.model_folder is None or w.loader is not None or w.job is not None:
            self.status.setText('Load a reconstruction and finish tracking first.');return
        self.folder=ROOT/'projects/meshes'/w.camera_editor.track.fingerprint/uuid.uuid4().hex[:10]
        self.folder.mkdir(parents=True,exist_ok=True)
        self.log=(self.folder/'meshing.log').open('w',encoding='utf-8');self.log_offset=0
        executable=Path(sys.executable)
        if executable.name.lower()=='pythonw.exe':executable=executable.with_name('python.exe')
        try:
            self.process=subprocess.Popen([str(executable),'-u',str(ROOT/'app/mesh_worker.py'),'--model',str(w.model_folder),'--output',str(self.folder),'--colmap',CONFIG['colmap'],'--depth',str(self.depth.value()),'--limit',str(self.limit.value()),'--trim',str(self.trim.value())],stdout=self.log,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONIOENCODING='utf-8'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except Exception as exc:
            self.log.close();self.log=None;self.status.setText(str(exc));return
        self.status.setText('Building mesh…');self.progress.setRange(0,0);self.set_busy(True)

    def set_busy(self,busy):
        for widget in (self.build_button,self.load_button,self.depth,self.limit,self.trim):widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy);self.window.set_busy(busy or self.window.job is not None)

    def tick(self):
        if not self.process:return
        with (self.folder/'meshing.log').open(encoding='utf-8',errors='replace') as log:
            log.seek(self.log_offset);text=log.read(65536);self.log_offset=log.tell()
        if text:
            self.window.console.appendPlainText(text.rstrip());self.status.setText(text.strip().splitlines()[-1])
        code=self.process.poll()
        if code is None:return
        self.process=None;self.log.close();self.log=None;self.progress.setRange(0,1);self.progress.setValue(int(code==0));self.set_busy(False)
        if code!=0:self.status.setText('Meshing failed. Details are in the console and '+str(self.folder/'meshing.log'));return
        try:
            self.accept_mesh(self.folder/'surface.npz')
            manifest=self.folder.parent/'latest.json';temporary=manifest.with_suffix('.json.tmp')
            temporary.write_text(json.dumps({'path':str(self.folder/'surface.npz')}),encoding='utf-8');temporary.replace(manifest)
        except Exception as exc:self.status.setText('Mesh load failed: '+str(exc))

    def cancel(self):
        if not self.process:return
        # Stop the worker and its COLMAP child together; previous completed mesh stays loaded.
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=15)
        else:self.process.terminate()
        self.process.wait(timeout=10);self.process=None;self.log.close();self.log=None
        self.progress.setRange(0,1);self.progress.setValue(0);self.set_busy(False);self.status.setText('Mesh generation cancelled.')

    def choose_mesh(self):
        path,_=QFileDialog.getOpenFileName(self,'Load mesh for this reconstruction',str(ROOT/'projects/meshes'),'Tracker mesh (*.npz)')
        if path:
            try:self.accept_mesh(path)
            except Exception as exc:QMessageBox.warning(self,'Cannot load mesh',str(exc))

    def export(self):
        mesh=self.window.viewport.mesh
        if mesh is None:return
        path,_=QFileDialog.getSaveFileName(self,'Export mesh in world Z-up coordinates','surface.ply','PLY (*.ply)')
        if not path:return
        if not path.lower().endswith('.ply'):path+='.ply'
        try:
            m=transform_matrix(self.window.viewport.scene_transform)
            write_ply(path,mesh['vertices']@m[:3,:3].T+m[:3,3],mesh['colors'],mesh['faces'])
            self.status.setText('Mesh exported: '+path)
        except Exception as exc:QMessageBox.warning(self,'Cannot export mesh',str(exc))
