# PyInstaller recipe: builds one folder with two programs that share all libraries:
#   "Transcribe Anywhere"      - the app (no console window on Windows)
#   "transcribe-anywhere-cli"  - command line tools for testing/support
# Build:  pyinstaller packaging/transcribe_anywhere.spec --noconfirm
# The speech model is NOT bundled; it is downloaded on first use.

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files("faster_whisper")            # Silero VAD model
datas += [("../src/transcribe_anywhere/assets/app.ico", "transcribe_anywhere/assets")]
binaries = (collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("onnxruntime")
            + collect_dynamic_libs("sherpa_onnx"))

# Never ship NVIDIA libraries (~1-2 GB); target laptops run on the CPU.
excludes = ["nvidia", "tkinter", "pytest", "pyflakes", "IPython"]

a = Analysis(
    ["launch.py"],
    pathex=["../src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=["transcribe_anywhere.ui.app", "keyring.backends.Windows"],
    excludes=excludes,
)
pyz = PYZ(a.pure)

gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Transcribe Anywhere",
          console=False, icon="../src/transcribe_anywhere/assets/app.ico")
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="transcribe-anywhere-cli",
          console=True, icon=None)

COLLECT(gui, cli, a.binaries, a.datas, name="TranscribeAnywhere")
