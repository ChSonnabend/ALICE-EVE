"""Native desktop controls; all expensive work runs outside the UI thread."""
from __future__ import annotations
import json, threading, sqlite3, math, os
from pathlib import Path
import PySide6
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,QLabel,QPushButton,QLineEdit,QCheckBox,QComboBox,QSpinBox,QDoubleSpinBox,QTabWidget,QScrollArea,QSplitter,QTableView,QFileDialog,QMessageBox,QPlainTextEdit,QHeaderView,QDialog,QDialogButtonBox,QSizePolicy,QInputDialog,QSlider,QListWidget,QListWidgetItem,QTreeWidget,QTreeWidgetItem,QProgressBar)
from .catalogue import Catalogue
from .converters import convert
from .demo import generate
from .inputs import inspect_input,run_ingest_profile
from .model import DETECTORS,COLOR_FIELDS,RenderSettings
from .cluster_colors import CLUSTER_COLOR_FIELDS,DESCRIPTIONS
from .runtime import find_blender,probe,render_events,launch_editor
from .scene_config import recipe,save_config,load_config,resolve_settings,recommended_quality,quality_settings
from .catalogue import load_event
from .object_selection import parse_track_ids
from .palettes import names as palette_names
from .scene_library import SceneLibrary
from .resolution import PRESET_PERCENT, minimum_percent, percentage_size
from .defaults import startup_settings,commissioning_settings,local_geometry_asset,detector_settings,SETUP_PRESETS

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
    columns=('Render','Event','Grouping','Run','TF / AO2D frame','Tracks','Clusters','Detectors','PV contributors')
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
            return ('',row['event_id'],row['kind'],row['run'],row['timeframe'],row['ntracks'],row['nclusters'],', '.join(json.loads(row['detectors'])),row.get('contributors') if row.get('contributors') is not None else '—')[col]
        if role==Qt.ToolTipRole and col==2:return 'Only collision records refer to primary vertices. Timeframes and ROFs are explicitly labelled.'
        if role==Qt.ToolTipRole and col==8:return 'Tracks contributing to the reconstructed primary vertex; total exported tracks also include other O2 vertex-associated fitted sources.'
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
        self.catalogue=None;self.loaded_input=None;self.task=None;self.device_info=None;self.base=startup_settings();self.images=[];self.close_pending=False
        self.scene_overrides={};self.timeframe_source=None;self.collision_source=None;self.showing_timeframes=False;self.collision_mode='tracks'
        self.library=SceneLibrary(ROOT/'scene-library.local.sqlite');self.library_signature=None;self.scene_detector_selection=None;self.requested_modes=None
        self.settings_file=ROOT/'settings.local.json'
        if self.settings_file.exists():
            try:
                from .camera import upgrade_local_camera
                saved=json.loads(self.settings_file.read_text());self.base=RenderSettings(**upgrade_local_camera(saved.get('render',{})));self.saved=saved
            except Exception:self.saved={}
        else:self.saved={}
        self.scene_detector_selection=set(self.base.detectors)
        self.scene_overrides={key:getattr(self.base,key) for key in ('render_engine','detector_setup','camera_pose','color_ranges','geometry_lod','geometry_lods','geometry_schematics','geometry_display','geometry_openings','geometry_opening_directions','geometry_exclusions','geometry_inner_masks','geometry_components','geometry_opacities','roughness','metallic','shading','world_strength','lights','colors_linear','palette_lut')}
        central=QWidget();self.setCentralWidget(central);layout=QVBoxLayout(central)
        title=QLabel('ALICE  /  EVENT RENDERER');title.setObjectName('title');layout.addWidget(title)
        self.summary=QLabel('Choose an input, select events and detectors, then preview or render.');layout.addWidget(self.summary)
        top=QHBoxLayout();layout.addLayout(top)
        self.source=QLineEdit();self.source.setPlaceholderText('Paste a file or folder path, then press Enter or Load input');self.source.returnPressed.connect(self.load_typed_input);top.addWidget(self.source,1)
        self.open_button=QPushButton('Load input');self.open_button.clicked.connect(self.load_typed_input);top.addWidget(self.open_button)
        self.browse_button=QPushButton('Browse file…');self.browse_button.clicked.connect(self.open_input);top.addWidget(self.browse_button)
        self.folder_button=QPushButton('Browse folder…');self.folder_button.clicked.connect(self.open_folder);top.addWidget(self.folder_button)
        self.timeframe_button=QPushButton('Whole-TF detector views');self.timeframe_button.setEnabled(False);self.timeframe_button.clicked.connect(self.toggle_timeframe_views);top.addWidget(self.timeframe_button)
        self.demo_button=QPushButton('Synthetic demonstration');self.demo_button.clicked.connect(self.open_demo);top.addWidget(self.demo_button)
        inputs=QHBoxLayout();layout.addLayout(inputs);inputs.addWidget(QLabel('Recent data:'))
        self.input_recent_picker=QComboBox();self.input_recent_picker.setMinimumWidth(0);self.input_recent_picker.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);inputs.addWidget(self.input_recent_picker,1)
        self.input_recent_load=QPushButton('Load recent input');self.input_recent_load.clicked.connect(self.load_recent_input);inputs.addWidget(self.input_recent_load)
        self.input_recent_clear=QPushButton('Clear recents');self.input_recent_clear.clicked.connect(self.clear_recent_inputs);inputs.addWidget(self.input_recent_clear)
        self.refresh_recent_inputs()
        reuse=QHBoxLayout();layout.addLayout(reuse)
        reuse.addWidget(QLabel('Reuse scene settings:'))
        self.recent_picker=QComboBox();self.recent_picker.setMinimumWidth(0);self.recent_picker.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);reuse.addWidget(self.recent_picker,1)
        self.favourite_picker=QComboBox();self.favourite_picker.setMinimumWidth(0);self.favourite_picker.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);reuse.addWidget(self.favourite_picker,1)
        self.reuse_recent_button=QPushButton('Use recent');self.reuse_recent_button.clicked.connect(lambda:self.use_library_entry(self.recent_picker.currentData(),True));reuse.addWidget(self.reuse_recent_button)
        self.reuse_favourite_button=QPushButton('Use favourite');self.reuse_favourite_button.clicked.connect(lambda:self.use_library_entry(self.favourite_picker.currentData(),True));reuse.addWidget(self.reuse_favourite_button)
        split=QSplitter();layout.addWidget(split,1)
        self.tabs=QTabWidget();split.addWidget(self.tabs)
        self.detector_modes={};self.data_checks={};self.geometry_checks={};self.asset_fields={};self.color_buttons={};self.detector_labels={}
        self.build_detectors();self.build_components();self.build_appearance();self.build_render();self.build_runtime();self.build_library()
        right=QWidget();right_layout=QVBoxLayout(right);split.addWidget(right);split.setSizes([540,840])
        tools=QHBoxLayout();right_layout.addLayout(tools)
        self.all_button=QPushButton('Select all');self.none_button=QPushButton('Select none');tools.addWidget(self.all_button);tools.addWidget(self.none_button)
        self.selection_label=QLabel('0 events selected');tools.addWidget(self.selection_label,1)
        self.model=EventsModel();self.model.changed.connect(self.update_availability)
        self.all_button.clicked.connect(lambda:self.model.select_all(True));self.none_button.clicked.connect(lambda:self.model.select_all(False))
        self.table=QTableView();self.table.setModel(self.model);self.table.setAlternatingRowColors(True);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);self.table.horizontalHeader().setStretchLastSection(True);self.table.setMaximumHeight(290);right_layout.addWidget(self.table)
        self.image=QLabel('Preview will appear here');self.image.setAlignment(Qt.AlignCenter);self.image.setMinimumSize(400,260);self.image.setObjectName('preview');self.image.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Ignored)
        right_layout.addWidget(self.image,1)
        self.legend=QLabel('');self.legend.setWordWrap(True);right_layout.addWidget(self.legend)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(120);right_layout.addWidget(self.log)
        bottom=QHBoxLayout();layout.addLayout(bottom)
        self.render_progress=QProgressBar();self.render_progress.setRange(0,100);self.render_progress.setValue(0);bottom.addWidget(self.render_progress)
        self.status=QLabel('Ready');self.status.setMinimumWidth(0);self.status.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);bottom.addWidget(self.status,1)
        self.cancel_button=QPushButton('Cancel');self.cancel_button.setEnabled(False);self.cancel_button.clicked.connect(self.cancel_task);bottom.addWidget(self.cancel_button)
        self.load_config_button=QPushButton('Load config…');self.load_config_button.clicked.connect(self.import_scene);bottom.addWidget(self.load_config_button)
        self.export_config_button=QPushButton('Export config…');self.export_config_button.clicked.connect(self.export_scene);bottom.addWidget(self.export_config_button)
        self.fast_interactive=QCheckBox('Fast interactive');self.fast_interactive.setChecked(self.saved.get('fast_interactive',True));self.fast_interactive.setToolTip('Use reviewed cached approximate surfaces for detectors and magnet, with a 32-sample Eevee viewport. Full detail remains available in the editor.');bottom.addWidget(self.fast_interactive)
        self.editor_button=QPushButton('Interactive scene…');self.editor_button.clicked.connect(self.open_editor);bottom.addWidget(self.editor_button)
        self.preview_button=QPushButton('Preview first selected event');self.preview_button.clicked.connect(lambda:self.start_render(True));bottom.addWidget(self.preview_button)
        self.render_button=QPushButton('Render selected events');self.render_button.setObjectName('primary');self.render_button.clicked.connect(lambda:self.start_render(False));bottom.addWidget(self.render_button)
        self.update_availability()
        self.library.discover(Path(self.output.text()));self.refresh_library()
        self.geometry_lod.currentTextChanged.connect(self.refresh_components)
        for field in self.asset_fields.values():field.editingFinished.connect(self.refresh_components)
        self.refresh_components()
        self.library_timer=QTimer(self);self.library_timer.timeout.connect(self.refresh_library);self.library_timer.start(2000)
        self.setStyleSheet('''QWidget{background:#101724;color:#e2e8f2;font-size:13px;} QLabel#title{font-size:24px;font-weight:700;color:#94e5ff;margin:12px 0;} QLabel#preview{background:#070b14;border:1px solid #25334b;border-radius:8px;} QPushButton{background:#26334b;border:1px solid #40516f;padding:8px 12px;border-radius:5px;} QPushButton:hover{background:#344763;} QPushButton#primary{background:#147b89;border-color:#5ccdde;} QPushButton:disabled,QCheckBox:disabled{color:#586276;} QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QPlainTextEdit{background:#182236;border:1px solid #34435d;padding:6px;border-radius:4px;} QHeaderView::section{background:#26334b;padding:5px;border:0;} QTableView{alternate-background-color:#172034;gridline-color:#27344a;} QTabBar::tab{padding:10px;background:#182236;} QTabBar::tab:selected{background:#2b3b55;} QCheckBox{padding:4px;}''')

    def tab(self,name):
        widget=QWidget();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(widget);self.tabs.addTab(scroll,name);return widget
    def build_detectors(self):
        widget=self.tab('Detectors');layout=QVBoxLayout(widget)
        self.mode=QComboBox();self.mode.addItems(['tracks','clusters','both']);self.mode.setCurrentText(self.base.mode);self.mode.currentTextChanged.connect(self.set_all_detector_modes)
        form=QFormLayout();form.addRow('Set all object modes',self.mode);layout.addLayout(form)
        note=QLabel('Data controls are disabled when unavailable in the selected events. Tracks are trimmed to the selected source detectors when clipping is enabled.');note.setWordWrap(True);layout.addWidget(note)
        controls=QHBoxLayout();layout.addLayout(controls)
        none=QPushButton('Select no detectors');none.clicked.connect(self.select_no_detectors);controls.addWidget(none)
        complete=QPushButton('Show complete detectors');complete.clicked.connect(self.show_complete_detectors);controls.addWidget(complete)
        grid=QGridLayout();layout.addLayout(grid)
        for c,name in enumerate(['Detector','Data','Objects','Geometry','Colour']):grid.addWidget(QLabel(name),0,c)
        for row,name in enumerate(DETECTORS,1):
            data=QCheckBox();geometry=QCheckBox();geometry.setChecked(name in self.base.geometry)
            self.data_checks[name]=data;self.geometry_checks[name]=geometry
            geometry.toggled.connect(self.update_availability)
            data.clicked.connect(lambda checked=False:self.remember_detector_selection())
            mode=QComboBox();mode.addItems(['tracks','clusters','both']);mode.setCurrentText(self.base.detector_modes.get(name,self.base.mode));self.detector_modes[name]=mode
            label=QLabel(name);self.detector_labels[name]=label
            grid.addWidget(label,row,0);grid.addWidget(data,row,1);grid.addWidget(mode,row,2);grid.addWidget(geometry,row,3);grid.addWidget(self.color_button(name),row,4)
        self.magnet=QCheckBox('L3 magnet');self.magnet.setChecked(self.base.magnet);self.magnet.toggled.connect(self.update_availability);layout.addWidget(self.magnet)
        self.schematic=QCheckBox('Use approximate schematic envelopes');self.schematic.setChecked(self.base.schematic);self.schematic.setToolTip('Approximate dimensions, not calibrated detector geometry. This choice is recorded in render metadata.');layout.addWidget(self.schematic)
        self.cutaway=QCheckBox('Half cutaway (global Y plane)');self.cutaway.setChecked(self.base.cutaway);self.cutaway.toggled.connect(self.change_cutaway);layout.addWidget(self.cutaway)
        opening_note=QLabel('Opening direction is configurable per detector in the interactive editor: 0° is +X, 90° is +Y, −90° is −Y. The half-cutaway shortcut uses −Y. Show complete detectors resets opening angles.');opening_note.setWordWrap(True);layout.addWidget(opening_note)
        self.geometry_opening_label=QLabel();self.geometry_opening_label.setWordWrap(True);layout.addWidget(self.geometry_opening_label);self.refresh_opening_summary()
        self.geometry_lod=QComboBox();self.geometry_lod.addItems(['full','proxy','structural','simplified']);self.geometry_lod.setCurrentText(self.base.geometry_lod);layout.addWidget(QLabel('Geometry detail (proxy = cached approximate surfaces)'));layout.addWidget(self.geometry_lod)
        self.opacity=number(self.base.geometry_opacity,0,1,2);form=QFormLayout();form.addRow('Geometry opacity',self.opacity);layout.addLayout(form);layout.addStretch()
    def set_all_detector_modes(self,mode):
        for combo in self.detector_modes.values():combo.setCurrentText(mode)
        self.update_availability()
    def select_no_detectors(self):
        for box in (*self.data_checks.values(),*self.geometry_checks.values()):box.setChecked(False)
        self.magnet.setChecked(False)
        self.scene_detector_selection=set()
    def remember_detector_selection(self):
        self.scene_detector_selection={name for name,box in self.data_checks.items() if box.isChecked()}
    def change_cutaway(self,on):
        self.scene_overrides['geometry_openings']={name:180 if on else 0 for name in (*DETECTORS,'L3')}
        self.scene_overrides['geometry_opening_directions']={name:-90. for name in (*DETECTORS,'L3')}
        self.refresh_opening_summary()
    def show_complete_detectors(self):
        self.cutaway.setChecked(False);self.scene_overrides['geometry_openings']={name:0 for name in (*DETECTORS,'L3')}
        self.refresh_opening_summary()
    def refresh_opening_summary(self):
        values=self.scene_overrides.get('geometry_openings',{})
        directions=self.scene_overrides.get('geometry_opening_directions',{})
        text=', '.join(f'{name}: {angle:g}° toward {directions.get(name,-90.):g}° in XY' for name,angle in values.items() if angle)
        self.geometry_opening_label.setText('Configured openings: '+(text or 'complete surfaces'))
    def color_button(self,key):
        button=QPushButton(self.base.colors.get(key,'#243a82'));button.clicked.connect(lambda:self.pick_color(key));self.color_buttons[key]=button;return button
    def pick_color(self,key):
        from PySide6.QtWidgets import QColorDialog
        color=QColorDialog.getColor(QColor(self.color_buttons[key].text()),self,'Choose '+key+' colour')
        if color.isValid():
            self.color_buttons[key].setText(color.name());self.scene_overrides.get('colors_linear',{}).pop(key,None)
    def build_appearance(self):
        widget=self.tab('Appearance');layout=QFormLayout(widget)
        self.defaults_button=QPushButton('Use commissioning defaults');self.defaults_button.clicked.connect(self.use_commissioning_defaults);layout.addRow(self.defaults_button)
        self.track_mode=QComboBox();self.cluster_mode=QComboBox()
        for combo in (self.track_mode,self.cluster_mode):combo.setMinimumWidth(0);combo.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        for combo in (self.track_mode,self.cluster_mode):
            combo.addItems(COLOR_FIELDS);combo.setItemData(combo.findText('matching'),'0 = standalone fitted source; 1 = composite matched source (e.g. ITS-TPC); grey = unknown',Qt.ToolTipRole)
        self.cluster_mode.addItems(CLUSTER_COLOR_FIELDS)
        for mode in CLUSTER_COLOR_FIELDS:self.cluster_mode.setItemData(self.cluster_mode.findText(mode),DESCRIPTIONS[mode],Qt.ToolTipRole)
        self.track_mode.setCurrentText(self.base.track_color_mode);self.cluster_mode.setCurrentText(self.base.cluster_color_mode)
        layout.addRow('Track colouring',self.track_mode);layout.addRow('Cluster colouring',self.cluster_mode)
        note=QLabel('Unavailable quantities are disabled. XYZ colours refer to the first sampled point of a track or the cluster position. Unknown values use grey. p and pT are in GeV/c; angles in radians; coordinates and DCA in cm.');note.setWordWrap(True);layout.addRow(note)
        for key in ('tracks','clusters','background','magnet'):layout.addRow(key.capitalize(),self.color_button(key))
        self.palette=QComboBox();self.palette.addItems(palette_names());
        if self.palette.findText(self.base.palette)<0:self.palette.addItem(self.base.palette)
        self.palette.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);self.palette.setMinimumContentsLength(16);self.palette.setCurrentText(self.base.palette);layout.addRow('Colour scale',self.palette);self.palette.currentTextChanged.connect(lambda *_:self.scene_overrides.pop('palette_lut',None))
        self.auto_range=QCheckBox('Automatic scale range per event');self.auto_range.setChecked(self.base.scale_min is None);layout.addRow(self.auto_range)
        self.minimum=number(self.base.scale_min or 0,-1000000,1000000,3);self.maximum=number(self.base.scale_max or 10,-1000000,1000000,3);layout.addRow('Minimum',self.minimum);layout.addRow('Maximum',self.maximum)
        self.track_radius=number(self.base.track_radius_cm*2,.002,20,3);self.cluster_radius=number(self.base.cluster_radius_cm,.001,20,3);layout.addRow('Track linewidth (cm)',self.track_radius);self.clip_tracks=QCheckBox('Clip tracks to selected detectors');self.clip_tracks.setChecked(self.base.clip_tracks);layout.addRow(self.clip_tracks);self.include_ambiguous=QCheckBox('Include tracks ambiguously associated to several vertices');self.include_ambiguous.setChecked(self.base.include_ambiguous_tracks);layout.addRow(self.include_ambiguous);layout.addRow('Cluster radius (cm)',self.cluster_radius)
        self.view_transform=QComboBox();self.view_transform.addItems(['AgX','Standard']);self.view_transform.setCurrentText(self.base.view_transform);layout.addRow('Display colours',self.view_transform)
        self.exposure=number(self.base.exposure,-20,20,2);layout.addRow('Exposure (stops)',self.exposure)
        self.track_emission=number(self.base.track_emission,0,100,2);self.cluster_emission=number(self.base.cluster_emission,0,100,2);layout.addRow('Track glow',self.track_emission);layout.addRow('Cluster glow',self.cluster_emission)
        self.tpc_profile=QComboBox();self.tpc_profile.addItems(['sphere','ellipse','gaussian']);self.tpc_profile.setCurrentText(self.base.tpc_cluster_profile);layout.addRow('TPC cluster profile',self.tpc_profile)
        self.tpc_profile.setToolTip('Measured pad/time RMS; Gaussian uses weighted translucent shells. Missing widths retain spheres.')
        self.tpc_profile_scale=number(self.base.tpc_profile_scale,.01,100,2);layout.addRow('TPC profile sigma scale',self.tpc_profile_scale)
        self.tpc_profile_thickness=number(self.base.tpc_profile_thickness_cm,.001,10,3);layout.addRow('TPC profile display thickness (cm)',self.tpc_profile_thickness)
        self.detector_setup=QComboBox();self.detector_setup.addItems(SETUP_PRESETS);self.detector_setup.setCurrentText(self.base.detector_setup);setup_button=QPushButton('Apply detector setup defaults');setup_button.clicked.connect(self.use_detector_defaults);layout.addRow('Detector setup',self.detector_setup);layout.addRow(setup_button)
        self.data_glow_lighting=QCheckBox('Data glow lights geometry');self.data_glow_lighting.setChecked(self.base.data_glow_lighting);layout.addRow(self.data_glow_lighting)
        self.highlight_ids=QLineEdit(', '.join(self.base.highlight_track_ids));self.highlight_ids.setPlaceholderText('Track IDs: 11730, 50331650, …');layout.addRow('Special track IDs',self.highlight_ids)
        self.highlight_width=number(self.base.highlight_track_radius_cm*2,.002,20,3);layout.addRow('Special track linewidth (cm)',self.highlight_width)
        self.highlight_clusters=number(self.base.highlight_cluster_radius_cm,.001,20,3);layout.addRow('Linked cluster radius (cm)',self.highlight_clusters)
        self.highlight_override=QCheckBox('Use special colours');self.highlight_override.setChecked(self.base.highlight_override_color);layout.addRow(self.highlight_override)
        for key,value in [('highlight_track_color',self.base.highlight_track_color),('highlight_cluster_color',self.base.highlight_cluster_color)]:
            button=QPushButton(value);button.clicked.connect(lambda _,b=button:self.pick_special_color(b));setattr(self,key,button);layout.addRow(key.replace('_',' ').capitalize(),button)
    def pick_special_color(self,button):
        from PySide6.QtWidgets import QColorDialog
        color=QColorDialog.getColor(QColor(button.text()),self,'Choose special colour')
        if color.isValid():button.setText(color.name())
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
        self.camera_lens=number(self.base.camera_pose.get('lens',self.base.camera_lens_mm),.1,5000,2);layout.addRow('Focal length (mm)',self.camera_lens)
        self.camera_orbit_axis=QComboBox();self.camera_orbit_axis.addItems(['Y','Z']);self.camera_orbit_axis.setCurrentText(self.base.camera_orbit_axis);self.camera_orbit_axis.setToolTip('Y keeps ALICE XZ as the horizontal plane; Z reproduces the legacy orbit');layout.addRow('Vertical orbit axis',self.camera_orbit_axis);self.camera_orbit_axis.currentTextChanged.connect(lambda *_:self.scene_overrides.pop('camera_pose',None))
        self.azimuth=number(self.base.azimuth,-180,180,1);self.elevation=number(self.base.elevation,-90,90,1);self.distance=number(self.base.distance_cm,1,100000,1)
        self.roll=number(self.base.roll,-360,360,1);layout.addRow('Camera roll (°)',self.roll)
        layout.addRow('Azimuth (°)',self.azimuth);layout.addRow('Elevation (°)',self.elevation);layout.addRow('Distance (cm)',self.distance)
        self.target=[]
        for axis,val in zip('XYZ',self.base.target_cm):
            spin=number(val,-100000,100000,1);self.target.append(spin);layout.addRow('Target '+axis+' (cm)',spin)
        for field in [self.azimuth,self.elevation,self.roll,self.distance,*self.target]:field.valueChanged.connect(lambda *_:self.scene_overrides.pop('camera_pose',None))
        self.output=QLineEdit(self.saved.get('output',str(ROOT/'renders')));layout.addRow('Output directory',self.path_field(self.output,folder=True))
    def build_runtime(self):
        widget=self.tab('Setup');layout=QFormLayout(widget)
        self.blender=QLineEdit(self.saved.get('blender',find_blender()));layout.addRow('Blender executable',self.path_field(self.blender))
        default_profile=ROOT/'profiles/virgo4-ingest.json'
        self.profile=QLineEdit(self.saved.get('profile') or (str(default_profile) if default_profile.is_file() else ''));layout.addRow('O2 ingestion profile',self.path_field(self.profile))
        aod=self.saved.get('aod',{})
        self.aod_conditions=QLineEdit(aod.get('conditions',''));layout.addRow('AO2D field conditions (optional)',self.path_field(self.aod_conditions))
        self.aod_use_bz=QCheckBox('Use an explicit signed AO2D Bz (kG)');self.aod_use_bz.setChecked(aod.get('bz_kG') is not None);layout.addRow(self.aod_use_bz)
        self.aod_bz=number(aod.get('bz_kG') or 0.,-100,100,3);layout.addRow('AO2D Bz (kG)',self.aod_bz)
        note=QLabel('AO2D tables load without O2. Fitted-state display curves require field conditions or an explicit Bz; adjacent FILE.root.renderer.json is detected automatically. Reload the input after changing these settings. AO2D does not supply track-attached cluster coordinates.');note.setWordWrap(True);layout.addRow(note)
        note=QLabel('Raw TF/CTF inputs require ALICE O2 decoding/reconstruction and complete primary-vertex export. An O2 profile provides the command and prerequisite checks. Exported event JSON renders without O2. See docs/O2-INTEGRATION.md.');note.setWordWrap(True);layout.addRow(note)
        self.geometry_units=QComboBox();self.geometry_units.addItems(['cm','m']);self.geometry_units.setCurrentText(self.base.geometry_units);layout.addRow('Geometry asset units',self.geometry_units)
        note=QLabel('Each asset must contain only the named detector in ALICE global XYZ coordinates. GLB/glTF, OBJ and Blender files are supported. Preserve run/alignment provenance with the assets.');note.setWordWrap(True);layout.addRow(note)
        for name in (*DETECTORS,'L3'):
            field=QLineEdit(self.base.geometry_assets.get(name,''));self.asset_fields[name]=field;layout.addRow(name+' geometry',self.path_field(field))
    def build_library(self):
        self.library_lists={}
        for favourites,title in ((False,'Recent scenes'),(True,'Favourites')):
            widget=self.tab(title);layout=QVBoxLayout(widget)
            note=QLabel('Reload the original event, or reuse camera, colours, lights and surfaces for the input/event currently selected. Favourites keep a fixed snapshot.');note.setWordWrap(True);layout.addWidget(note)
            listing=QListWidget();self.library_lists[favourites]=listing;layout.addWidget(listing)
            def selected(listing=listing):
                item=listing.currentItem();return item.data(Qt.UserRole) if item else None
            for label,action in (
                ('Reload scene and original event',lambda checked=False,get=selected:self.use_library_entry(get(),False)),
                ('Use for current input / event',lambda checked=False,get=selected:self.use_library_entry(get(),True)),
                ('Remove favourite' if favourites else 'Add to favourites…',lambda checked=False,get=selected,remove=favourites:self.change_favourite(get(),remove)),
                ('Refresh',self.discover_library)):
                button=QPushButton(label);button.clicked.connect(action);layout.addWidget(button)
    def discover_library(self):
        self.library.discover(Path(self.output.text()));self.library_signature=None;self.refresh_library()
    def refresh_library(self):
        recent=self.library.entries();favourites=self.library.entries(True)
        signature=json.dumps([recent,favourites],sort_keys=True)
        if signature==self.library_signature:return
        self.library_signature=signature
        for combo,entries,label in ((self.recent_picker,recent,'Recent scenes…'),(self.favourite_picker,favourites,'Favourites…')):
            chosen=combo.currentData();chosen_id=chosen.get('id') if chosen else None
            combo.clear();combo.addItem(label,None)
            for entry in entries:
                combo.addItem(('★ ' if entry['favourite'] else '')+entry['title'],entry)
                combo.setItemData(combo.count()-1,entry['config'],Qt.ToolTipRole)
                if entry['id']==chosen_id:combo.setCurrentIndex(combo.count()-1)
        for is_favourite,listing in self.library_lists.items():
            old=listing.currentItem();chosen_id=old.data(Qt.UserRole)['id'] if old else None
            listing.clear()
            for entry in favourites if is_favourite else recent:
                item=QListWidgetItem(('★ ' if entry['favourite'] else '')+entry['title']);item.setData(Qt.UserRole,entry);item.setToolTip(entry['config']+'\n'+entry['input']);listing.addItem(item)
                if entry['id']==chosen_id:listing.setCurrentItem(item)
    def change_favourite(self,entry,remove=False):
        if not entry:return
        try:
            if remove:self.library.unfavourite(entry)
            else:
                title,ok=QInputDialog.getText(self,'Save favourite','Name',text=entry['title'])
                if not ok:return
                self.library.favourite(entry,title=title.strip() or entry['title'])
            self.refresh_library()
        except Exception as exc:self.failure(str(exc))
    def use_library_entry(self,entry,reuse=True):
        if not entry:return
        try:
            assets={k:v.text() for k,v in self.asset_fields.items() if v.text()}
            cfg=self.library.settings(entry,reuse=reuse,assets=assets or None,geometry_units=self.geometry_units.currentText() if assets else None)
            if not reuse:
                if not entry['input'] or not Path(entry['input']).exists():raise ValueError('Original input is unavailable. Choose a local input and use “Use for current input / event”.')
                if not entry['event']:raise ValueError('This config has no original event. Use it for the current input/event.')
            self.apply_scene(cfg)
            if reuse:self.message('Scene settings reused. Input and event selection retained; event-specific highlighted track IDs cleared.')
            else:self.load_input(entry['input'],event_selector=entry['event'],retain_scene_geometry=True)
        except Exception as exc:self.failure(str(exc))
    def register_scene(self,path,kind,cfg):
        event=str(next(r['event_id'] for r in self.model.rows if r['ordinal']==min(self.model.selected))) if self.model.selected else ''
        self.library.register(path,kind=kind,input_path=self.loaded_input or self.source.text(),event=event,assets=cfg.geometry_assets);self.refresh_library()

    def path_field(self,line,folder=False):
        widget=QWidget();layout=QHBoxLayout(widget);layout.setContentsMargins(0,0,0,0);layout.addWidget(line)
        button=QPushButton('…');button.setMaximumWidth(36)
        def choose():
            path=QFileDialog.getExistingDirectory(self,'Select folder') if folder else QFileDialog.getOpenFileName(self,'Select file')[0]
            if path:line.setText(path)
        button.clicked.connect(choose);layout.addWidget(button);return widget

    def settings(self):
        cfg=RenderSettings(detectors=[d for d,c in self.data_checks.items() if c.isChecked() and c.isEnabled()],geometry=[d for d,c in self.geometry_checks.items() if c.isChecked()],magnet=self.magnet.isChecked(),mode=self.mode.currentText(),track_color_mode=self.track_mode.currentText(),cluster_color_mode=self.cluster_mode.currentText(),colors={k:b.text() for k,b in self.color_buttons.items()},scale_min=None if self.auto_range.isChecked() else self.minimum.value(),scale_max=None if self.auto_range.isChecked() else self.maximum.value(),palette=self.palette.currentText(),geometry_assets={k:v.text() for k,v in self.asset_fields.items() if v.text()},geometry_units=self.geometry_units.currentText(),geometry_opacity=self.opacity.value(),cutaway=self.cutaway.isChecked(),schematic=self.schematic.isChecked(),width=self.width.value(),height=self.height.value(),samples=self.samples.value(),denoise=self.denoise.isChecked(),backend=self.backend.currentText(),device=self.device.currentData() or '',threads=self.threads.value(),track_radius_cm=self.track_radius.value()/2,cluster_radius_cm=self.cluster_radius.value(),camera=self.camera.currentText(),azimuth=self.azimuth.value(),elevation=self.elevation.value(),distance_cm=self.distance.value(),target_cm=[s.value() for s in self.target],save_blend=self.save_blend.isChecked())
        for key,value in self.scene_overrides.items():setattr(cfg,key,value)
        cfg.detector_modes={name:combo.currentText() for name,combo in self.detector_modes.items()}
        cfg.highlight_track_ids=parse_track_ids(self.highlight_ids.text());cfg.highlight_track_radius_cm=self.highlight_width.value()/2;cfg.highlight_cluster_radius_cm=self.highlight_clusters.value();cfg.highlight_override_color=self.highlight_override.isChecked();cfg.highlight_track_color=self.highlight_track_color.text();cfg.highlight_cluster_color=self.highlight_cluster_color.text();cfg.roll=self.roll.value()
        cfg.clip_tracks=self.clip_tracks.isChecked();cfg.include_ambiguous_tracks=self.include_ambiguous.isChecked()
        cfg.camera_orbit_axis=self.camera_orbit_axis.currentText()
        cfg.geometry_lod=self.geometry_lod.currentText()
        cfg.view_transform=self.view_transform.currentText();cfg.exposure=self.exposure.value();cfg.track_emission=self.track_emission.value();cfg.cluster_emission=self.cluster_emission.value()
        cfg.tpc_cluster_profile=self.tpc_profile.currentText();cfg.tpc_profile_scale=self.tpc_profile_scale.value();cfg.tpc_profile_thickness_cm=self.tpc_profile_thickness.value()
        cfg.data_glow_lighting=self.data_glow_lighting.isChecked()
        cfg.camera_lens_mm=self.camera_lens.value()
        if cfg.camera_pose:cfg.camera_pose={**cfg.camera_pose,'lens':cfg.camera_lens_mm}
        cfg.frame_aspect=cfg.width/cfg.height
        return cfg.validate()
    def save_settings(self,cfg):
        saved={'fast_interactive':self.fast_interactive.isChecked(),'render':cfg.to_dict(),'blender':self.blender.text(),'profile':self.profile.text(),'output':self.output.text(),'aod':self.aod_options()}
        self.settings_file.write_text(json.dumps(saved,indent=2))
    def aod_options(self):
        return {'conditions':self.aod_conditions.text(),'bz_kG':self.aod_bz.value() if self.aod_use_bz.isChecked() else None}
    def busy(self,on):
        self.render_progress.setRange(0,0 if on else 100)
        for w in (self.fast_interactive,self.input_recent_picker,self.input_recent_load,self.input_recent_clear,self.tabs,self.source,self.open_button,self.browse_button,self.folder_button,self.demo_button,self.table,self.all_button,self.none_button,self.preview_button,self.render_button,self.editor_button,self.export_config_button,self.load_config_button,self.recent_picker,self.favourite_picker,self.reuse_recent_button,self.reuse_favourite_button):w.setEnabled(not on)
        self.cancel_button.setEnabled(on)
        self.timeframe_button.setEnabled(not on and self.timeframe_source is not None)
        if not on:self.update_availability();self.refresh_recent_inputs()
    def start_task(self,fn,done):
        if self.task and self.task.isRunning():return
        self.busy(True);self.task=Task(fn,self);self.task.message.connect(self.message)
        self.task.result.connect(done);self.task.failed.connect(self.failure);self.task.cancelled.connect(self.message);self.task.finished.connect(self.task_finished);self.task.start()
    def task_finished(self):
        self.busy(False)
        if self.close_pending:self.close()
    def message(self,text):
        import re
        match=re.search(r'Render progress: (\d+)%',text)
        if match:self.render_progress.setRange(0,100);self.render_progress.setValue(int(match[1]))
        self.status.setText(text);self.status.setToolTip(text);self.log.appendPlainText(text)
        if text.endswith('/render.png') and Path(text).exists():self.show_image(Path(text))
    def failure(self,text):
        self.status.setText('Action stopped — see prerequisites or details');self.log.appendPlainText(text)
        if not self.close_pending:QMessageBox.warning(self,'Unable to continue',text)
    def cancel_task(self):
        if self.task:self.task.cancel.set();self.status.setText('Cancelling…')
    def refresh_recent_inputs(self):
        selected=self.input_recent_picker.currentData()
        self.input_recent_picker.clear()
        for path in self.library.recent_inputs():
            self.input_recent_picker.addItem(path+(' (missing)' if not Path(path).exists() else ''),path)
            self.input_recent_picker.setItemData(self.input_recent_picker.count()-1,path,Qt.ToolTipRole)
        index=self.input_recent_picker.findData(selected)
        if index>=0:self.input_recent_picker.setCurrentIndex(index)
        enabled=bool(self.input_recent_picker.count())
        for widget in (self.input_recent_picker,self.input_recent_load,self.input_recent_clear):widget.setEnabled(enabled)
    def load_recent_input(self):
        if self.task and self.task.isRunning():return
        path=self.input_recent_picker.currentData()
        if path:self.load_input(path)
    def clear_recent_inputs(self):
        self.library.clear_recent_inputs();self.refresh_recent_inputs()
    def load_typed_input(self):
        if self.task and self.task.isRunning():return
        text=self.source.text().strip()
        if not text:self.open_input();return
        if len(text)>1 and text[0]==text[-1] and text[0] in ("'",'"'):text=text[1:-1]
        if text.startswith('file://'):
            from PySide6.QtCore import QUrl
            text=QUrl(text).toLocalFile()
        self.load_input(Path(text).expanduser())
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
    def load_input(self,path,event_selector=None,retain_scene_geometry=False):
        retain_scene_geometry=retain_scene_geometry or self.scene_overrides.get('detector_setup','ALICE2')!='ALICE2'
        path=Path(path).expanduser()
        if path.is_dir() and not any(path.glob('*.json*')):
            candidates=sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in ('.tf','.rawtf','.root','.ctf'))
            if len(candidates)==1:path=candidates[0]
            elif candidates:
                name,ok=QInputDialog.getItem(self,'Choose input in folder','TF / CTF file',[p.name for p in candidates],0,False)
                if not ok:return
                path=path/name
        self.source.setText(str(path));profile=self.profile.text();aod_options=self.aod_options()
        def work(progress,cancelled):
            info=inspect_input(path,cancelled=cancelled);progress(f'{info.format}: {info.timeframes if info.timeframes is not None else "exported"} timeframe entries; detectors {", ".join(info.detectors) or "not yet decoded"}')
            for warning in info.warnings:progress(warning)
            source=path
            if info.format not in ('events','aod'):
                if not profile:raise ValueError('This input requires O2 decoding/reconstruction before collision events can be listed. Set an O2 ingestion profile in Setup. Blender rendering of exported event JSON does not require O2. See docs/O2-INTEGRATION.md.')
                source=run_ingest_profile(path,Path(profile),ROOT/'cache',progress=progress,cancelled=cancelled)
            cat=Catalogue.build(source,ROOT/'cache',convert=convert,progress=progress,cancelled=cancelled,aod_options=aod_options)
            return cat,info
        def done(result):
            self.loaded_input=self.source.text()
            self.catalogue,info=result;self.model.set_rows(self.catalogue.rows());self.summary.setText(f'{len(self.model.rows)} records loaded · grouping is shown explicitly · {Path(info.path).name}')
            if info.format=='aod' and event_selector is None:
                self.model.select_all(False)
                if self.model.rows:self.model.selected={self.model.rows[0]['ordinal']};self.update_availability()
            with sqlite3.connect(self.catalogue.db) as database:
                exported_source=Path(database.execute("SELECT value FROM metadata WHERE key='source'").fetchone()[0])
            manifest_path=(exported_source if exported_source.is_dir() else exported_source.parent)/'manifest.json'
            self.timeframe_source=None;self.collision_source=None;self.showing_timeframes=False
            if manifest_path.exists():
                try:
                    manifest=json.loads(manifest_path.read_text())
                    for name,path in manifest.get('geometry_assets',{}).items():
                        if not retain_scene_geometry and name in self.asset_fields and isinstance(path,str):
                            local=local_geometry_asset(path,manifest_path,ROOT)
                            if local:self.asset_fields[name].setText(local)
                            elif not Path(self.asset_fields[name].text()).is_file():
                                self.asset_fields[name].clear()
                                self.message(f'{name}: exported geometry is unavailable locally; choose its asset in Setup.')
                    if not retain_scene_geometry and manifest.get('geometry_units') in ('cm','m'):self.geometry_units.setCurrentText(manifest['geometry_units'])
                    if manifest.get('timeframe_events_file')=='timeframe-events.jsonl.gz' and manifest.get('events_file') in ('events.jsonl','events.jsonl.gz'):
                        frames=manifest_path.parent/'timeframe-events.jsonl.gz';collisions=manifest_path.parent/manifest['events_file']
                        if frames.is_file() and collisions.is_file():
                            self.timeframe_source=frames;self.collision_source=collisions;self.showing_timeframes=exported_source.resolve()==frames.resolve()
                except (OSError,ValueError,AttributeError,TypeError):self.message('Geometry metadata could not be loaded; configure assets in Setup.')
            self.timeframe_button.setText('Collision events' if self.showing_timeframes else 'Whole-TF detector views')
            if not self.model.rows:self.failure('Event catalogue is empty; regenerate the input catalogue');return
            if event_selector is not None:
                matches={r['ordinal'] for r in self.model.rows if str(r['event_id'])==str(event_selector)}
                if len(matches)!=1:self.failure('The original event was not found in this input');self.model.select_all(False);return
                self.model.select_all(False);self.model.selected=matches;self.model.dataChanged.emit(self.model.index(0,0),self.model.index(len(self.model.rows)-1,0),[Qt.CheckStateRole]);self.update_availability()
            available={d for row in self.model.rows if row['ordinal'] in self.model.selected for d in json.loads(row['detectors'])}
            for d,c in self.data_checks.items():c.setChecked(d in available and (self.scene_detector_selection is None or d in self.scene_detector_selection))
            if self.requested_modes:
                self.track_mode.setCurrentText(self.requested_modes[0]);self.cluster_mode.setCurrentText(self.requested_modes[1])
            if info.format!='aod':
                first=self.catalogue.load(self.model.rows[0]['ordinal'])
                for warning in first.get('warnings',[]):self.message(warning)
            self.library.remember_input(self.loaded_input);self.refresh_recent_inputs()
            self.status.setText('Events ready')
        self.start_task(work,done)
    def update_availability(self):
        if not hasattr(self,'model'):return
        rows=[r for r in self.model.rows if r['ordinal'] in self.model.selected]
        available={d for r in rows for d in json.loads(r['detectors'])}
        for name,box in self.data_checks.items():
            was=box.isEnabled();box.setEnabled(name in available);box.setToolTip('Available in selected records' if name in available else 'No exported data for this detector in selected records')
            self.detector_modes[name].setEnabled(name in available)
            self.detector_labels[name].setStyleSheet('color:#e2e8f2' if name in available else 'color:#586276')
            if name not in available:box.setChecked(False)
            elif not was:box.setChecked(self.scene_detector_selection is None or name in self.scene_detector_selection)
        for combo,field in ((self.track_mode,'track_fields'),(self.cluster_mode,'cluster_fields')):
            supported=set(json.loads(rows[0][field])) if rows else {'solid'}
            for row in rows[1:]:supported&=set(json.loads(row[field]))
            for mode in sorted(supported):
                if combo.findText(mode)<0:combo.addItem(mode)
            if not rows:supported={'solid'}
            for i in range(combo.count()):combo.model().item(i).setEnabled(combo.itemText(i) in supported)
            if combo.currentText() not in supported and not self.requested_modes:combo.setCurrentText('solid')
        self.selection_label.setText(f'{len(rows)} / {len(self.model.rows)} selected')
        renderable=bool(rows) or any(c.isChecked() for c in self.geometry_checks.values()) or self.magnet.isChecked()
        self.preview_button.setEnabled(renderable);self.render_button.setEnabled(renderable);self.editor_button.setEnabled(renderable)
        self.preview_button.setText('Preview first selected event' if rows else 'Preview geometry only')
        self.render_button.setText('Render selected events' if rows else 'Render geometry only')
    def check_devices(self):
        def done(info):
            self.device_info=info;self.device_label.setText(info['version_string']+' · '+', '.join(d['name']+' ('+d['type']+')' for d in info['devices']));self.update_devices()
        blender=self.blender.text();self.start_task(lambda p,c:probe(blender),done)
    def build_components(self):
        page=QWidget();layout=QVBoxLayout(page)
        self.component_detector=QComboBox();self.component_detector.addItems([*DETECTORS,'L3']);layout.addWidget(self.component_detector)
        note=QLabel('Uncheck layers, walls, services or individual elements. These controls affect surfaces, not event data. Explicitly checking a component restores it from legacy name masks.');note.setWordWrap(True);layout.addWidget(note)
        self.component_tree=QTreeWidget();self.component_tree.setHeaderLabels(['Detector component','Placements']);layout.addWidget(self.component_tree,1)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        reset=QPushButton('Reset component choices');reset.clicked.connect(self.reset_components);buttons.addWidget(reset)
        refresh=QPushButton('Refresh asset components');refresh.clicked.connect(self.refresh_components);buttons.addWidget(refresh)
        self.tabs.addTab(page,'Components');self.component_detector.currentTextChanged.connect(self.refresh_components);self.component_tree.itemChanged.connect(self.component_changed)
        self.refresh_components()
    def refresh_components(self,*_):
        from .geometry_components import load_components,component_visibility
        name=self.component_detector.currentText();field=self.asset_fields.get(name);path=field.text().strip() if field else ''
        self.component_tree.blockSignals(True);self.component_tree.clear()
        try:
            data=load_components(path,verify=False) if path and Path(path).is_file() else None
            if not data:
                QTreeWidgetItem(self.component_tree,['No component metadata for this asset','']);return
            choices=self.scene_overrides.get('geometry_components',{}).get(name,{})
            large=self.scene_overrides.get('geometry_lods',{}).get(name,self.geometry_lod.currentText()) in ('structural','proxy')
            supported=None
            if large:
                from .structural_geometry import load,supported_components
                if self.scene_overrides.get('geometry_lods',{}).get(name,self.geometry_lod.currentText())=='proxy':
                    from .surface_proxy import load
                supported=supported_components(load(path,self.geometry_units.currentText()))
            visibility=component_visibility(data,choices,self.scene_overrides.get('geometry_exclusions',{}).get(name,[]))
            nodes={}
            for identifier,entry in sorted(data['components'].items(),key=lambda kv:(kv[0].count('/'),kv[0])):
                parent=nodes.get(entry['parent'],self.component_tree);item=QTreeWidgetItem(parent,[entry['label'],str(entry['count'])]);item.setData(0,Qt.UserRole,identifier)
                item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(0,Qt.PartiallyChecked if visibility[identifier] is None else Qt.Checked if visibility[identifier] else Qt.Unchecked);nodes[identifier]=item
                if supported is not None and identifier not in supported:
                    item.setFlags(item.flags()&~Qt.ItemIsEnabled);item.setToolTip(0,'Fine component omitted from large-surface geometry; choose full detail to display it')
            self.component_tree.expandToDepth(0)
        except Exception as exc:QTreeWidgetItem(self.component_tree,[str(exc),''])
        finally:self.component_tree.blockSignals(False)
    def component_changed(self,item,column):
        identifier=item.data(0,Qt.UserRole)
        if not identifier:return
        choices=self.scene_overrides.setdefault('geometry_components',{}).setdefault(self.component_detector.currentText(),{})
        # A parent toggle resets its descendants so checking Layers restores all.
        for key in list(choices):
            if key.startswith(identifier+'/'):del choices[key]
        choices[identifier]=item.checkState(0)==Qt.Checked;self.refresh_components()
    def reset_components(self):
        self.scene_overrides.setdefault('geometry_components',{}).pop(self.component_detector.currentText(),None);self.refresh_components()
    def update_devices(self):
        if not self.device_info:return
        self.device.clear();self.device.addItem('All devices in selected backend','')
        for d in self.device_info['devices']:
            if d['type']==self.backend.currentText():self.device.addItem(d['name'],d['id'])
        for i in range(self.backend.count()):self.backend.model().item(i).setEnabled(any(d['type']==self.backend.itemText(i) for d in self.device_info['devices']))
    def export_scene(self):
        try:
            cfg=self.settings();catalogue=self.catalogue;ordinal=min(self.model.selected) if catalogue and self.model.selected else None
            path=QFileDialog.getSaveFileName(self,'Export portable scene','scene-config.json','Scene config (*.json)')[0]
            if not path:return
            def work(progress,cancelled):
                event=load_event(catalogue.event_path(ordinal,progress=progress,cancelled=cancelled)) if ordinal is not None else None
                save_config(path,recipe(cfg,event));return path
            def done(result):self.register_scene(result,'export',cfg);self.message('Portable scene exported: '+result)
            self.start_task(work,done)
        except Exception as exc:self.failure(str(exc))
    def import_scene(self):
        path=QFileDialog.getOpenFileName(self,'Load portable scene','','Scene config (*.json)')[0]
        if not path:return
        try:
            data=load_config(path);root=Path(path).parent
            from .scene_config import sha256
            # A portable recipe names geometry files, not this machine's paths.
            # Reuse already configured assets only when their saved hashes match.
            available={}
            for name,field in self.asset_fields.items():
                asset=Path(field.text()).expanduser()
                ref=data['geometry'].get(name)
                if asset.is_file() and (ref is None or sha256(asset)==ref['sha256']):available[name]=str(asset.resolve())
            if any(name not in available and not (root/ref['file']).is_file() for name,ref in data['geometry'].items()):
                chosen=QFileDialog.getExistingDirectory(self,'Choose the matching geometry bundle')
                if not chosen:return
                root=Path(chosen)
            cfg=resolve_settings(data,path,root,asset_overrides=available)
            self.apply_scene(cfg);self.register_scene(path,'config',cfg);self.message('Scene loaded. Choose the local input and event, then preview or render.')
        except Exception as exc:self.failure(str(exc))
    def apply_scene(self,cfg):
        self.detector_setup.setCurrentText(cfg.detector_setup)
        self.scene_detector_selection=set(cfg.detectors);self.requested_modes=(cfg.track_color_mode,cfg.cluster_color_mode)
        if self.palette.findText(cfg.palette)<0:self.palette.addItem(cfg.palette)
        for combo,mode in ((self.track_mode,cfg.track_color_mode),(self.cluster_mode,cfg.cluster_color_mode)):
            if combo.findText(mode)<0:combo.addItem(mode)
        self.scene_overrides={key:getattr(cfg,key) for key in ('render_engine','detector_setup','camera_pose','color_ranges','geometry_lod','geometry_lods','geometry_schematics','geometry_display','geometry_openings','geometry_opening_directions','geometry_exclusions','geometry_inner_masks','geometry_components','geometry_opacities','roughness','metallic','shading','world_strength','lights','colors_linear','palette_lut')}
        for name,box in self.data_checks.items():box.setChecked(name in cfg.detectors)
        for name,combo in self.detector_modes.items():combo.setCurrentText(cfg.detector_modes.get(name,cfg.mode))
        for name,box in self.geometry_checks.items():box.setChecked(name in cfg.geometry)
        for name,field in self.asset_fields.items():field.setText(cfg.geometry_assets.get(name,''))
        for name,button in self.color_buttons.items():
            button.setText(cfg.colors.get(name,'#243a82'));button.setStyleSheet('background:'+cfg.colors.get(name,'#243a82'))
        for name,value in [('mode',cfg.mode),('track_mode',cfg.track_color_mode),('cluster_mode',cfg.cluster_color_mode),('palette',cfg.palette),('camera',cfg.camera),('camera_orbit_axis',cfg.camera_orbit_axis),('geometry_units',cfg.geometry_units)]:getattr(self,name).setCurrentText(value)
        for name,value in [('opacity',cfg.geometry_opacity),('track_radius',cfg.track_radius_cm*2),('cluster_radius',cfg.cluster_radius_cm),('azimuth',cfg.azimuth),('elevation',cfg.elevation),('distance',cfg.distance_cm)]:getattr(self,name).setValue(value)
        for spin,value in zip(self.target,cfg.target_cm):spin.setValue(value)
        self.geometry_lod.setCurrentText(cfg.geometry_lod)
        self.clip_tracks.setChecked(cfg.clip_tracks);self.include_ambiguous.setChecked(cfg.include_ambiguous_tracks)
        self.magnet.setChecked(cfg.magnet);self.cutaway.setChecked(cfg.cutaway);self.schematic.setChecked(cfg.schematic)
        self.auto_range.setChecked(cfg.scale_min is None)
        if cfg.scale_min is not None:self.minimum.setValue(cfg.scale_min)
        if cfg.scale_max is not None:self.maximum.setValue(cfg.scale_max)
        w,h=percentage_size(25,cfg.frame_aspect);self.width.setValue(w);self.height.setValue(h)
        for name,combo in self.detector_modes.items():combo.setCurrentText(cfg.detector_modes.get(name,cfg.mode))
        self.roll.setValue(cfg.roll);self.highlight_ids.setText(', '.join(cfg.highlight_track_ids));self.highlight_width.setValue(cfg.highlight_track_radius_cm*2);self.highlight_clusters.setValue(cfg.highlight_cluster_radius_cm);self.highlight_override.setChecked(cfg.highlight_override_color);self.highlight_track_color.setText(cfg.highlight_track_color);self.highlight_cluster_color.setText(cfg.highlight_cluster_color)
        self.tpc_profile.setCurrentText(cfg.tpc_cluster_profile);self.tpc_profile_scale.setValue(cfg.tpc_profile_scale);self.tpc_profile_thickness.setValue(cfg.tpc_profile_thickness_cm)
        self.view_transform.setCurrentText(cfg.view_transform);self.exposure.setValue(cfg.exposure);self.track_emission.setValue(cfg.track_emission);self.cluster_emission.setValue(cfg.cluster_emission)
        self.data_glow_lighting.setChecked(cfg.data_glow_lighting)
        self.camera_lens.setValue(cfg.camera_pose.get('lens',cfg.camera_lens_mm))
        self.scene_overrides['palette_lut']=cfg.palette_lut
        self.scene_overrides['camera_pose']=cfg.camera_pose
        self.scene_overrides['geometry_openings']=cfg.geometry_openings
        self.scene_overrides['geometry_opening_directions']=cfg.geometry_opening_directions
        self.scene_overrides['geometry_exclusions']=cfg.geometry_exclusions
        self.scene_overrides['geometry_inner_masks']=cfg.geometry_inner_masks
        self.scene_overrides['geometry_components']=cfg.geometry_components
        self.refresh_components()
        self.refresh_opening_summary()
    def use_detector_defaults(self):
        try:
            cfg=detector_settings(self.detector_setup.currentText(),ROOT)
            self.apply_scene(cfg);self.update_availability();self.save_settings(self.settings())
            self.message('Detector setup applied. Upgrade geometry is nominal O2 design geometry; data detector identities are unchanged.')
        except Exception as exc:self.failure(str(exc))
    def use_commissioning_defaults(self):
        cfg=commissioning_settings({k:v.text() for k,v in self.asset_fields.items() if v.text()},self.geometry_units.currentText())
        self.apply_scene(cfg);self.update_availability()
        saved=self.settings();saved.detectors=cfg.detectors;self.save_settings(saved)
        self.message('Improved commissioning defaults applied. Input, selected events and local geometry assets retained.')
    def open_editor(self):
        has_event=bool(self.catalogue and self.model.selected)
        if has_event and self.source.text()!=self.loaded_input:self.failure('The input path has changed. Press Enter or Load input, then select its event before opening the editor.');return
        try:cfg=self.settings();ordinal=min(self.model.selected) if has_event else None
        except Exception as exc:self.failure(str(exc));return
        def launched(result):
            self.refresh_library();self.message('Interactive Blender scene started. Open the ALICE EVE sidebar; export or render from there. Log: '+str(result[0]/'editor.log'))
        blender=self.blender.text();output=Path(self.output.text())
        fast=self.fast_interactive.isChecked()
        self.start_task(lambda p,c:launch_editor(blender,self.catalogue.event_path(ordinal,progress=p,cancelled=c) if has_event else None,cfg,output,library_path=self.library.path,fast=fast),launched)
    def render_quality_dialog(self,cfg,devices):
        rec=recommended_quality(devices);dialog=QDialog(self);dialog.setWindowTitle('Full render quality');form=QFormLayout(dialog)
        note=QLabel(rec['reason']);note.setWordWrap(True);form.addRow(note)
        quality=QComboBox();quality.addItems(['draft','balanced','final','publication','custom']);quality.setCurrentText(rec['quality']);form.addRow('Sampling preset',quality)
        backend=QComboBox();backend.addItems(list(dict.fromkeys(d['type'] for d in devices['devices'])));backend.setCurrentText(rec['backend']);form.addRow('Available backend',backend)
        slider=QSlider(Qt.Horizontal);slider.setObjectName('resolutionPercent');slider.setRange(math.ceil(minimum_percent(cfg.frame_aspect)*10),1000);slider.setTickInterval(250);slider.setTickPosition(QSlider.TicksBelow);slider.setValue(round(PRESET_PERCENT[rec['quality']]*10))
        form.addRow('Resolution (% of 8K)',slider);resolution=QLabel();form.addRow(resolution)
        milestones=QWidget();row=QHBoxLayout(milestones);row.setContentsMargins(0,0,0,0)
        for percent,label in ((25,'25% · 1080p'),(50,'50% · 4K'),(100,'100% · 8K')):
            button=QPushButton(label);button.clicked.connect(lambda checked=False,p=percent:slider.setValue(p*10));row.addWidget(button)
        form.addRow(milestones)
        def show_resolution():
            w,h=percentage_size(slider.value()/10,cfg.frame_aspect);resolution.setText(f'{slider.value()/10:g}% · {w} × {h} px · preserves camera aspect')
        slider.valueChanged.connect(show_resolution);show_resolution()
        samples=number(cfg.samples,1,8192);form.addRow('Custom samples',samples)
        geometry_details={}
        for name in cfg.geometry+(['L3'] if cfg.magnet else []):
            from .geometry_selection import description
            combo=QComboBox();combo.addItem('Keep current: '+description(cfg.to_dict(),name),'current');combo.addItem('Full aligned surfaces','full')
            if name in ('ITS','TPC'):combo.addItem('Large surfaces (cached, fast)','structural')
            from .surface_proxy import sidecar_path
            if sidecar_path(cfg.geometry_assets.get(name,'')).is_file():combo.addItem('Cached approximate surfaces (fast)','proxy')
            combo.addItem('Simplified aligned cells','simplified');combo.addItem('Schematic envelope','schematic');geometry_details[name]=combo;form.addRow(name+' geometry detail',combo)
        if geometry_details:
            note=QLabel('Explicit geometry choices override the preview type and appearance. Full and simplified aligned geometry require their assets.');note.setWordWrap(True);form.addRow(note)
        def toggle():
            samples.setEnabled(quality.currentText()=='custom');slider.setValue(round(PRESET_PERCENT[quality.currentText()]*10))
        quality.currentTextChanged.connect(toggle);toggle()
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()!=QDialog.Accepted:return None
        custom=quality.currentText()=='custom'
        chosen=quality_settings(cfg,'balanced' if custom else quality.currentText(),backend=backend.currentText(),samples=samples.value() if custom else None,resolution_percent=slider.value()/10)
        from .geometry_selection import render_choices
        return render_choices(chosen,{name:combo.currentData() for name,combo in geometry_details.items()})
    def start_render(self,preview):
        if self.model.selected and self.source.text()!=self.loaded_input:self.failure('The input path has changed. Press Enter or Load input, then select its event before rendering.');return
        try:cfg=self.settings();self.save_settings(cfg)
        except Exception as exc:self.failure(str(exc));return
        ids=sorted(self.model.selected)
        if preview:ids=ids[:1]
        blender=self.blender.text();output=Path(self.output.text())
        def run(chosen):
            if chosen is not None:self.start_task(lambda p,c:render_events(blender,[self.catalogue.event_path(i,progress=p,cancelled=c) for i in ids],chosen,output,preview=preview,progress=p,cancelled=c,library_path=self.library.path),lambda batch:(self.refresh_library(),self.message(f'Completed: {batch}')))
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
        profile=metadata.get('cluster_legend',{})
        if profile.get('tpc_profile','sphere')!='sphere':parts.append(f"TPC profiles: {profile.get('profiled_clusters',0)} measured; {profile.get('missing_tpc_profiles',0)} missing widths (spheres)")
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
    # Conda's qt.conf can redirect discovery to plugins from a different Qt
    # release. Use the plugins shipped with the PySide6 loaded by this process.
    bundled_plugins=Path(PySide6.__file__).resolve().parent/'Qt'/'plugins'
    if bundled_plugins.is_dir():
        os.environ.setdefault('QT_PLUGIN_PATH',str(bundled_plugins))
        os.environ.setdefault('QT_QPA_PLATFORM_PLUGIN_PATH',str(bundled_plugins/'platforms'))
    app=QApplication.instance() or QApplication([]);window=Window();window.show();return app.exec()

if __name__=='__main__':raise SystemExit(main())
