import sys
import os
import json
import base64
import tempfile
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QSlider,
    QLineEdit,
    QStackedLayout,
    QAction,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QInputDialog,
    QMenu,
)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import Qt, QEvent, QUrl, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap, QFont, QFontMetrics, QPainter, QPen, QColor

from mutagen import File as MutagenFile
from mutagen.flac import FLAC, Picture
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis
from pydub import AudioSegment

# -----------------------------------------------------------------------------
#   Styling constants
# -----------------------------------------------------------------------------
GREEN_SLIM = (
    "QSlider::groove:horizontal{height:6px;background:rgb(0,80,0);border-radius:3px;}"
    "QSlider::handle:horizontal{background:#C0C0C0;border:1px solid #333;width:12px;"
    "height:12px;margin:-4px 0;border-radius:6px;}"
    "QSlider::sub-page:horizontal{background:rgb(0,180,0);border-radius:3px;}"
)
BLUE_SLIM = GREEN_SLIM.replace("0,80,0", "0,60,120").replace("0,180,0", "30,144,255")
RED_SLIM = (
    "QSlider::groove:horizontal{height:6px;background:#404040;border-radius:3px;}"
    "QSlider::sub-page:horizontal{background:#FF3030;border-radius:3px;}"
    "QSlider::handle:horizontal{width:0px;height:0px;margin:0px;}"
)

BUFFER_MS = 250  # Skip‑protection buffer when looping

# -----------------------------------------------------------------------------
#   Helper dialogs
# -----------------------------------------------------------------------------


