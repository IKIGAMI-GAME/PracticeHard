---

## 🚀 Overview

Practice Hard! is a powerful audio player designed for language learners, musicians, and anyone who wants to master listening skills through repetition.
With an intuitive UI and robust preset features, it supercharges your practice sessions.

---

## 🖼️ Demo

---

## ✨ Features

* ⏩ **Speed Presets** (One-tap switching: 20%, 50%, 80%, etc.)
* 🔁 **Custom Loop Playback & Save**
* 🎨 **Automatic Cover Art Display**
* 🖱️ **Intuitive UI with Giant Play Button**
* 💾 **Per-song Preset Saving**
* 🎵 **Supports Multiple Formats (mp3, flac, m4a, ogg, ...)**

---

## 🗃️ Release

The latest release can be found on the [Releases page](https://github.com/IKIGAMI-GAME/PracticeHard/releases).

---

## ▶️ Usage

1. Run `practice_hard.py`
2. Open an audio file (click or press the spacebar to play/pause)
3. Adjust playback speed and loop range, then save presets
4. Level up your skills with relentless practice!

---

## 🖥️ Packaging as a Standalone Application (macOS only)

1. Install PyInstaller if you haven't already:

   ```bash
   pip install pyinstaller
   ```
2. Place the macOS icon file `practice_hard.icns` in the project root.
3. Build the app bundle with one of the following methods:

**Single-line command** (avoids shell prompts):

```bash
pyinstaller --windowed --name 'Practice Hard!' --icon practice_hard.icns practice_hard.py
```

4. After building, you’ll find the app in the `dist/` folder. The resulting `.app` includes Python and all necessary dependencies (e.g. PyQt5, mutagen), so users can run it directly without installing anything.

## 🤝 Contributing

* Issues and PRs are welcome!
* Contribution guidelines will be added soon

---

## 📄 License

MIT License

Created by Taichi Sawamura