import json,math,copy
import numpy as np
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QHBoxLayout,QLabel,QComboBox,QDoubleSpinBox,QPushButton,QFileDialog,QMessageBox,QTreeWidget,QTreeWidgetItem,QAbstractItemView,QInputDialog,QHeaderView
from scene_geometry import identity_transform,transform_matrix
from scene_icons import scene_icon


class SceneEditor(QWidget):
    def __init__(self,view):
        super().__init__();self.view=view
        layout=QVBoxLayout(self);layout.addWidget(QLabel('SCENE OBJECTS'))
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['Object','Show','Lock']);self.tree.setMinimumHeight(180);self.tree.setMaximumHeight(300)
        self.tree.headerItem().setIcon(1,scene_icon('Show'));self.tree.headerItem().setIcon(2,scene_icon('Lock'))
        self.tree.header().setStretchLastSection(False);self.tree.header().setSectionResizeMode(0,QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1,QHeaderView.ResizeToContents);self.tree.header().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers);self.tree.currentItemChanged.connect(self.select_item);self.tree.itemChanged.connect(self.item_changed)
        self.tree.itemDoubleClicked.connect(lambda item,column:QTimer.singleShot(0,self.rename) if column==0 else None);layout.addWidget(self.tree)
        self.target=QComboBox();self.target.currentIndexChanged.connect(self.select);self.target.hide()
        row=QHBoxLayout();self.button('Rename',self.rename,row);self.button('Duplicate',self.duplicate,row);self.button('Frame',self.frame_selected,row);layout.addLayout(row)
        self.space=QComboBox();self.space.addItems(['Global','Local']);self.space.currentTextChanged.connect(self.change_space);layout.addWidget(QLabel('Gizmo axes'));layout.addWidget(self.space)
        layout.addWidget(QLabel('Whole scene includes camera, points,\ntrajectory and added objects. Pivot: origin.'))
        form=QFormLayout();self.fields={}
        for key,label in [('position','Position'),('rotation','Rotation °')]:
            for i,axis in enumerate('XYZ'):
                spin=QDoubleSpinBox();spin.setDecimals(3);spin.setRange(-1e9,1e9);spin.setSingleStep(.1 if key=='position' else 1);spin.setKeyboardTracking(False)
                spin.valueChanged.connect(lambda value,k=key,n=i:self.set_value(k,n,value));self.fields[key,i]=spin;form.addRow(label+' '+axis,spin)
        spin=QDoubleSpinBox();spin.setDecimals(4);spin.setRange(.0001,1e6);spin.setSingleStep(.1);spin.setKeyboardTracking(False)
        spin.valueChanged.connect(lambda value:self.set_value('scale',None,value));self.fields['scale',None]=spin;form.addRow('Scale',spin);layout.addLayout(form)
        self.button('Reset transform',self.reset,layout);self.button('Remove selected object',self.remove,layout)
        row=QHBoxLayout();self.button('+ Cube',lambda:view.add_primitive('Cube'),row);self.button('+ Cone ↓',lambda:view.add_primitive('Cone'),row);layout.addLayout(row)
        layout.addWidget(QLabel('Cone origin = downward tip.\nE: Move · R: Rotate · T: Uniform scale.\nDrag an arrow, ring or scale square. Esc cancels.'))
        self.button('Save scene layout…',self.save,layout);self.button('Load scene layout…',self.load,layout);layout.addStretch()
        self.tree_key=None;view.edited.connect(self.refresh);view.hierarchy_changed.connect(self.refresh);self.refresh()
    def button(self,text,callback,layout):
        button=QPushButton(text);button.clicked.connect(callback);layout.addWidget(button)
        kind={'+ Cube':'Cube','+ Cone ↓':'Cone','Reset transform':'Reset','Remove selected object':'Remove','Save scene layout…':'Save','Load scene layout…':'Load'}.get(text,text)
        button.setIcon(scene_icon(kind))
    def select(self,index):
        if self.view.drag:return
        self.view.selected=index-1;self.refresh_fields();self.view.update();self.view.edited.emit()
    def select_item(self,item,previous):
        if item is not None:self.select(int(item.data(0,Qt.UserRole))+1)
    def item_changed(self,item,column):
        index=item.data(0,Qt.UserRole)
        if index is None or index<0:return
        obj=self.view.objects[index]
        if column in (1,2):obj['visible' if column==1 else 'locked']=item.checkState(column)==Qt.Checked
        self._tree_edit=True
        try:self.view.edited.emit();self.view.update()
        finally:self._tree_edit=False
    def change_space(self,text):self.view.gizmo_space=text;self.view.handles=[];self.view.update()
    def refresh(self):
        if getattr(self,'_tree_edit',False):QTimer.singleShot(0,self.refresh);return
        self.target.blockSignals(True);self.target.clear();self.target.addItems(['Whole scene']+[o['name'] for o in self.view.objects]);self.target.setCurrentIndex(self.view.selected+1);self.target.blockSignals(False);self.refresh_fields()
        key=([(o['name'],o['kind'],o.get('visible',True),o.get('locked',False)) for o in self.view.objects],len(self.view.points),len(self.view.path),id(self.view.mesh))
        self.tree.blockSignals(True)
        if key!=self.tree_key:
            scroll=self.tree.verticalScrollBar().value();self.tree.clear();self.tree_key=key
            root=QTreeWidgetItem(['Whole scene']);root.setData(0,Qt.UserRole,-1);self.tree.addTopLevelItem(root);self.rows={-1:root}
            root.setIcon(0,scene_icon('Whole scene'))
            for label,exists in [('Point cloud',len(self.view.points)),('Camera path',len(self.view.path)),('Surface mesh',self.view.mesh is not None)]:
                if exists:
                    node=QTreeWidgetItem([label]);node.setData(0,Qt.UserRole,-1);node.setToolTip(0,'Moves with Whole scene');root.addChild(node)
                    node.setIcon(0,scene_icon(label))
            for index,obj in enumerate(self.view.objects):
                node=QTreeWidgetItem([obj['name']]);node.setData(0,Qt.UserRole,index);node.setToolTip(0,obj['kind']);node.setFlags(node.flags()|Qt.ItemIsUserCheckable)
                node.setIcon(0,scene_icon(obj['kind']))
                node.setCheckState(1,Qt.Checked if obj.get('visible',True) else Qt.Unchecked);node.setCheckState(2,Qt.Checked if obj.get('locked',False) else Qt.Unchecked)
                root.addChild(node);self.rows[index]=node
            root.setExpanded(True);self.tree.verticalScrollBar().setValue(scroll)
        self.tree.setCurrentItem(self.rows.get(self.view.selected,self.rows[-1]));self.tree.blockSignals(False)
    def refresh_fields(self):
        item=self.view.active_transform()
        for (key,index),spin in self.fields.items():
            spin.blockSignals(True);spin.setValue(item[key] if index is None else item[key][index]);spin.setEnabled(not item.get('locked',False));spin.blockSignals(False)
    def set_value(self,key,index,value):
        item=self.view.active_transform()
        if item.get('locked',False):return
        if index is None:item[key]=value
        else:item[key][index]=value
        self.view.update();self.view.edited.emit()
    def reset(self):
        if self.view.active_transform().get('locked',False):return
        self.view.active_transform().update(identity_transform());self.view.update();self.view.edited.emit()
    def remove(self):
        if self.view.selected<0 or self.view.active_transform().get('locked',False):return
        del self.view.objects[self.view.selected];self.view.selected=-1;self.view.update();self.view.edited.emit()
    def rename(self):
        if self.view.selected<0 or self.view.active_transform().get('locked',False):return
        obj=self.view.active_transform();name,ok=QInputDialog.getText(self,'Rename object','Name',text=obj['name'])
        if ok and name.strip():obj['name']=name.strip()[:200];self.view.edited.emit()
    def duplicate(self):
        if self.view.selected<0:return
        obj=copy.deepcopy(self.view.active_transform());obj['name']+=' copy';obj['locked']=False
        self.view.objects.append(obj);self.view.selected=len(self.view.objects)-1;self.view.edited.emit();self.view.update()
    def frame_selected(self):
        if self.view.selected<0:self.view.fit();return
        obj=self.view.active_transform();root=transform_matrix(self.view.scene_transform)
        self.view.center=root[:3,:3]@np.array(obj['position'])+root[:3,3]
        self.view.distance=max(.01,obj['scale']*self.view.scene_transform['scale']*8);self.view.update()
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
            from project_io import validate_layout
            validate_layout(data)
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
