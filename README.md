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

The latest release can be found on the [Releases page](https://github.com/yourusername/PracticeHard/releases).

**How to get started:**

1. Download the latest release archive (`.zip` or `.tar.gz`) from the Releases page.
2. Extract the files to your preferred directory.
3. Install dependencies:

   ```bash
   pip install PyQt5 mutagen
   ```
4. Run the app:

   ```bash
   python practice_hard.py
   ```

**Changelog:**
See [CHANGELOG.md](CHANGELOG.md) for details on new features, bug fixes, and updates.

*If there is no release yet, stay tuned! The first official release is coming soon.*

---

## 🛠️ Installation

```bash
pip install PyQt5 mutagen
```

---

## ▶️ Usage

1. Run `practice_hard.py`
2. Open an audio file and start playback
3. Adjust loop range and speed, save presets
4. Level up your skills with relentless practice!

---

## 🖥️ Packaging as a Standalone Application

### macOS (using PyInstaller)

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

4. After building, you’ll find the app in the `dist/` folder. You can distribute this `.app` directly without requiring users to install Python or dependencies.

### Windows (using PyInstaller)

1. Install PyInstaller:

   ```bash
   pip install pyinstaller
   ```
2. Convert the icon to Windows format (`.ico`) if necessary, naming it `practice_hard.ico`, and place it in the project root.
3. Build the executable:

   ```bash
   pyinstaller \
     --windowed \
     --name "Practice Hard!" \
     --icon "practice_hard.ico" \
     practice_hard.py
   ```
4. After building, you’ll find the exe and its supporting files in the `dist/Practice Hard!/` directory. Share this folder with Windows users to run the app standalone.

---

## 🤝 Contributing

* Issues and PRs are welcome!
* Contribution guidelines will be added soon

---

## 📄 License

MIT License

Created by GM7595 (part_time_metalhead)