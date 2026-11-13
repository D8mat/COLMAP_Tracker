"""Per-session recovery files; active sessions never offer one another's snapshots."""
import json,uuid,os
from pathlib import Path
from PySide6.QtCore import QObject,QTimer,QLockFile
from PySide6.QtWidgets import QFileDialog,QMessageBox
from project_io import write_project,project_document
from pipeline import ROOT


class Recovery(QObject):
    def __init__(self,project,folder=None):
        super().__init__(project);self.project=project;self.folder=Path(folder or os.environ.get('ALIEN_TRACKER_STATE_DIR') or ROOT/'projects/.recovery');self.folder.mkdir(parents=True,exist_ok=True)
        self.path=self.folder/(uuid.uuid4().hex+'.tracker.json');self.lock=QLockFile(str(self.path)+'.lock');self.lock.setStaleLockTime(0);self.lock.tryLock(0)
        self.recent_path=self.folder.parent/'recent_projects.json';self.recent=[]
        try:self.recent=[p for p in json.loads(self.recent_path.read_text()) if isinstance(p,str)][:10]
        except (OSError,ValueError,TypeError):pass
        self.recent_menu=project.menu.addMenu('Recent projects');self.recover_menu=project.menu.addMenu('Recover autosave')
        self.refresh_menus();self.timer=QTimer(self);self.timer.timeout.connect(self.autosave);self.timer.start(30000)
        QTimer.singleShot(500,self.announce)

    def candidates(self):
        result=[]
        for path in self.folder.glob('*.tracker.json'):
            if path==self.path:continue
            lock=QLockFile(str(path)+'.lock');lock.setStaleLockTime(0)
            if lock.tryLock(0):result.append(path);lock.unlock()
        return sorted(result,key=lambda p:p.stat().st_mtime,reverse=True)

    def announce(self):
        if self.candidates():self.project.w.status.setText('Recovery available — File > Recover autosave')

    def refresh_menus(self):
        self.recent_menu.clear();self.recover_menu.clear()
        for path in self.recent:
            action=self.recent_menu.addAction(str(path));action.triggered.connect(lambda checked=False,p=path:self.project.open_path(p,relink=True))
        for path in self.candidates():
            action=self.recover_menu.addAction(path.name);action.triggered.connect(lambda checked=False,p=path:self.project.open_path(p,recovery=True))
        self.recent_menu.setEnabled(bool(self.recent));self.recover_menu.setEnabled(bool(self.recover_menu.actions()))

    def remember(self,path):
        self.recent=[str(path)]+[p for p in self.recent if p!=str(path)];self.recent=self.recent[:10]
        temp=self.recent_path.with_suffix('.tmp')
        try:temp.write_text(json.dumps(self.recent,indent=2),encoding='utf-8');temp.replace(self.recent_path)
        except OSError:pass
        self.refresh_menus()

    def autosave(self):
        p=self.project;w=p.w
        if p.restoring or w.loader is not None or w.viewport.drag or w.camera_editor.dragging or w.job or w.mesh_panel.running:return
        if p.signature()==p.baseline:return
        try:
            data=p.snapshot();data['recovery_source']=str(p.path or '')
            write_project(self.path,data)
        except (OSError,ValueError) as exc:w.status.setText('Autosave failed: '+str(exc))

    def discard(self):
        self.path.unlink(missing_ok=True)

    def close(self):
        self.timer.stop();self.discard();self.lock.unlock()


def relink_document(window,path):
    """Resolve missing assets in a copy before replacing the current project."""
    data=project_document(path);replaced={};data['_relinked']=False
    for key,value in data['assets'].items():
        if not value:continue
        folder=key in ('model','images','sequence','model_sequence')
        if (Path(value).is_dir() if folder else Path(value).is_file()):continue
        if value in replaced:data['assets'][key]=replaced[value];continue
        answer=QMessageBox.question(window,'Missing project asset',f'{key}:\n{value}\n\nLocate the moved file or folder?',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Yes)
        if answer!=QMessageBox.Yes:return None
        if folder:chosen=QFileDialog.getExistingDirectory(window,'Locate '+key,str(Path(value).parent))
        else:chosen=QFileDialog.getOpenFileName(window,'Locate '+key,str(Path(value).parent),'All files (*)')[0]
        if not chosen:return None
        replaced[value]=str(Path(chosen).resolve());data['assets'][key]=replaced[value];data['_relinked']=True
    mask=data['tracking'].get('mask','')
    if mask and not Path(mask).is_file():
        chosen=QFileDialog.getOpenFileName(window,'Locate missing tracking mask',str(Path(mask).parent),'Images (*.png *.jpg *.bmp)')[0]
        if not chosen:return None
        data['tracking']['mask']=str(Path(chosen).resolve())
        data['_relinked']=True
    return data
