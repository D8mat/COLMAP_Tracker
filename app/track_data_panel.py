"""Read-only import inspection and pixel-error overlay display settings."""
from PySide6.QtCore import Qt,QAbstractTableModel,QModelIndex,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableView,QHeaderView,QAbstractItemView,QPushButton,QPlainTextEdit,QDoubleSpinBox,QSpinBox
from track_data import VALID,UNTRIANGULATED


class ImageTable(QAbstractTableModel):
    headers=('Frame','Time (s)','Image ID','Camera ID','2D points','Linked 3D','Unlinked','Invalid','Image')

    def __init__(self,parent=None):
        super().__init__(parent);self.tracks=None;self.images=[];self.fps=30.

    def set_tracks(self,tracks,fps):
        self.beginResetModel();self.tracks=tracks;self.fps=fps
        self.images=sorted(tracks.images.values(),key=lambda image:image.frame) if tracks else []
        self.endResetModel()

    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.images)
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.headers)
    def headerData(self,section,orientation,role=Qt.DisplayRole):
        if role==Qt.DisplayRole and orientation==Qt.Horizontal:return self.headers[section]
        return None

    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid():return None
        image=self.images[index.row()];counts=self.tracks.frame_counts[image.image_id]
        if role==Qt.DisplayRole:
            return (image.frame,f'{image.time_seconds(self.fps):.3f}',image.image_id,image.camera_id,
                    len(image.xy),int(counts[VALID]),int(counts[UNTRIANGULATED]),int(counts[2:].sum()),image.name)[index.column()]
        if role==Qt.TextAlignmentRole and index.column()<8:return int(Qt.AlignRight|Qt.AlignVCenter)
        if role==Qt.ToolTipRole:
            return ('Time is derived from the numbered extracted frame and tracking FPS. It is not a source-video frame number.' if index.column()==1 else
                    'Unlinked = measured 2D features without a reconstructed 3D point. Invalid = missing/inconsistent references or non-finite coordinates; not reprojection error.' if index.column() in (6,7) else image.name)
        return None


class TrackDataPanel(QWidget):
    selected=Signal(int)

    def __init__(self):
        super().__init__();layout=QVBoxLayout(self)
        settings=QHBoxLayout();settings.addWidget(QLabel('Track error overlay: min error'))
        self.minimum_error=QDoubleSpinBox();self.minimum_error.setRange(0,1000);self.minimum_error.setDecimals(2);self.minimum_error.setSuffix(' px');self.minimum_error.setKeyboardTracking(False);settings.addWidget(self.minimum_error)
        settings.addWidget(QLabel('Max markers'));self.marker_limit=QSpinBox();self.marker_limit.setRange(10,5000);self.marker_limit.setValue(1000);self.marker_limit.setSingleStep(100);settings.addWidget(self.marker_limit);settings.addStretch();layout.addLayout(settings)
        self.minimum_error.setToolTip('Error in pixels of the imported model image, independent of preview zoom. The largest errors are prioritised when the marker limit is reached.')
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.model=ImageTable(self);self.table=QTableView();self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True);self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table,1)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(70);layout.addWidget(self.details)
        row=QHBoxLayout();self.go=QPushButton('Go to selected frame');self.go.clicked.connect(self.go_to_frame);row.addWidget(self.go);row.addStretch();layout.addLayout(row)
        self.table.doubleClicked.connect(lambda _:self.go_to_frame());self.table.selectionModel().selectionChanged.connect(lambda:self.go.setEnabled(self.table.currentIndex().isValid()))
        self.set_tracks(None,30.)

    def set_tracks(self,tracks,fps):
        self.model.set_tracks(tracks,fps);self.go.setEnabled(False)
        if tracks is None:
            self.summary.setText('Load a reconstruction to inspect its track data.');self.details.clear();return
        valid=int(tracks.counts[VALID]);unlinked=int(tracks.counts[UNTRIANGULATED]);invalid=int(tracks.counts[2:].sum())
        self.summary.setText(f'{len(tracks.images):,} registered images  ·  {len(tracks.point_ids):,} 3D points  ·  {int(tracks.counts.sum()):,} measured 2D points\n'
                             f'{valid:,} valid 2D↔3D links  ·  {unlinked:,} unlinked features  ·  {invalid:,} invalid observations  ·  {tracks.invalid_links:,} invalid reverse links')
        note='Original imported model data. XY uses its image pixel coordinates; camera/floor edits do not modify these measurements. Time = (frame − 1) / tracking FPS. Only registered images are listed. These counts do not measure solve accuracy.'
        self.details.setPlainText(note+('\n'+'\n'.join(tracks.issue_examples) if tracks.issue_examples else ''))

    def go_to_frame(self):
        index=self.table.currentIndex()
        if index.isValid():self.selected.emit(self.model.images[index.row()].frame)
