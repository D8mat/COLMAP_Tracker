import json,math
from pathlib import Path
from PySide6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QHBoxLayout,QLabel,QComboBox,QDoubleSpinBox,QPushButton,QFileDialog,QMessageBox
from scene_geometry import identity_transform


class SceneEditor(QWidget):
    def __init__(self,view):
        super().__init__();self.view=view
        layout=QVBoxLayout(self);layout.addWidget(QLabel('Transform target'))
        self.target=QComboBox();self.target.currentIndexChanged.connect(self.select);layout.addWidget(self.target)
        self.space=QComboBox();self.space.addItems(['Global','Local']);self.space.currentTextChanged.connect(self.change_space);layout.addWidget(QLabel('Gizmo axes'));layout.addWidget(self.space)
        layout.addWidget(QLabel('Whole scene includes camera, points,\ntrajectory and added objects. Pivot: origin.'))
        form=QFormLayout();self.fields={}
        for key,label in [('position','Position'),('rotation','Rotation °')]:
            for i,axis in enumerate('XYZ'):
                spin=QDoubleSpinBox();spin.setDecimals(3);spin.setRange(-1e9,1e9);spin.setSingleStep(.1 if key=='position' else 1)
                spin.valueChanged.connect(lambda value,k=key,n=i:self.set_value(k,n,value));self.fields[key,i]=spin;form.addRow(label+' '+axis,spin)
        spin=QDoubleSpinBox();spin.setDecimals(4);spin.setRange(.0001,1e6);spin.setSingleStep(.1)
        spin.valueChanged.connect(lambda value:self.set_value('scale',None,value));self.fields['scale',None]=spin;form.addRow('Scale',spin);layout.addLayout(form)
        self.button('Reset transform',self.reset,layout);self.button('Remove selected object',self.remove,layout)
        row=QHBoxLayout();self.button('+ Cube',lambda:view.add_primitive('Cube'),row);self.button('+ Cone ↓',lambda:view.add_primitive('Cone'),row);layout.addLayout(row)
        layout.addWidget(QLabel('Cone origin = downward tip.\nE: Move · R: Rotate · T: Uniform scale.\nDrag an arrow, ring or scale square. Esc cancels.'))
        self.button('Save scene layout…',self.save,layout);self.button('Load scene layout…',self.load,layout);layout.addStretch()
        view.edited.connect(self.refresh);self.refresh()
    def button(self,text,callback,layout):
        button=QPushButton(text);button.clicked.connect(callback);layout.addWidget(button)
    def select(self,index):self.view.selected=index-1;self.refresh_fields();self.view.update();self.view.edited.emit()
    def change_space(self,text):self.view.gizmo_space=text;self.view.handles=[];self.view.update()
    def refresh(self):
        self.target.blockSignals(True);self.target.clear();self.target.addItems(['Whole scene']+[o['name'] for o in self.view.objects]);self.target.setCurrentIndex(self.view.selected+1);self.target.blockSignals(False);self.refresh_fields()
    def refresh_fields(self):
        item=self.view.active_transform()
        for (key,index),spin in self.fields.items():
            spin.blockSignals(True);spin.setValue(item[key] if index is None else item[key][index]);spin.blockSignals(False)
    def set_value(self,key,index,value):
        item=self.view.active_transform()
        if index is None:item[key]=value
        else:item[key][index]=value
        self.view.update();self.view.edited.emit()
    def reset(self):self.view.active_transform().update(identity_transform());self.view.update();self.view.edited.emit()
    def remove(self):
        if self.view.selected<0:return
        del self.view.objects[self.view.selected];self.view.selected=-1;self.view.update();self.view.edited.emit()
    def snapshot(self):return dict(version=1,scene=self.view.scene_transform,objects=self.view.objects)
    def save(self):
        path,_=QFileDialog.getSaveFileName(self,'Save scene layout','','Scene layout (*.json)')
        if path:
            if not path.lower().endswith('.json'):path+='.json'
            try:Path(path).write_text(json.dumps(self.snapshot(),indent=2),encoding='utf-8')
            except Exception as exc:QMessageBox.warning(self,'Save failed',str(exc))
    def load(self):
        path,_=QFileDialog.getOpenFileName(self,'Load scene layout','','Scene layout (*.json)')
        if not path:return
        try:
            data=json.loads(Path(path).read_text(encoding='utf-8'));assert data['version']==1
            assert isinstance(data['objects'],list) and len(data['objects'])<=1000
            for item in [data['scene']]+data['objects']:
                for k in ('position','rotation'):
                    assert len(item[k])==3 and all(math.isfinite(float(v)) and abs(v)<=1e9 for v in item[k])
                assert .0001<=float(item['scale'])<=1e6
            for item in data['objects']:
                assert item['kind'] in ('Cube','Cone') and isinstance(item['name'],str)
                assert len(item['color'])==3 and all(0<=float(v)<=1 for v in item['color'])
            self.view.scene_transform=data['scene'];self.view.objects=data['objects'];self.view.selected=-1;self.view.edited.emit();self.view.fit()
        except Exception as exc:QMessageBox.warning(self,'Invalid scene layout',str(exc) or 'Invalid fields')
