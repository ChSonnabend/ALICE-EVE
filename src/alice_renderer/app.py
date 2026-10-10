"""Native desktop controls; all expensive work runs outside the UI thread."""
from __future__ import annotations
import json, threading, sqlite3
from pathlib import Path
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QThread, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,QLabel,QPushButton,QLineEdit,QCheckBox,QComboBox,QSpinBox,QDoubleSpinBox,QTabWidget,QScrollArea,QSplitter,QTableView,QFileDialog,QMessageBox,QPlainTextEdit,QHeaderView,QDialog,QDialogButtonBox)
from .catalogue import Catalogue
from .converters import convert
from .demo import generate
from .inputs import inspect_input,run_ingest_profile
from .model import DETECTORS,COLOR_FIELDS,RenderSettings
from .runtime import find_blender,probe,render_events,launch_editor
from .scene_config import recipe,save_config,load_config,resolve_settings,recommended_quality,quality_settings
from .catalogue import load_event

ROOT=Path(__file__).resolve().parents[2]

class Task(QThread):
    message=Signal(str);result=Signal(object);failed=Signal(str);cancelled=Signal(str)
    def __init__(self,fn,parent):super().__init__(parent);self.fn=fn;self.cancel=threading.Event()
    def run(self):
        try:self.result.emit(self.fn(self.message.emit,self.cancel.is_set))
        except InterruptedError as exc:self.cancelled.emit(str(exc))
        except Exception as exc:self.failed.emit(str(exc))

class EventsModel(QAbstractTableModel):
    changed=Signal()
    columns=('Render','Event','Grouping','Run','TF','Tracks','Clusters','Detectors')
    def __init__(self):super().__init__();self.rows=[];self.selected=set()
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()):return len(self.columns)
    def headerData(self,section,orientation,role=Qt.DisplayRole):
        if role==Qt.DisplayRole:return self.columns[section] if orientation==Qt.Horizontal else section+1
    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid():return None
        row=self.rows[index.row()];col=index.column()
        if col==0 and role==Qt.CheckStateRole:return Qt.Checked if row['ordinal'] in self.selected else Qt.Unchecked
        if role==Qt.DisplayRole:
            return ('',row['event_id'],row['kind'],row['run'],row['timeframe'],row['ntracks'],row['nclusters'],', '.join(json.loads(row['detectors'])))[col]
        if role==Qt.ToolTipRole and col==2:return 'Only collision records refer to primary vertices. Timeframes and ROFs are explicitly labelled.'
    def flags(self,index):return Qt.ItemIsEnabled|Qt.ItemIsSelectable|(Qt.ItemIsUserCheckable if index.column()==0 else Qt.NoItemFlags)
    def setData(self,index,value,role=Qt.EditRole):
        if index.column()!=0 or role!=Qt.CheckStateRole:return False
        ordinal=self.rows[index.row()]['ordinal']
        if value==Qt.Checked.value or value==Qt.Checked:self.selected.add(ordinal)
        else:self.selected.discard(ordinal)
        self.dataChanged.emit(index,index,[role]);self.changed.emit();return True
    def set_rows(self,rows):
        self.beginResetModel();self.rows=rows;self.selected={r['ordinal'] for r in rows};self.endResetModel();self.changed.emit()
    def select_all(self,on):
        self.selected={r['ordinal'] for r in self.rows} if on else set()
        if self.rows:self.dataChanged.emit(self.index(0,0),self.index(len(self.rows)-1,0),[Qt.CheckStateRole])
        self.changed.emit()

def number(value,minimum,maximum,decimals=0):
    obj=QDoubleSpinBox() if decimals else QSpinBox();obj.setRange(minimum,maximum);obj.setValue(value)
    if decimals:obj.setDecimals(decimals)
    return obj

