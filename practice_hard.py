import sys
import os
import json
import base64
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QSlider, QLineEdit,
    QStackedLayout, QAction, QDialog, QDialogButtonBox,
    QFormLayout, QSpinBox
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


# ─────────────────────────── Range Preset Editor ───────────────────────────
class RangePresetEditor(QDialog):
    def __init__(self, presets, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Range Presets")
        self.setModal(True)
        self.starts = []
        self.ends = []
        form = QFormLayout(self)
        for i, (s, e) in enumerate(presets, 1):
            start_edit = QLineEdit(self)
            start_edit.setPlaceholderText("mm:ss or ss")
            start_edit.setText(s)
            end_edit = QLineEdit(self)
            end_edit.setPlaceholderText("mm:ss or ss")
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
        return [(s.text().strip(), e.text().strip()) for s, e in zip(self.starts, self.ends)]


# ─────────────────────────── Speed Preset Editor ──────────────────────────
class PresetEditor(QDialog):
    def __init__(self, presets, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Speed Presets")
        self.setModal(True)
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
        return [s.value() for s in self.spins]


# ───────────────────────────────── Loop overlay ──────────────────────────────
class LoopOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.start_ms = None
        self.end_ms   = None
        self.duration = 0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def set_loop(self, start_ms, end_ms, duration):
        self.start_ms, self.end_ms, self.duration = start_ms, end_ms, duration
        self.setVisible(bool(start_ms is not None and end_ms is not None and duration))
        self.update()

    def paintEvent(self, e):
        if not self.isVisible() or not self.duration:
            return
        painter = QPainter(self)
        painter.setPen(QPen(QColor(255, 255, 0), 3))
        w = self.width()
        x1 = int(self.start_ms / self.duration * w)
        x2 = int(self.end_ms   / self.duration * w)
        painter.drawLine(x1, 0, x1, self.height())
        painter.drawLine(x2, 0, x2, self.height())


# ───────────────────────────────── Slider ────────────────────────────────────
class SeekSlider(QSlider):
    sliderClicked = pyqtSignal(int)
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.orientation() == Qt.Horizontal:
            ratio = ev.pos().x() / self.width()
            new_val = self.minimum() + round(ratio * (self.maximum() - self.minimum()))
            self.setValue(new_val)
            self.sliderClicked.emit(new_val)
            ev.accept()
        super().mousePressEvent(ev)


# ───────────────────────────────── Styles ────────────────────────────────────
GREEN_SLIM = '''
QSlider::groove:horizontal{height:6px;background:rgb(0,80,0);border-radius:3px;}
QSlider::handle:horizontal{background:#C0C0C0;border:1px solid #333;width:12px;height:12px;
                           margin:-4px 0;border-radius:6px;}
QSlider::sub-page:horizontal{background:rgb(0,180,0);border-radius:3px;}'''
BLUE_SLIM = GREEN_SLIM.replace("0,80,0", "0,60,120").replace("0,180,0", "30,144,255")
RED_SLIM  = '''
QSlider::groove:horizontal{height:6px;background:#404040;border-radius:3px;}
QSlider::sub-page:horizontal{background:#FF3030;border-radius:3px;}
QSlider::handle:horizontal{width:0px;height:0px;margin:0px;}''' 


# ───────────────────────────────── Main ──────────────────────────────────────
class AudioPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Practice Hard!")
        self.setStyleSheet("background-color:#000")
        self.resize(700, 900)

        # presets file in Documents/Practice Hard
        docs = Path.home() / "Documents" / "Practice Hard"
        docs.mkdir(parents=True, exist_ok=True)
        self.presets_file = str(docs / "presets.json")
        try:
            with open(self.presets_file, 'r') as f:
                self.presets_data = json.load(f)
        except:
            self.presets_data = {}
        self.current_key = None

        # presets
        self.speed_presets = [20, 50, 80]
        self.range_presets = [("", "") for _ in range(3)]

        # player state
        self.player = QMediaPlayer()
        self.duration = 0
        self.start_pos = self.end_pos = None
        self.scrubbing = False

        # signals
        self.player.durationChanged.connect(self._duration_changed)
        self.player.mediaStatusChanged.connect(self._media_status)

        # UI setup
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

        # initial UI refresh
        self._refresh_presets_ui(first_time=True)
        self._refresh_range_presets_ui()

        # Global event filter & refresh timer
        QApplication.instance().installEventFilter(self)
        self.tick = QTimer(self)
        self.tick.setInterval(40)
        self.tick.timeout.connect(self._refresh_ui)
        self.tick.start()

    # New helper to parse time strings
    def _parse_time(self, text: str) -> int:
        t = text.strip()
        if ':' in t:
            try:
                m, s = map(int, t.split(':'))
                return (m*60 + s)*1000
            except ValueError:
                return None
        return int(t)*1000 if t.isdigit() else None

    # Handles applying a preset directly
    def _apply_preset(self, ss, ee):
        st = self._parse_time(ss)
        ed = self._parse_time(ee)
        if st is None or ed is None or st >= ed:
            return
        self.start_pos, self.end_pos = st, ed
        self.player.setPosition(st)
        self._update_loop_overlay()

    def _build_header(self):
        self.label = QLabel("← it's time to practice…", self)
        self.label.setStyleSheet("font-size:20px;font-weight:bold;color:#fff")

        self.upload_btn = QPushButton("📁", self)
        self.upload_btn.setFixedSize(40, 40)
        self.upload_btn.setStyleSheet("font-size:35px;background:#000000;border-radius:5px")
        self.upload_btn.clicked.connect(self._open_file)

        row = QHBoxLayout()
        row.addWidget(self.upload_btn)
        row.addWidget(self.label)
        self.main.addLayout(row)

    def _build_range_controls(self):
        self.start_in = QLineEdit(self)
        self.end_in   = QLineEdit(self)
        for e in (self.start_in, self.end_in):
            e.setPlaceholderText("mm:ss  or  ss")

        self.set_range = QPushButton("GO", self)
        self.set_range.setFixedSize(40, 40)
        self.set_range.setEnabled(False)
        self.set_range.setStyleSheet(
            "font-size:20px;background:#67ce61;color:#fff;border-radius:5px"
        )
        self.set_range.clicked.connect(self._apply_range)

        self.save_range_btn = QPushButton("SAVE", self)
        self.save_range_btn.setFixedSize(40, 40)
        self.save_range_btn.setEnabled(False)
        self.save_range_btn.setStyleSheet(
            "font-size:16px;background:#FFC107;color:#000;border-radius:5px"
        )
        self.save_range_btn.clicked.connect(self._save_current_range)

        row = QHBoxLayout()
        row.addWidget(QLabel("RANGE:"))
        row.addWidget(self.start_in)
        row.addWidget(QLabel("→"))
        row.addWidget(self.end_in)
        row.addWidget(self.set_range)
        row.addWidget(self.save_range_btn)
        self.main.addLayout(row)

    def _build_cover(self):
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
        self.progress = SeekSlider(Qt.Horizontal, self)
        self.progress.setStyleSheet(RED_SLIM)
        self.progress.sliderPressed.connect(lambda: setattr(self, "scrubbing", True))
        self.progress.sliderReleased.connect(self._seek_released)
        self.progress.sliderMoved.connect(self._seek_moved)
        self.progress.sliderClicked.connect(self._seek_clicked)

        self.loop_overlay = LoopOverlay(self.progress)
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
        self.spd = QSlider(Qt.Horizontal, self)
        self.spd.setStyleSheet(BLUE_SLIM)

        self.slbl = QLabel(self)
        self.spd.valueChanged.connect(
            lambda v: (
                self.player.setPlaybackRate(v / 100),
                self.slbl.setText(f"{v}%")
            )
        )

        row = QHBoxLayout()
        row.addWidget(QLabel("SPEED:"))
        row.addWidget(self.spd)
        row.addWidget(self.slbl)
        self.main.addLayout(row)

    def _build_presets_row(self):
        self.preset_row = QHBoxLayout()
        self.preset_row.addWidget(QLabel("SPEED PRESETS:"))
        self.main.addLayout(self.preset_row)

    def _build_range_presets_row(self):
        self.range_preset_row = QHBoxLayout()
        self.range_preset_row.addWidget(QLabel("RANGE PRESETS:"))
        self.main.addLayout(self.range_preset_row)

    def _refresh_presets_ui(self, first_time=False):
        # speed slider update
        max_val = max(100, *self.speed_presets)
        self.spd.setRange(1, max_val)
        self.spd.setValue(100 if first_time else min(self.spd.value(), max_val))
        self.slbl.setText(f"{self.spd.value()}%")

        # build menu
        self.menuBar().clear()
        menu = self.menuBar().addMenu("PRESETS")
        # Speed presets submenu
        speed_menu = menu.addMenu("Speed Presets")
        for v in self.speed_presets:
            speed_menu.addAction(QAction(f"{v}%", self, triggered=lambda _, vv=v: self.spd.setValue(vv)))
        # Range presets submenu
        range_menu = menu.addMenu("Range Presets")
        for s, e in self.range_presets:
            if s and e:
                label = f"{s} → {e}"
                range_menu.addAction(QAction(label, self, triggered=lambda _, ss=s, ee=e: (self.start_in.setText(ss), self.end_in.setText(ee))))
        # Edit actions
        menu.addSeparator()
        menu.addAction(QAction("Edit Speed…", self, triggered=self._edit_presets))
        menu.addAction(QAction("Edit Ranges…", self, triggered=self._edit_ranges))

        # refresh speed presets row
        while self.preset_row.count() > 1:
            item = self.preset_row.takeAt(1)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for v in self.speed_presets:
            btn = QPushButton(f"{v}%", self)
            btn.clicked.connect(lambda _, vv=v: self.spd.setValue(vv))
            self.preset_row.addWidget(btn)

    def _refresh_range_presets_ui(self):
        # clear old
        while self.range_preset_row.count() > 1:
            item = self.range_preset_row.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()
        # add new
        for s, e in self.range_presets:
            label = f"{s}→{e}" if s and e else "-"
            btn = QPushButton(label, self)
            btn.setEnabled(bool(s and e))
            btn.clicked.connect(lambda _, ss=s, ee=e: self._apply_preset(ss, ee))
            self.range_preset_row.addWidget(btn)

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

    def _save_current_range(self):
        start = self.start_in.text().strip()
        end = self.end_in.text().strip()
        if not start or not end:
            return
        try:
            def to_ms(t):
                if ':' in t:
                    m, s = map(int, t.split(':'))
                    return (m * 60 + s) * 1000
                return int(t) * 1000
            _ = to_ms(start)
            _ = to_ms(end)
        except:
            return
        idx = next((i for i, (s, e) in enumerate(self.range_presets) if not s or not e), 0)
        self.range_presets[idx] = (start, end)
        self._refresh_range_presets_ui()
        self._store_presets()

    def _store_presets(self):
        if not self.current_key:
            return
        self.presets_data[self.current_key] = {
            'speed_presets': self.speed_presets,
            'range_presets': self.range_presets
        }
        try:
            with open(self.presets_file, 'w') as f:
                json.dump(self.presets_data, f, indent=2)
        except:
            pass

    def eventFilter(self, src, ev):
        if ev.type() == QEvent.KeyPress and ev.key() == Qt.Key_Space:
            self._toggle_play()
            return True
        if src is self.progress and ev.type() == QEvent.Resize:
            self.loop_overlay.resize(self.progress.size())
            self.loop_overlay.update()
        return super().eventFilter(src, ev)

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Audio", "",
            "Audio Files (*.mp3 *.flac *.m4a *.ogg);;All Files (*)"
        )
        if not path:
            return
        # load media
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        base = os.path.splitext(os.path.basename(path))[0]
        # extract metadata for key
        meta = MutagenFile(path, easy=True)
        artist = (meta.tags.get('artist') or ['Unknown'])[0] if meta and meta.tags else 'Unknown'
        title = (meta.tags.get('title') or [base])[0] if meta and meta.tags else base
        key = f"{artist} - {title}"
        self.current_key = key
        # load presets for this song
        song_presets = self.presets_data.get(key, {})
        self.speed_presets = song_presets.get('speed_presets', [20, 50, 80])
        self.range_presets = song_presets.get('range_presets', [("", ""),("", ""),("", "")])
        # update UI
        self._refresh_presets_ui(first_time=True)
        self._refresh_range_presets_ui()

        # update header and controls
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
        audio = MutagenFile(path, easy=False)
        pix = QPixmap()

        if isinstance(audio, FLAC) and getattr(audio, 'pictures', None):
            pix.loadFromData(audio.pictures[0].data)
        elif isinstance(audio, MP3):
            tags = audio.tags or ID3(path)
            for tag in tags.values():
                if isinstance(tag, APIC):
                    pix.loadFromData(tag.data)
                    break
        elif isinstance(audio, MP4):
            covr = audio.tags.get('covr')
            if covr and isinstance(covr[0], MP4Cover):
                pix.loadFromData(bytes(covr[0]))
        elif isinstance(audio, OggVorbis):
            pic_data = audio.get('metadata_block_picture')
            if pic_data:
                raw = base64.b64decode(pic_data[0])
                pic = Picture()
                pic.parse(raw)
                pix.loadFromData(pic.data)

        if not pix.isNull():
            self.cover.setPixmap(
                pix.scaled(500, 500,
                           Qt.KeepAspectRatioByExpanding,
                           Qt.SmoothTransformation)
            )
        self.play_btn.raise_()

    def _toggle_play(self):
        if self.player.media().isNull():
            return
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_btn.setText("▶")
        else:
            self.player.play()
            self.play_btn.setText("⏸")

    def _seek_moved(self, v):
        self.time_lbl.setText(f"{self._fmt(v)} / {self._fmt(self.duration)}")

    def _seek_released(self):
        self.player.setPosition(self.progress.value())
        self.scrubbing = False

    def _seek_clicked(self, v):
        self.player.setPosition(v)

    def _refresh_ui(self):
        if self.scrubbing or not self.duration:
            return
        pos = self.player.position()
        if self.end_pos is not None and pos >= self.end_pos:
            self.player.setPosition(self.start_pos)
            return

        self.progress.blockSignals(True)
        self.progress.setValue(pos)
        self.progress.blockSignals(False)
        self.time_lbl.setText(f"{self._fmt(pos)} / {self._fmt(self.duration)}")

    def _duration_changed(self, d):
        self.duration = d
        self.progress.setRange(0, d)
        self.progress.setValue(0)
        self.time_lbl.setText(f"{self._fmt(0)} / {self._fmt(d)}")
        self._update_loop_overlay()

    def _media_status(self, status):
        if status == QMediaPlayer.EndOfMedia and self.end_pos is None:
            self.player.setPosition(0)
            self.player.play()

    def _apply_range(self):
        def to_ms(text):
            t = text.strip()
            if ':' in t:
                try:
                    m, s = map(int, t.split(':'))
                    return (m * 60 + s) * 1000
                except ValueError:
                    return None
            return int(t) * 1000 if t.isdigit() else None

        st = to_ms(self.start_in.text())
        ed = to_ms(self.end_in.text())
        if st is None or ed is None or st >= ed:
            return

        self.start_pos, self.end_pos = st, ed
        self.player.setPosition(st)
        self._update_loop_overlay()

    def _update_loop_overlay(self):
        self.loop_overlay.set_loop(self.start_pos, self.end_pos, self.duration)

    @staticmethod
    def _fmt(ms):
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}.{ms:03d}"


# ──────────────────────────────── Run ────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = AudioPlayer()
    gui.show()
    sys.exit(app.exec_())
