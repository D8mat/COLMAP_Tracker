"""Qt adaptation of the Shadow palette by --Shadow--.
Reference: https://extensions.blender.org/themes/shadow/"""
STYLE='''
QWidget { background:#1f1f1f; color:#d7d7d7; font:9pt "Segoe UI"; }
QMainWindow { background:#171717; }
QLabel#brand { color:#e6e6e6; font:700 20pt "Bahnschrift"; padding:9px; border-left:4px solid #2f75bd; }
QLabel#section { color:#e6e6e6; font-weight:700; padding:6px 0; }
QLabel#cameraDrag { padding:2px; border-radius:3px; }
QLabel#cameraDrag:hover { background:#2f75bd; color:#ffffff; }
QLabel#stats { background:#242424; color:#e6e6e6; padding:9px; border-left:2px solid #3b8fe6; }
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QPlainTextEdit { background:#161616; color:#e6e6e6; border:1px solid #333333; border-radius:3px; padding:4px; selection-background-color:#2f75bd; selection-color:#f0f0f0; }
QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus,QComboBox:focus { border-color:#e6e6e6; }
QPushButton { background:#404040; border:1px solid #2b2b2b; border-radius:3px; padding:6px 8px; }
QPushButton:hover { background:#505050; color:#e6e6e6; border-color:#d7d7d7; }
QPushButton:pressed,QPushButton:checked { background:#2f75bd; color:#e6e6e6; border-color:#3b8fe6; }
QPushButton#primary { background:#2f75bd; color:#f0f0f0; font-weight:700; border:1px solid #4772b3; }
QWidget:disabled { color:#777777; } QPushButton:disabled { background:#292929; border-color:#303030; }
QGroupBox { border:1px solid #333333; margin-top:12px; padding-top:13px; }
QGroupBox::title { subcontrol-origin:margin; left:10px; color:#e6e6e6; }
QMenuBar { background:#242424; color:#e6e6e6; border-bottom:1px solid #333333; }
QMenuBar::item:selected,QMenu::item:selected { background:#2f75bd; color:#e6e6e6; }
QMenu { background:#1f1f1f; border:1px solid #333333; padding:5px; }
QMenu::item { padding:5px 25px; } QMenu::separator { height:1px; background:#333333; margin:4px; }
QDockWidget::title { background:#242424; color:#e6e6e6; padding:7px; border-bottom:1px solid #333333; }
QTabBar::tab { background:#242424; padding:7px; border:1px solid #333333; }
QTabBar::tab:selected { background:#2f75bd; color:#e6e6e6; border-bottom:2px solid #e6e6e6; }
QTreeWidget,QTableView { background:#1f1f1f; alternate-background-color:#242424; border:1px solid #333333; }
QTreeWidget::item,QTableView::item { padding:4px; } QTreeWidget::item:selected,QTableView::item:selected { background:#2f75bd; color:#e6e6e6; }
QHeaderView::section { background:#242424; color:#e6e6e6; border:0; border-bottom:1px solid #333333; padding:5px; }
QCheckBox::indicator,QTreeView::indicator { width:12px; height:12px; border:1px solid #d7d7d7; background:#161616; }
QCheckBox::indicator:checked,QTreeView::indicator:checked { background:#2f75bd; border:2px solid #7cadf0; }
QSlider::groove:horizontal { height:4px; background:#0a0a0a; }
QSlider::sub-page:horizontal { background:#3b8fe6; }
QSlider::handle:horizontal { background:#2f75bd; width:10px; margin:-5px 0; border:1px solid #4772b3; }
QScrollBar:vertical { background:#1f1f1f; width:10px; margin:0; }
QScrollBar::handle:vertical { background:#333333; min-height:25px; }
QScrollBar::handle:vertical:hover { background:#d7d7d7; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar:horizontal { background:#1f1f1f; height:10px; margin:0; }
QScrollBar::handle:horizontal { background:#333333; min-width:25px; }
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal { width:0; }
QProgressBar { background:#171717; border:1px solid #333333; color:#e6e6e6; text-align:center; }
QProgressBar::chunk { background:#2f75bd; }
QSplitter::handle { background:#333333; }
QToolTip { background:#171717; color:#e6e6e6; border:1px solid #4772b3; padding:5px; }
'''