class Window(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('ALICE · Event Renderer');self.resize(1440,980)
        self.catalogue=None;self.task=None;self.device_info=None;self.base=RenderSettings();self.images=[];self.close_pending=False
        self.scene_overrides={};self.timeframe_source=None;self.collision_source=None;self.showing_timeframes=False;self.collision_mode='tracks'
        self.settings_file=ROOT/'settings.local.json'
        if self.settings_file.exists():
            try:
                saved=json.loads(self.settings_file.read_text());self.base=RenderSettings(**saved.get('render',{}));self.saved=saved
            except Exception:self.saved={}
        else:self.saved={}
        self.scene_overrides={key:getattr(self.base,key) for key in ('camera_pose','color_ranges','geometry_lod','geometry_openings','geometry_opacities','roughness','metallic','shading','world_strength','lights','colors_linear')}
        central=QWidget();self.setCentralWidget(central);layout=QVBoxLayout(central)
        title=QLabel('ALICE  /  EVENT RENDERER');title.setObjectName('title');layout.addWidget(title)
        self.summary=QLabel('Choose an input, select events and detectors, then preview or render.');layout.addWidget(self.summary)
        top=QHBoxLayout();layout.addLayout(top)
        self.source=QLineEdit();self.source.setPlaceholderText('Raw TF, CTF, or exported event JSON / JSONL');top.addWidget(self.source,1)
        self.open_button=QPushButton('Open input…');self.open_button.clicked.connect(self.open_input);top.addWidget(self.open_button)
        self.folder_button=QPushButton('Import event folder…');self.folder_button.clicked.connect(self.open_folder);top.addWidget(self.folder_button)
        self.timeframe_button=QPushButton('Whole-TF detector views');self.timeframe_button.setEnabled(False);self.timeframe_button.clicked.connect(self.toggle_timeframe_views);top.addWidget(self.timeframe_button)
        self.demo_button=QPushButton('Synthetic demonstration');self.demo_button.clicked.connect(self.open_demo);top.addWidget(self.demo_button)
        split=QSplitter();layout.addWidget(split,1)
        self.tabs=QTabWidget();split.addWidget(self.tabs)
        self.data_checks={};self.geometry_checks={};self.asset_fields={};self.color_buttons={};self.detector_labels={}
        self.build_detectors();self.build_appearance();self.build_render();self.build_runtime()
        right=QWidget();right_layout=QVBoxLayout(right);split.addWidget(right);split.setSizes([480,900])
        tools=QHBoxLayout();right_layout.addLayout(tools)
        self.all_button=QPushButton('Select all');self.none_button=QPushButton('Select none');tools.addWidget(self.all_button);tools.addWidget(self.none_button)
        self.selection_label=QLabel('0 events selected');tools.addWidget(self.selection_label,1)
        self.model=EventsModel();self.model.changed.connect(self.update_availability)
        self.all_button.clicked.connect(lambda:self.model.select_all(True));self.none_button.clicked.connect(lambda:self.model.select_all(False))
        self.table=QTableView();self.table.setModel(self.model);self.table.setAlternatingRowColors(True);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);self.table.horizontalHeader().setStretchLastSection(True);self.table.setMaximumHeight(290);right_layout.addWidget(self.table)
        self.image=QLabel('Preview will appear here');self.image.setAlignment(Qt.AlignCenter);self.image.setMinimumSize(400,260);self.image.setObjectName('preview')
        right_layout.addWidget(self.image,1)
        self.legend=QLabel('');self.legend.setWordWrap(True);right_layout.addWidget(self.legend)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(120);right_layout.addWidget(self.log)
        bottom=QHBoxLayout();layout.addLayout(bottom)
        self.status=QLabel('Ready');bottom.addWidget(self.status,1)
        self.cancel_button=QPushButton('Cancel');self.cancel_button.setEnabled(False);self.cancel_button.clicked.connect(self.cancel_task);bottom.addWidget(self.cancel_button)
        self.load_config_button=QPushButton('Load config…');self.load_config_button.clicked.connect(self.import_scene);bottom.addWidget(self.load_config_button)
        self.export_config_button=QPushButton('Export config…');self.export_config_button.clicked.connect(self.export_scene);bottom.addWidget(self.export_config_button)
        self.editor_button=QPushButton('Interactive scene…');self.editor_button.clicked.connect(self.open_editor);bottom.addWidget(self.editor_button)
        self.preview_button=QPushButton('Preview first selected event');self.preview_button.clicked.connect(lambda:self.start_render(True));bottom.addWidget(self.preview_button)
        self.render_button=QPushButton('Render selected events');self.render_button.setObjectName('primary');self.render_button.clicked.connect(lambda:self.start_render(False));bottom.addWidget(self.render_button)
        self.update_availability()
        self.setStyleSheet('''QWidget{background:#101724;color:#e2e8f2;font-size:13px;} QLabel#title{font-size:24px;font-weight:700;color:#94e5ff;margin:12px 0;} QLabel#preview{background:#070b14;border:1px solid #25334b;border-radius:8px;} QPushButton{background:#26334b;border:1px solid #40516f;padding:8px 12px;border-radius:5px;} QPushButton:hover{background:#344763;} QPushButton#primary{background:#147b89;border-color:#5ccdde;} QPushButton:disabled,QCheckBox:disabled{color:#586276;} QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QPlainTextEdit{background:#182236;border:1px solid #34435d;padding:6px;border-radius:4px;} QHeaderView::section{background:#26334b;padding:5px;border:0;} QTableView{alternate-background-color:#172034;gridline-color:#27344a;} QTabBar::tab{padding:10px;background:#182236;} QTabBar::tab:selected{background:#2b3b55;} QCheckBox{padding:4px;}''')

    def tab(self,name):
        widget=QWidget();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(widget);self.tabs.addTab(scroll,name);return widget
    def build_detectors(self):
        widget=self.tab('Detectors');layout=QVBoxLayout(widget)
        self.mode=QComboBox();self.mode.addItems(['tracks','clusters','both']);self.mode.setCurrentText(self.base.mode);self.mode.currentTextChanged.connect(self.update_availability)
        form=QFormLayout();form.addRow('Objects',self.mode);layout.addLayout(form)
        note=QLabel('Data controls are disabled when unavailable in the selected events. Matched tracks are shown once in full when any source detector is selected.');note.setWordWrap(True);layout.addWidget(note)
        grid=QGridLayout();layout.addLayout(grid)
        for c,name in enumerate(['Detector','Data','Geometry','Colour']):grid.addWidget(QLabel(name),0,c)
        for row,name in enumerate(DETECTORS,1):
            data=QCheckBox();geometry=QCheckBox();geometry.setChecked(name in self.base.geometry)
            self.data_checks[name]=data;self.geometry_checks[name]=geometry
            label=QLabel(name);self.detector_labels[name]=label
            grid.addWidget(label,row,0);grid.addWidget(data,row,1);grid.addWidget(geometry,row,2);grid.addWidget(self.color_button(name),row,3)
        self.magnet=QCheckBox('L3 magnet');self.magnet.setChecked(self.base.magnet);layout.addWidget(self.magnet)
        self.schematic=QCheckBox('Use approximate schematic envelopes');self.schematic.setChecked(self.base.schematic);self.schematic.setToolTip('Approximate dimensions, not calibrated detector geometry. This choice is recorded in render metadata.');layout.addWidget(self.schematic)
        self.cutaway=QCheckBox('Half cutaway (global Y plane)');self.cutaway.setChecked(self.base.cutaway);layout.addWidget(self.cutaway)
        self.geometry_lod=QComboBox();self.geometry_lod.addItems(['full','simplified']);self.geometry_lod.setCurrentText(self.base.geometry_lod);layout.addWidget(QLabel('Geometry detail'));layout.addWidget(self.geometry_lod)
        self.opacity=number(self.base.geometry_opacity,0,1,2);form=QFormLayout();form.addRow('Geometry opacity',self.opacity);layout.addLayout(form);layout.addStretch()
    def color_button(self,key):
        button=QPushButton(self.base.colors.get(key,'#243a82'));button.clicked.connect(lambda:self.pick_color(key));self.color_buttons[key]=button;return button
    def pick_color(self,key):
        from PySide6.QtWidgets import QColorDialog
        color=QColorDialog.getColor(QColor(self.color_buttons[key].text()),self,'Choose '+key+' colour')
        if color.isValid():
            self.color_buttons[key].setText(color.name());self.scene_overrides.get('colors_linear',{}).pop(key,None)
    def build_appearance(self):
        widget=self.tab('Appearance');layout=QFormLayout(widget)
        self.track_mode=QComboBox();self.cluster_mode=QComboBox()
        for combo in (self.track_mode,self.cluster_mode):combo.addItems(COLOR_FIELDS)
        self.track_mode.setCurrentText(self.base.track_color_mode);self.cluster_mode.setCurrentText(self.base.cluster_color_mode)
        layout.addRow('Track colouring',self.track_mode);layout.addRow('Cluster colouring',self.cluster_mode)
        note=QLabel('Unavailable quantities are disabled. XYZ colours refer to the first sampled point of a track or the cluster position. Unknown values use grey. p and pT are in GeV/c; angles in radians; coordinates and DCA in cm.');note.setWordWrap(True);layout.addRow(note)
        for key in ('tracks','clusters','background','magnet'):layout.addRow(key.capitalize(),self.color_button(key))
        self.palette=QComboBox();self.palette.addItems(['viridis','coolwarm','hsv']);self.palette.setCurrentText(self.base.palette);layout.addRow('Colour scale',self.palette)
        self.auto_range=QCheckBox('Automatic scale range per event');self.auto_range.setChecked(self.base.scale_min is None);layout.addRow(self.auto_range)
        self.minimum=number(self.base.scale_min or 0,-1000000,1000000,3);self.maximum=number(self.base.scale_max or 10,-1000000,1000000,3);layout.addRow('Minimum',self.minimum);layout.addRow('Maximum',self.maximum)
        self.track_radius=number(self.base.track_radius_cm,.001,10,3);self.cluster_radius=number(self.base.cluster_radius_cm,.001,20,3);layout.addRow('Track radius (cm)',self.track_radius);layout.addRow('Cluster radius (cm)',self.cluster_radius)
    def build_render(self):
        widget=self.tab('Render');layout=QFormLayout(widget)
        self.width=number(self.base.width,64,16384);self.height=number(self.base.height,64,16384);self.samples=number(self.base.samples,1,8192)
        layout.addRow('Width (px)',self.width);layout.addRow('Height (px)',self.height);layout.addRow('Cycles samples',self.samples)
        self.denoise=QCheckBox('Denoise');self.denoise.setChecked(self.base.denoise);layout.addRow(self.denoise)
        self.save_blend=QCheckBox('Save editable Blender scenes');self.save_blend.setChecked(self.base.save_blend);layout.addRow(self.save_blend)
        self.backend=QComboBox();self.backend.addItems(['CPU','METAL','HIP','CUDA','OPTIX']);self.backend.setCurrentText(self.base.backend);layout.addRow('Render device backend',self.backend)
        self.device=QComboBox();self.device.addItem('All devices in selected backend','');layout.addRow('Device',self.device)
        self.backend.currentTextChanged.connect(self.update_devices)
        self.probe_button=QPushButton('Check Blender and devices');self.probe_button.clicked.connect(self.check_devices);layout.addRow(self.probe_button)
        self.device_label=QLabel('Device availability is verified before rendering.');self.device_label.setWordWrap(True);layout.addRow(self.device_label)
        self.threads=number(self.base.threads,0,256);layout.addRow('CPU threads (0 = automatic)',self.threads)
        self.camera=QComboBox();self.camera.addItems(['perspective','orthographic']);self.camera.setCurrentText(self.base.camera);layout.addRow('Camera',self.camera)
        self.azimuth=number(self.base.azimuth,-180,180,1);self.elevation=number(self.base.elevation,-89,89,1);self.distance=number(self.base.distance_cm,1,100000,1)
        layout.addRow('Azimuth (°)',self.azimuth);layout.addRow('Elevation (°)',self.elevation);layout.addRow('Distance (cm)',self.distance)
        self.target=[]
        for axis,val in zip('XYZ',self.base.target_cm):
            spin=number(val,-100000,100000,1);self.target.append(spin);layout.addRow('Target '+axis+' (cm)',spin)
        for field in [self.azimuth,self.elevation,self.distance,*self.target]:field.valueChanged.connect(lambda *_:self.scene_overrides.pop('camera_pose',None))
        self.output=QLineEdit(self.saved.get('output',str(ROOT/'renders')));layout.addRow('Output directory',self.path_field(self.output,folder=True))
    def build_runtime(self):
        widget=self.tab('Setup');layout=QFormLayout(widget)
        self.blender=QLineEdit(self.saved.get('blender',find_blender()));layout.addRow('Blender executable',self.path_field(self.blender))
        default_profile=ROOT/'profiles/virgo4-ingest.json'
        self.profile=QLineEdit(self.saved.get('profile') or (str(default_profile) if default_profile.is_file() else ''));layout.addRow('O2 ingestion profile',self.path_field(self.profile))
        note=QLabel('Raw TF/CTF inputs require ALICE O2 decoding/reconstruction and complete primary-vertex export. An O2 profile provides the command and prerequisite checks. Exported event JSON renders without O2. See docs/O2-INTEGRATION.md.');note.setWordWrap(True);layout.addRow(note)
        self.geometry_units=QComboBox();self.geometry_units.addItems(['cm','m']);self.geometry_units.setCurrentText(self.base.geometry_units);layout.addRow('Geometry asset units',self.geometry_units)
        note=QLabel('Each asset must contain only the named detector in ALICE global XYZ coordinates. GLB/glTF, OBJ and Blender files are supported. Preserve run/alignment provenance with the assets.');note.setWordWrap(True);layout.addRow(note)
        for name in (*DETECTORS,'L3'):
            field=QLineEdit(self.base.geometry_assets.get(name,''));self.asset_fields[name]=field;layout.addRow(name+' geometry',self.path_field(field))
    def path_field(self,line,folder=False):
        widget=QWidget();layout=QHBoxLayout(widget);layout.setContentsMargins(0,0,0,0);layout.addWidget(line)
        button=QPushButton('…');button.setMaximumWidth(36)
        def choose():
            path=QFileDialog.getExistingDirectory(self,'Select folder') if folder else QFileDialog.getOpenFileName(self,'Select file')[0]
            if path:line.setText(path)
        button.clicked.connect(choose);layout.addWidget(button);return widget

    def settings(self):
        cfg=RenderSettings(detectors=[d for d,c in self.data_checks.items() if c.isChecked() and c.isEnabled()],geometry=[d for d,c in self.geometry_checks.items() if c.isChecked()],magnet=self.magnet.isChecked(),mode=self.mode.currentText(),track_color_mode=self.track_mode.currentText(),cluster_color_mode=self.cluster_mode.currentText(),colors={k:b.text() for k,b in self.color_buttons.items()},scale_min=None if self.auto_range.isChecked() else self.minimum.value(),scale_max=None if self.auto_range.isChecked() else self.maximum.value(),palette=self.palette.currentText(),geometry_assets={k:v.text() for k,v in self.asset_fields.items() if v.text()},geometry_units=self.geometry_units.currentText(),geometry_opacity=self.opacity.value(),cutaway=self.cutaway.isChecked(),schematic=self.schematic.isChecked(),width=self.width.value(),height=self.height.value(),samples=self.samples.value(),denoise=self.denoise.isChecked(),backend=self.backend.currentText(),device=self.device.currentData() or '',threads=self.threads.value(),track_radius_cm=self.track_radius.value(),cluster_radius_cm=self.cluster_radius.value(),camera=self.camera.currentText(),azimuth=self.azimuth.value(),elevation=self.elevation.value(),distance_cm=self.distance.value(),target_cm=[s.value() for s in self.target],save_blend=self.save_blend.isChecked())
        for key,value in self.scene_overrides.items():setattr(cfg,key,value)
        cfg.geometry_lod=self.geometry_lod.currentText()
        cfg.frame_aspect=cfg.width/cfg.height
        return cfg.validate()
    def save_settings(self,cfg):
        saved={'render':cfg.to_dict(),'blender':self.blender.text(),'profile':self.profile.text(),'output':self.output.text()}
        self.settings_file.write_text(json.dumps(saved,indent=2))
    def busy(self,on):
        for w in (self.tabs,self.open_button,self.folder_button,self.demo_button,self.table,self.all_button,self.none_button,self.preview_button,self.render_button,self.editor_button,self.export_config_button,self.load_config_button):w.setEnabled(not on)
        self.cancel_button.setEnabled(on)
        self.timeframe_button.setEnabled(not on and self.timeframe_source is not None)
        if not on:self.update_availability()
    def start_task(self,fn,done):
        if self.task and self.task.isRunning():return
        self.busy(True);self.task=Task(fn,self);self.task.message.connect(self.message)
        self.task.result.connect(done);self.task.failed.connect(self.failure);self.task.cancelled.connect(self.message);self.task.finished.connect(self.task_finished);self.task.start()
    def task_finished(self):
        self.busy(False)
        if self.close_pending:self.close()
    def message(self,text):
        self.status.setText(text);self.log.appendPlainText(text)
        if text.endswith('/render.png') and Path(text).exists():self.show_image(Path(text))
    def failure(self,text):
        self.status.setText('Action stopped — see prerequisites or details');self.log.appendPlainText(text)
        if not self.close_pending:QMessageBox.warning(self,'Unable to continue',text)
    def cancel_task(self):
        if self.task:self.task.cancel.set();self.status.setText('Cancelling…')
    def open_input(self):
        path=QFileDialog.getOpenFileName(self,'Open ALICE data',str(ROOT/'data'),'ALICE data (*.tf *.rawtf *.root *.ctf *.json *.jsonl *.json.gz *.jsonl.gz);;All files (*)')[0]
        if path:self.load_input(Path(path))
    def open_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Import event JSON folder')
        if path:self.load_input(Path(path))
    def open_demo(self):
        path=generate(ROOT/'examples'/'synthetic-events.jsonl');self.load_input(path)
    def toggle_timeframe_views(self):
        if self.showing_timeframes:
            self.mode.setCurrentText(self.collision_mode);self.load_input(self.collision_source)
        elif self.timeframe_source:
            self.collision_mode=self.mode.currentText();self.mode.setCurrentText('clusters');self.load_input(self.timeframe_source)
    def load_input(self,path):
        self.source.setText(str(path));profile=self.profile.text()
        def work(progress,cancelled):
            info=inspect_input(path,cancelled=cancelled);progress(f'{info.format}: {info.timeframes if info.timeframes is not None else "exported"} timeframe entries; detectors {", ".join(info.detectors) or "not yet decoded"}')
            for warning in info.warnings:progress(warning)
            source=path
            if info.format!='events':
                if not profile:raise ValueError('This input requires O2 decoding/reconstruction before collision events can be listed. Set an O2 ingestion profile in Setup. Blender rendering of exported event JSON does not require O2. See docs/O2-INTEGRATION.md.')
                source=run_ingest_profile(path,Path(profile),ROOT/'cache',progress=progress,cancelled=cancelled)
            cat=Catalogue.build(source,ROOT/'cache',convert=convert,progress=progress,cancelled=cancelled)
            return cat,info
        def done(result):
            self.catalogue,info=result;self.model.set_rows(self.catalogue.rows());self.summary.setText(f'{len(self.model.rows)} records loaded · grouping is shown explicitly · {Path(info.path).name}')
            with sqlite3.connect(self.catalogue.db) as database:
                exported_source=Path(database.execute("SELECT value FROM metadata WHERE key='source'").fetchone()[0])
            manifest_path=(exported_source if exported_source.is_dir() else exported_source.parent)/'manifest.json'
            self.timeframe_source=None;self.collision_source=None;self.showing_timeframes=False
            if manifest_path.exists():
                try:
                    manifest=json.loads(manifest_path.read_text())
                    for name,path in manifest.get('geometry_assets',{}).items():
                        if name in self.asset_fields and isinstance(path,str):self.asset_fields[name].setText(path)
                    if manifest.get('geometry_units') in ('cm','m'):self.geometry_units.setCurrentText(manifest['geometry_units'])
                    if manifest.get('timeframe_events_file')=='timeframe-events.jsonl.gz' and manifest.get('events_file') in ('events.jsonl','events.jsonl.gz'):
                        frames=manifest_path.parent/'timeframe-events.jsonl.gz';collisions=manifest_path.parent/manifest['events_file']
                        if frames.is_file() and collisions.is_file():
                            self.timeframe_source=frames;self.collision_source=collisions;self.showing_timeframes=exported_source.resolve()==frames.resolve()
                except (OSError,ValueError,AttributeError,TypeError):self.message('Geometry metadata could not be loaded; configure assets in Setup.')
            self.timeframe_button.setText('Collision events' if self.showing_timeframes else 'Whole-TF detector views')
            if not self.model.rows:self.failure('Event catalogue is empty; regenerate the input catalogue');return
            available={d for row in self.model.rows for d in json.loads(row['detectors'])}
            for d,c in self.data_checks.items():c.setChecked(d in available)
            first=self.catalogue.load(self.model.rows[0]['ordinal'])
            for warning in first.get('warnings',[]):self.message(warning)
            self.status.setText('Events ready')
        self.start_task(work,done)
    def update_availability(self):
        if not hasattr(self,'model'):return
        rows=[r for r in self.model.rows if r['ordinal'] in self.model.selected]
        available={d for r in rows for d in json.loads(r['detectors'])}
        for name,box in self.data_checks.items():
            was=box.isEnabled();box.setEnabled(name in available);box.setToolTip('Available in selected records' if name in available else 'No exported data for this detector in selected records')
            self.detector_labels[name].setStyleSheet('color:#e2e8f2' if name in available else 'color:#586276')
            if name not in available:box.setChecked(False)
            elif not was:box.setChecked(True)
        for combo,field in ((self.track_mode,'track_fields'),(self.cluster_mode,'cluster_fields')):
            supported=set(COLOR_FIELDS)
            for row in rows:supported&=set(json.loads(row[field]))
            if not rows:supported={'solid'}
            for i in range(combo.count()):combo.model().item(i).setEnabled(combo.itemText(i) in supported)
            if combo.currentText() not in supported:combo.setCurrentText('solid')
        self.selection_label.setText(f'{len(rows)} / {len(self.model.rows)} selected')
        self.preview_button.setEnabled(bool(rows));self.render_button.setEnabled(bool(rows))
    def check_devices(self):
        def done(info):
            self.device_info=info;self.device_label.setText(info['version_string']+' · '+', '.join(d['name']+' ('+d['type']+')' for d in info['devices']));self.update_devices()
        blender=self.blender.text();self.start_task(lambda p,c:probe(blender),done)
    def update_devices(self):
        if not self.device_info:return
        self.device.clear();self.device.addItem('All devices in selected backend','')
        for d in self.device_info['devices']:
            if d['type']==self.backend.currentText():self.device.addItem(d['name'],d['id'])
        for i in range(self.backend.count()):self.backend.model().item(i).setEnabled(any(d['type']==self.backend.itemText(i) for d in self.device_info['devices']))
    def export_scene(self):
        try:
            cfg=self.settings();event=load_event(self.catalogue.event_path(min(self.model.selected))) if self.catalogue and self.model.selected else None
            path=QFileDialog.getSaveFileName(self,'Export portable scene','scene-config.json','Scene config (*.json)')[0]
            if path:save_config(path,recipe(cfg,event));self.message('Portable scene exported: '+path)
        except Exception as exc:self.failure(str(exc))
    def import_scene(self):
        path=QFileDialog.getOpenFileName(self,'Load portable scene','','Scene config (*.json)')[0]
        if not path:return
        try:
            data=load_config(path);root=Path(path).parent
            if any(not (root/ref['file']).is_file() for ref in data['geometry'].values()):
                chosen=QFileDialog.getExistingDirectory(self,'Choose the matching geometry bundle')
                if not chosen:return
                root=Path(chosen)
            cfg=resolve_settings(data,path,root)
            self.apply_scene(cfg);self.message('Scene loaded. Choose the local input and event, then preview or render.')
        except Exception as exc:self.failure(str(exc))
    def apply_scene(self,cfg):
        self.scene_overrides={key:getattr(cfg,key) for key in ('camera_pose','color_ranges','geometry_lod','geometry_openings','geometry_opacities','roughness','metallic','shading','world_strength','lights','colors_linear')}
        for name,box in self.data_checks.items():box.setChecked(name in cfg.detectors)
        for name,box in self.geometry_checks.items():box.setChecked(name in cfg.geometry)
        for name,field in self.asset_fields.items():field.setText(cfg.geometry_assets.get(name,''))
        for name,button in self.color_buttons.items():
            button.setText(cfg.colors[name]);button.setStyleSheet('background:'+cfg.colors[name])
        for name,value in [('mode',cfg.mode),('track_mode',cfg.track_color_mode),('cluster_mode',cfg.cluster_color_mode),('palette',cfg.palette),('camera',cfg.camera),('geometry_units',cfg.geometry_units)]:getattr(self,name).setCurrentText(value)
        for name,value in [('opacity',cfg.geometry_opacity),('track_radius',cfg.track_radius_cm),('cluster_radius',cfg.cluster_radius_cm),('azimuth',cfg.azimuth),('elevation',cfg.elevation),('distance',cfg.distance_cm)]:getattr(self,name).setValue(value)
        for spin,value in zip(self.target,cfg.target_cm):spin.setValue(value)
        self.geometry_lod.setCurrentText(cfg.geometry_lod)
        self.magnet.setChecked(cfg.magnet);self.cutaway.setChecked(cfg.cutaway);self.schematic.setChecked(cfg.schematic)
        self.auto_range.setChecked(cfg.scale_min is None)
        if cfg.scale_min is not None:self.minimum.setValue(cfg.scale_min)
        if cfg.scale_max is not None:self.maximum.setValue(cfg.scale_max)
        self.width.setValue(1920);self.height.setValue(max(64,round(1920/cfg.frame_aspect)))
        self.scene_overrides['camera_pose']=cfg.camera_pose
    def open_editor(self):
        if not self.catalogue or not self.model.selected:return
        try:cfg=self.settings();event=self.catalogue.event_path(min(self.model.selected))
        except Exception as exc:self.failure(str(exc));return
        self.start_task(lambda p,c:launch_editor(self.blender.text(),event,cfg,Path(self.output.text())),lambda result:self.message('Interactive Blender scene started. Open the ALICE EVE sidebar; export or render from there. Log: '+str(result[0]/'editor.log')))
    def render_quality_dialog(self,cfg,devices):
        rec=recommended_quality(devices);dialog=QDialog(self);dialog.setWindowTitle('Full render quality');form=QFormLayout(dialog)
        note=QLabel(rec['reason']);note.setWordWrap(True);form.addRow(note)
        quality=QComboBox();quality.addItems(['draft','balanced','final','publication','custom']);quality.setCurrentText(rec['quality']);form.addRow('Quality preset',quality)
        backend=QComboBox();backend.addItems(list(dict.fromkeys(d['type'] for d in devices['devices'])));backend.setCurrentText(rec['backend']);form.addRow('Available backend',backend)
        width=number(cfg.width,64,16384);height=number(cfg.height,64,16384);samples=number(cfg.samples,1,8192);form.addRow('Custom width',width);form.addRow('Custom height',height);form.addRow('Custom samples',samples)
        def toggle():
            for field in (width,height,samples):field.setEnabled(quality.currentText()=='custom')
        quality.currentTextChanged.connect(toggle);toggle()
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()!=QDialog.Accepted:return None
        custom=quality.currentText()=='custom'
        return quality_settings(cfg,'balanced' if custom else quality.currentText(),backend=backend.currentText(),width=width.value() if custom else None,height=height.value() if custom else None,samples=samples.value() if custom else None)
    def start_render(self,preview):
        if not self.catalogue:return
        try:cfg=self.settings();self.save_settings(cfg)
        except Exception as exc:self.failure(str(exc));return
        ids=sorted(self.model.selected)
        if preview:ids=ids[:1]
        paths=[self.catalogue.event_path(i) for i in ids];blender=self.blender.text();output=Path(self.output.text())
        def run(chosen):
            if chosen is not None:self.start_task(lambda p,c:render_events(blender,paths,chosen,output,preview=preview,progress=p,cancelled=c),lambda batch:self.message(f'Completed: {batch}'))
        if preview:run(cfg)
        else:
            def ready(info):
                # Queue until the device check thread has released the busy state.
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0,lambda:run(self.render_quality_dialog(cfg,info)))
            self.start_task(lambda p,c:probe(blender),ready)
    def show_image(self,path):
        self.images.append(path);self.current_pixmap=QPixmap(str(path));self.image.setPixmap(self.current_pixmap.scaled(self.image.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
        metadata=json.loads((path.parent/'metadata.json').read_text());parts=[f'{metadata["event_id"]} · {metadata["kind"]}',f'{metadata["rendered_tracks"]} tracks · {metadata["rendered_clusters"]} clusters']
        for key in ('track_legend','cluster_legend'):
            legend=metadata.get(key)
            if legend and legend['mode']!='solid':parts.append(f'{key.split("_")[0]}: {legend["mode"]} [{legend["min"]:.3g}, {legend["max"]:.3g}] · {legend["missing"]} unknown')
        if any(v['type']=='schematic' for v in metadata['geometry'].values()):parts.append('Approximate schematic geometry')
        self.legend.setText(' | '.join(parts))
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'current_pixmap'):self.image.setPixmap(self.current_pixmap.scaled(self.image.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
    def closeEvent(self,event):
        if self.task and self.task.isRunning():
            self.close_pending=True;self.task.cancel.set();event.ignore();self.status.setText('Cancelling active work; the window will close when cleanup finishes.');return
        super().closeEvent(event)

def main():
    app=QApplication.instance() or QApplication([]);window=Window();window.show();return app.exec()

if __name__=='__main__':raise SystemExit(main())