class RangePresetEditor(QDialog):
    """Modal dialog allowing the user to edit three range‑loop presets."""

    def __init__(self, presets, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Range Presets")
        self.starts, self.ends = [], []
        form = QFormLayout(self)
        for i, (s, e) in enumerate(presets, 1):
            start_edit, end_edit = QLineEdit(self), QLineEdit(self)
            start_edit.setPlaceholderText("mm:ss or ss")
            end_edit.setPlaceholderText("mm:ss or ss")
            start_edit.setText(s)
            end_edit.setText(e)
            row = QHBoxLayout()
            row.addWidget(start_edit)
            row.addWidget(QLabel("→"))
            row.addWidget(end_edit)
            form.addRow(f"Preset {i}", row)
            self.starts.append(start_edit)
            self.ends.append(end_edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addWidget(btns)

    def values(self):
        """Return the edited preset tuples as strings."""
        return [(s.text().strip(), e.text().strip()) for s, e in zip(self.starts, self.ends)]


class PresetEditor(QDialog):
    """Modal dialog used for editing speed‑percentage presets."""

    def __init__(self, presets, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Speed Presets")
        self.spins = []
        form = QFormLayout(self)
        for i, val in enumerate(presets, 1):
            spin = QSpinBox()
            spin.setRange(1, 200)
            spin.setValue(val)
            form.addRow(f"Preset {i} (%)", spin)
            self.spins.append(spin)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addWidget(btns)

    def values(self):
        """Return the edited speed‑preset values as integers."""
        return [s.value() for s in self.spins]


# -----------------------------------------------------------------------------
#   Custom widgets
# -----------------------------------------------------------------------------


class LoopOverlay(QWidget):
    """Transparent overlay drawing yellow start/end markers on the seek slider."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.start_ms, self.end_ms, self.duration = None, None, 0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def set_loop(self, start_ms, end_ms, duration):
        """Configure which segment is currently looped and trigger repaint."""
        self.start_ms, self.end_ms, self.duration = start_ms, end_ms, duration
        self.setVisible(bool(start_ms is not None and end_ms is not None and duration))
        self.update()

    def paintEvent(self, _):
        if not self.isVisible() or not self.duration:
            return
        painter = QPainter(self)
        painter.setPen(QPen(QColor(255, 255, 0), 3))
        w = self.width()
        x1 = int(self.start_ms / self.duration * w)
        x2 = int(self.end_ms / self.duration * w)
        painter.drawLine(x1, 0, x1, self.height())
        painter.drawLine(x2, 0, x2, self.height())


class SeekSlider(QSlider):
    """Horizontal slider that supports direct click‑to‑seek interactions."""

    sliderClicked = pyqtSignal(int)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.orientation() == Qt.Horizontal:
            ratio = ev.pos().x() / self.width()
            new_val = self.minimum() + round(ratio * (self.maximum() - self.minimum()))
            self.setValue(new_val)
            self.sliderClicked.emit(new_val)
            ev.accept()
        super().mousePressEvent(ev)


# -----------------------------------------------------------------------------
#   Main window
# -----------------------------------------------------------------------------


class AudioPlayer(QMainWindow):
    """Full‑fledged practice audio player exposing loop, speed and range tools."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Practice Hard!")
        self.setStyleSheet("background-color:#000")
        self.resize(700, 900)

        # Persistent preset storage --------------------------------------------------
        docs = Path.home() / "Documents" / "Practice Hard"
        docs.mkdir(parents=True, exist_ok=True)
        self.presets_file = str(docs / "presets.json")
        try:
            with open(self.presets_file, "r", encoding="utf-8") as fp:
                self.presets_data = json.load(fp)
        except (FileNotFoundError, json.JSONDecodeError):
            self.presets_data = {}

        # Runtime state --------------------------------------------------------------
        self.current_key = None
        self.speed_presets = []
        self.range_presets = [("", "") for _ in range(3)]
        self.skip_ms = 5_000
        self.slice_start = 0
        self.slice_end = None
        self.full_duration = 0
        self.duration = 0
        self.start_pos = self.end_pos = None
        self.scrubbing = False
        self._skip_pos_updates = 0
        self._resume_after_slice = False
        self.current_path = ""
        self.original_path = ""

        # Backend player -------------------------------------------------------------
        self.player = QMediaPlayer()
        self.player.setNotifyInterval(5)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.durationChanged.connect(self._store_full_len)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.mediaStatusChanged.connect(self._resume_if_needed)
        self.player.positionChanged.connect(self._ui_pos_changed)

        # UI construction ------------------------------------------------------------
        central = QWidget(self)
        self.setCentralWidget(central)
        self.main = QVBoxLayout(central)
        self._build_header()
        self._build_range_controls()
        self._build_cover()
        self._build_progress_bar()
        self._build_volume()
        self._build_speed_slider()
        self._build_presets_row()
        self._build_range_presets_row()
        self._refresh_presets_ui(first_time=True)
        self._refresh_range_presets_ui()
        self._refresh_settings_menu()

        # Global timers and event filter --------------------------------------------
        QApplication.instance().installEventFilter(self)
        self.tick = QTimer(self)
        self.tick.setInterval(100)
        self.tick.timeout.connect(self._refresh_ui)
        self.tick.start()

    # -------------------------------------------------------------------------
    #   UI builders
    # -------------------------------------------------------------------------
    def _build_header(self):
        """Create top‑bar with upload button and filename label."""
        self.label = QLabel("← it's time to practice…", self)
        self.label.setStyleSheet("font-size:20px;font-weight:bold;color:#fff")
        self.upload_btn = QPushButton("📁", self)
        self.upload_btn.setFixedSize(40, 40)
        self.upload_btn.setStyleSheet("font-size:35px;background:#000;border-radius:5px")
        self.upload_btn.clicked.connect(self._open_file)
        row = QHBoxLayout()
        row.addWidget(self.upload_btn)
        row.addWidget(self.label)
        self.main.addLayout(row)

    def _build_range_controls(self):
        """Add range‑selection inputs, GO/SET buttons and full‑track restore."""
        self.start_in, self.end_in = QLineEdit(self), QLineEdit(self)
        for e in (self.start_in, self.end_in):
            e.setPlaceholderText("mm:ss  or  ss")
        self.set_range = QPushButton("GO", self)
        self.set_range.setFixedSize(40, 40)
        self.set_range.setEnabled(False)
        self.set_range.setStyleSheet("font-size:20px;background:#67ce61;color:#fff;border-radius:5px")
        self.set_range.clicked.connect(self._apply_range)
        self.save_range_btn = QPushButton("SET", self)
        self.save_range_btn.setFixedSize(40, 40)
        self.save_range_btn.setEnabled(False)
        self.save_range_btn.setStyleSheet("font-size:16px;background:#FFC107;color:#000;border-radius:5px")
        self.save_range_btn.clicked.connect(self._save_current_range)
        self.back_btn = QPushButton("FULL", self)
        self.back_btn.setFixedSize(40, 40)
        self.back_btn.setEnabled(False)
        self.back_btn.setStyleSheet("font-size:16px;background:#ff0000;color:#fff;border-radius:5px")
        self.back_btn.clicked.connect(self._restore_full_track)
        row = QHBoxLayout()
        row.addWidget(QLabel("RANGE:"))
        row.addWidget(self.start_in)
        row.addWidget(QLabel("→"))
        row.addWidget(self.end_in)
        row.addWidget(self.set_range)
        row.addWidget(self.save_range_btn)
        row.addWidget(self.back_btn)
        self.main.addLayout(row)

    def _build_cover(self):
        """Create album‑art display with an oversized play/pause toggle."""
        self.cover = QLabel(self)
        self.cover.setScaledContents(True)
        self.cover.setFixedSize(500, 500)
        self.play_btn = QPushButton("▶", self)
        self.play_btn.setFixedSize(500, 500)
        self.play_btn.setEnabled(False)
        self.play_btn.setStyleSheet("font-size:250px;background:transparent;color:#fff")
        self.play_btn.clicked.connect(self._toggle_play)
        stack = QStackedLayout()
        stack.setStackingMode(QStackedLayout.StackAll)
        stack.addWidget(self.cover)
        stack.addWidget(self.play_btn)
        container = QWidget(self)
        container.setLayout(stack)
        self.main.addWidget(container, alignment=Qt.AlignCenter)

    def _build_progress_bar(self):
        """Create seek slider, time label and attach LoopOverlay."""
        self.progress = SeekSlider(Qt.Horizontal, self)
        self.progress.setStyleSheet(RED_SLIM)
        self.progress.sliderPressed.connect(lambda: setattr(self, "scrubbing", True))
        self.progress.sliderReleased.connect(self._seek_released)
        self.progress.sliderMoved.connect(self._seek_moved)
        self.loop_overlay = LoopOverlay(self.progress)
        self.loop_overlay.setGeometry(0, 0, self.progress.width(), self.progress.height())
        self.progress.installEventFilter(self)
        mono = QFont("Courier New", 10)
        self.time_lbl = QLabel("00:00.000 / 00:00.000", self)
        self.time_lbl.setFont(mono)
        width = QFontMetrics(mono).horizontalAdvance(self.time_lbl.text())
        self.time_lbl.setFixedWidth(width)
        row = QHBoxLayout()
        row.addWidget(self.progress)
        row.addWidget(self.time_lbl)
        self.main.addLayout(row)

    def _build_volume(self):
        """Create green volume slider with percentage display."""
        self.vol = QSlider(Qt.Horizontal, self)
        self.vol.setRange(0, 100)
        self.vol.setValue(100)
        self.vol.setStyleSheet(GREEN_SLIM)
        self.vol.valueChanged.connect(self.player.setVolume)
        self.vlbl = QLabel("100%", self)
        self.vol.valueChanged.connect(lambda v: self.vlbl.setText(f"{v}%"))
        row = QHBoxLayout()
        row.addWidget(QLabel("VOLUME:"))
        row.addWidget(self.vol)
        row.addWidget(self.vlbl)
        self.main.addLayout(row)

    def _build_speed_slider(self):
        """Create blue speed slider controlling playback‑rate."""
        self.spd = QSlider(Qt.Horizontal, self)
        self.spd.setStyleSheet(BLUE_SLIM)
        self.slbl = QLabel(self)
        self.spd.valueChanged.connect(lambda v: (self.player.setPlaybackRate(v / 100), self.slbl.setText(f"{v}%")))
        row = QHBoxLayout()
        row.addWidget(QLabel("SPEED:"))
        row.addWidget(self.spd)
        row.addWidget(self.slbl)
        self.main.addLayout(row)

    def _build_presets_row(self):
        """Prepare horizontal layout that will host speed‑preset buttons."""
        self.preset_row = QHBoxLayout()
        self.preset_row.addWidget(QLabel("SPEED PRESETS:"))
        self.main.addLayout(self.preset_row)

    def _build_range_presets_row(self):
        """Prepare horizontal layout that will host range‑preset buttons."""
        self.range_preset_row = QHBoxLayout()
        self.range_preset_row.addWidget(QLabel("RANGE PRESETS:"))
        self.main.addLayout(self.range_preset_row)

    # -------------------------------------------------------------------------
    #   Preset helpers
    # -------------------------------------------------------------------------
    def _refresh_presets_ui(self, first_time=False):
        """Synchronise speed‑preset buttons, slider range and label text."""
        if isinstance(self.speed_presets, int):
            self.speed_presets = [self.speed_presets]
        if self.speed_presets is None:
            self.speed_presets = []
        max_val = max(100, *self.speed_presets) if self.speed_presets else 100
        self.spd.setRange(1, max_val)
        self.spd.setValue(100 if first_time else min(self.spd.value(), max_val))
        self.slbl.setText(f"{self.spd.value()}%")
        while self.preset_row.count() > 1:
            w = self.preset_row.takeAt(1).widget()
            if w:
                w.deleteLater()
        for v in self.speed_presets:
            btn = QPushButton(f"{v}%", self)
            btn.clicked.connect(lambda _, vv=v: self.spd.setValue(vv))
            self.preset_row.addWidget(btn)

    def _refresh_range_presets_ui(self):
        """Rebuild the row of buttons representing saved range presets."""
        while self.range_preset_row.count() > 1:
            item = self.range_preset_row.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()
        for s, e in self.range_presets:
            label = f"{s}→{e}" if s and e else "-"
            btn = QPushButton(label, self)
            btn.setEnabled(bool(s and e))
            btn.clicked.connect(lambda _, ss=s, ee=e: self._apply_preset(ss, ee))
            self.range_preset_row.addWidget(btn)

    def _refresh_settings_menu(self):
        """Update the SETTINGS menu to reflect current configuration."""
        if menu := self.menuBar().findChild(QMenu, "SETTINGS_MENU"):
            self.menuBar().removeAction(menu.menuAction())
        settings = self.menuBar().addMenu("SETTINGS")
        settings.setObjectName("SETTINGS_MENU")
        settings.addAction(QAction(f"Edit Skip…  (current: {self.skip_ms // 1000}s)", self, triggered=self._edit_skip))
        cur_speed = " / ".join(f"{v}%" for v in self.speed_presets) or "none"
        settings.addAction(QAction(f"Edit Speed Presets…  (current: {cur_speed})", self, triggered=self._edit_presets))
        filled_ranges = sum(1 for s, e in self.range_presets if s and e)
        settings.addAction(QAction(f"Edit Range Presets…  (current: {filled_ranges} set)", self, triggered=self._edit_ranges))

    def _store_presets(self):
        """Persist current speed and range presets to disk."""
        if not self.current_key:
            return
        self.presets_data[self.current_key] = {
            "speed_presets": self.speed_presets,
            "range_presets": self.range_presets,
        }
        try:
            with open(self.presets_file, "w", encoding="utf-8") as f:
                json.dump(self.presets_data, f, indent=2)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    #   Dialog callbacks
    # -------------------------------------------------------------------------
    def _edit_presets(self):
        dlg = PresetEditor(self.speed_presets, self)
        if dlg.exec_() == QDialog.Accepted:
            self.speed_presets = dlg.values()
            self._refresh_presets_ui()
            self._store_presets()

    def _edit_ranges(self):
        dlg = RangePresetEditor(self.range_presets, self)
        if dlg.exec_() == QDialog.Accepted:
            self.range_presets = dlg.values()
            self._refresh_range_presets_ui()
            self._refresh_presets_ui()
            self._store_presets()

    def _edit_skip(self):
        secs, ok = QInputDialog.getInt(self, "Skip interval", "Jump amount for ← / →  (seconds):", self.skip_ms // 1000, 1, 60, 1)
        if ok:
            self.skip_ms = secs * 1000
            self._refresh_settings_menu()

    # -------------------------------------------------------------------------
    #   Preset application helpers
    # -------------------------------------------------------------------------
    def _apply_preset(self, ss, ee):
        """Fill inputs and activate the selected range preset."""
        if not (ss and ee):
            return
        self.start_in.setText(ss)
        self.end_in.setText(ee)
        was_playing = self.player.state() == QMediaPlayer.PlayingState
        self._apply_range()
        if was_playing and self.player.state() != QMediaPlayer.PlayingState:
            self.player.play()

    def _save_current_range(self):
        """Store the currently entered range into the first available preset slot."""
        start, end = self.start_in.text().strip(), self.end_in.text().strip()
        if not start or not end:
            return
        try:
            self._parse_time(start)
            self._parse_time(end)
        except Exception:
            return
        empty_slots = [i for i, (s, e) in enumerate(self.range_presets) if not s or not e]
        if empty_slots:
            idx = empty_slots[0]
        else:
            slot, ok = QInputDialog.getInt(self, "Overwrite Range Preset", "All 3 range presets are used.\nSelect preset slot to overwrite (1–3):", 1, 1, len(self.range_presets), 1)
            if not ok:
                return
            idx = slot - 1
        self.range_presets[idx] = (start, end)
        self._refresh_range_presets_ui()
        self._store_presets()

    # -------------------------------------------------------------------------
    #   File loading and metadata
    # -------------------------------------------------------------------------
    def _open_file(self):
        """Show file dialog, load selected audio and associated presets."""
        path, _ = QFileDialog.getOpenFileName(self, "Open Audio", "", "Audio Files (*.mp3 *.flac *.m4a *.ogg);;All Files (*)")
        if not path:
            return
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        self.current_path = path
        self.original_path = path
        base = os.path.splitext(os.path.basename(path))[0]
        meta = MutagenFile(path, easy=True)
        artist = (meta.tags.get("artist") or ["Unknown"])[0] if meta and meta.tags else "Unknown"
        title = (meta.tags.get("title") or [base])[0] if meta and meta.tags else base
        self.current_key = f"{artist} - {title}"
        song_presets = self.presets_data.get(self.current_key, {})
        sp = song_presets.get("speed_presets", [])
        if isinstance(sp, int):
            sp = [sp]
        if not sp:
            sp = [20, 50, 80]
        self.speed_presets = sp
        self.range_presets = song_presets.get("range_presets", [("", ""), ("", ""), ("", "")])
        self._refresh_presets_ui(first_time=True)
        self._refresh_range_presets_ui()
        self.label.setText(f"🔥 Now Practicing: {base} 🔥")
        self.label.setStyleSheet("font-size:20px;font-weight:bold;color:#FF5733")
        self.play_btn.setEnabled(True)
        self.set_range.setEnabled(True)
        self.save_range_btn.setEnabled(True)
        self.start_in.clear()
        self.end_in.clear()
        self.start_pos = self.end_pos = None
        self._load_cover(path)
        self._update_loop_overlay()

    def _load_cover(self, path):
        """Extract and display embedded album art if present."""
        audio = MutagenFile(path, easy=False)
        pix = QPixmap()
        if isinstance(audio, FLAC) and getattr(audio, "pictures", None):
            pix.loadFromData(audio.pictures[0].data)
        elif isinstance(audio, MP3):
            tags = audio.tags or ID3(path)
            for tag in tags.values():
                if isinstance(tag, APIC):
                    pix.loadFromData(tag.data)
                    break
        elif isinstance(audio, MP4):
            covr = audio.tags.get("covr")
            if covr and isinstance(covr[0], MP4Cover):
                pix.loadFromData(bytes(covr[0]))
        elif isinstance(audio, OggVorbis):
            pic_data = audio.get("metadata_block_picture")
            if pic_data:
                raw = base64.b64decode(pic_data[0])
                pic = Picture()
                pic.parse(raw)
                pix.loadFromData(pic.data)
        if not pix.isNull():
            self.cover.setPixmap(pix.scaled(500, 500, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        self.play_btn.raise_()

    # -------------------------------------------------------------------------
    #   Playback controls
    # -------------------------------------------------------------------------
    def _toggle_play(self):
        """Play or pause the current media and update toggle icon."""
        if self.player.media().isNull():
            return
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_btn.setText("▶")
        else:
            self.player.play()
            self.play_btn.setText("⏸")

    def _skip(self, delta_ms: int):
        """Jump forwards/backwards on the *full* timeline by a delta."""
        if self.full_duration == 0:
            return
        cur_full = self._slice_to_full(self.player.position())
        new_full = max(0, min(self.full_duration, cur_full + delta_ms))
        self.player.setPosition(self._full_to_slice(new_full))

    def _seek_moved(self, v):
        """Update time label while knob is dragged on the seek slider."""
        if not self.scrubbing:
            self.scrubbing = True
            self.player.pause()
        if self.slice_end is not None:
            v = max(self.slice_start, min(self.slice_end, v))
            self.progress.blockSignals(True)
            self.progress.setValue(v)
            self.progress.blockSignals(False)
        self.time_lbl.setText(f"{self._fmt(v)} / {self._fmt(self.full_duration)}")

    def _seek_released(self):
        """Perform final seek when the slider knob is released."""
        full_target = self.progress.value()
        if self.slice_end is not None:
            full_target = max(self.slice_start, min(self.slice_end, full_target))
        slice_pos = self._full_to_slice(full_target)
        self._skip_pos_updates = 2
        self.player.setPosition(slice_pos)
        self._update_slider_and_time(slice_pos)
        self.scrubbing = False
        self.player.play()

    # -------------------------------------------------------------------------
    #   Loop / slice handling
    # -------------------------------------------------------------------------
    def _apply_range(self):
        """Render user‑specified range as a looping slice and load it."""
        st, ed = self._parse_time(self.start_in.text()), self._parse_time(self.end_in.text())
        if st is None or ed is None or st >= ed:
            return
        resume_after = self.player.state() == QMediaPlayer.PlayingState
        self.slice_start, self.slice_end = st, ed
        seg = AudioSegment.from_file(self.current_path)[st:ed]
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        seg.export(tmp.name, format="wav")
        from PyQt5.QtMultimedia import QMediaPlaylist
        pl = QMediaPlaylist()
        pl.addMedia(QMediaContent(QUrl.fromLocalFile(tmp.name)))
        pl.setPlaybackMode(QMediaPlaylist.CurrentItemInLoop)
        self.player.setPlaylist(pl)
        self.duration = len(seg)
        self.progress.setRange(0, self.full_duration)
        self._update_loop_overlay()
        self.back_btn.setEnabled(True)
        self._resume_after_slice = resume_after

    def _restore_full_track(self):
        """Return from sliced playback to the original file."""
        if not self.original_path:
            return
        self.player.stop()
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(self.original_path)))
        self.player.play()
        self.slice_start, self.slice_end = 0, None
        self.duration = self.full_duration
        self.progress.setRange(0, self.full_duration)
        self.back_btn.setEnabled(False)
        self._update_loop_overlay()

    def _update_loop_overlay(self):
        """Sync loop markers with current slice (if any)."""
        if self.slice_end is not None:
            self.loop_overlay.set_loop(self.slice_start, self.slice_end, self.full_duration)
        else:
            self.loop_overlay.set_loop(None, None, 0)
        self.loop_overlay.update()

    # -------------------------------------------------------------------------
    #   Player callbacks
    # -------------------------------------------------------------------------
    def _duration_changed(self, d):
        self.duration = d
        self.progress.setRange(0, self.full_duration)
        self.progress.setValue(0)
        self.time_lbl.setText(f"{self._fmt(0)} / {self._fmt(d)}")
        self._update_loop_overlay()

    def _media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.player.setPosition(0)
            self.player.play()

    def _ui_pos_changed(self, pos: int):
        if self._skip_pos_updates:
            self._skip_pos_updates -= 1
            return
        if not self.scrubbing:
            self._update_slider_and_time(pos)

    def _store_full_len(self, dur_ms: int):
        if self.slice_end is None:
            self.full_duration = dur_ms
            self.progress.setRange(0, dur_ms)

    def _resume_if_needed(self, status):
        if status == QMediaPlayer.LoadedMedia and self._resume_after_slice:
            self._resume_after_slice = False
            self.player.play()
            self.play_btn.setText("⏸")

    # -------------------------------------------------------------------------
    #   Misc helpers
    # -------------------------------------------------------------------------
    def _update_slider_and_time(self, player_pos_ms: int):
        """Update seek slider and time label using full‑track scale."""
        if self.slice_end is not None:
            display_pos = self.slice_start + player_pos_ms
            total_ms = self.full_duration
        else:
            display_pos = player_pos_ms
            total_ms = self.full_duration or player_pos_ms
        self.progress.blockSignals(True)
        self.progress.setValue(display_pos)
        self.progress.blockSignals(False)
        self.time_lbl.setText(f"{self._fmt(display_pos)} / {self._fmt(total_ms)}")

    @staticmethod
    def _fmt(ms):
        """Return mm:ss.mmm formatted string given milliseconds."""
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}.{ms:03d}"

    @staticmethod
    def _parse_time(text: str):
        """Convert 'mm:ss' or 'ss' string to milliseconds or None."""
        t = text.strip()
        if ":" in t:
            try:
                m, s = map(int, t.split(":"))
                return (m * 60 + s) * 1000
            except ValueError:
                return None
        return int(t) * 1000 if t.isdigit() else None

    def _full_to_slice(self, full_ms: int) -> int:
        """Translate full‑track timestamp to slice‑relative timestamp."""
        if self.slice_end is None:
            return full_ms
        return max(0, min(self.slice_end, full_ms) - self.slice_start)

    def _slice_to_full(self, slice_ms: int) -> int:
        """Translate slice‑relative timestamp to full‑track timestamp."""
        if self.slice_end is None:
            return slice_ms
        return self.slice_start + slice_ms

    def _refresh_ui(self):
        """Timer‑driven UI refresh used while playback is paused."""
        if self.player.state() != QMediaPlayer.PlayingState and not self.scrubbing:
            self._update_slider_and_time(self.player.position())

    # -------------------------------------------------------------------------
    #   Qt overrides
    # -------------------------------------------------------------------------
    def eventFilter(self, src, ev):
        """Global hotkeys and overlay resizing."""
        if ev.type() == QEvent.KeyPress and not isinstance(src, QLineEdit):
            key = ev.key()
            if key == Qt.Key_Space:
                self._toggle_play()
                return True
            if key == Qt.Key_Left:
                self._skip(-self.skip_ms)
                return True
            if key == Qt.Key_Right:
                self._skip(self.skip_ms)
                return True
            if key == Qt.Key_R:
                self.player.setPosition(0)
                return True
        if src is self.progress and ev.type() in (QEvent.Resize, QEvent.Move):
            self.loop_overlay.setGeometry(0, 0, self.progress.width(), self.progress.height())
            self.loop_overlay.update()
        return super().eventFilter(src, ev)


# -----------------------------------------------------------------------------
#   Application entry point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = AudioPlayer()
    gui.show()
    sys.exit(app.exec_())
