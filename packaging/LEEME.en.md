# Build PDFiu

[Español](LEEME.md) · **English** · [Home](../README.en.md)

## Windows x64

Install 64-bit Python 3.12 and Inno Setup 6.3 or later. From the repository root, prepare the [OCR models](../USER_GUIDE.en.md#set-up-ocr-models) and run the commands below. Replace `ISCC.exe` with its full path if it is outside your PATH.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install PyInstaller
.\.venv\Scripts\python.exe packaging/build_app.py --tessdata runtime/tessdata --output build
$env:PDFIU_BUILD_DIR = (Resolve-Path build).Path
ISCC.exe packaging/windows.iss
```

Find the installer in `build/installer`. The version comes from `release_info.py`. Use `--dry-run` to inspect the PyInstaller command. Test installation, update, uninstall, launch without Python, OCR in both languages, and both the Windows certificate store and PFX signing.

An optional `--updates-url` argument accepts an HTTPS link to an update manifest. The manifest uses `version` and `url` fields. The update command opens the download page if there is a newer version.

## macOS

Build on macOS with Python 3.12, native dependencies for your architecture, PyInstaller, and both OCR models. Run `python packaging/build_app.py --tessdata runtime/tessdata --output build` in the activated environment. Test Apple Silicon and Intel builds separately. P12/PFX signing uses the cross-platform code path. Windows certificate store integration is specific to Windows. Sign and notarize the package as required for your distribution channel.

## Distribute builds

The build generates a `third-party` folder with a dependency inventory and license notices. It also identifies items for review. Keep these notices with the package and verify the requirements that apply to the actual libraries you bundle, including the corresponding source and replaceability of LGPL libraries where required. [Third-party notices](../THIRD_PARTY_NOTICES.md#english) · [Qt licensing guidance](https://www.qt.io/development/open-source-lgpl-obligations)
