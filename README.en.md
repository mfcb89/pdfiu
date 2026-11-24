<img src="assets/brand/pdfiu-wordmark.svg" alt="PDFiu" width="220">

# PDFiu

[Español](README.md) · **English**

![Version 0.12.1](https://img.shields.io/badge/version-0.12.1-2f7d6d?style=flat-square)
![MIT License](https://img.shields.io/badge/license-MIT-182a3d?style=flat-square)
![Windows x64](https://img.shields.io/badge/Windows-x64-294459?style=flat-square)
![100% Local](https://img.shields.io/badge/privacy-100%25%20local%20%C2%B7%20no%20account-317f72?style=flat-square)

An open-source PDF reader and editor created by **mfcb89**, built as a lightweight, 100% local alternative to heavy proprietary PDF readers. Open, organize, edit, sign, measure drawings, and convert documents from a desktop app with no account, no cloud, and no telemetry. The interface (with light and dark themes) and guided tour are available in Spanish and English.

![PDFiu in English showing the welcome document, thumbnails, and tools](docs/pdfiu-en.png)

## Why PDFiu

- **100% local and private:** your PDFs stay on your computer. PDFiu requires no account and makes no network requests unless you manually check for updates or enable the opt-in startup update check.
- **Complete desktop toolkit:** includes features commonly locked behind paid subscriptions (merging and organizing pages, editing text, filling forms, English/Spanish OCR, digital signatures, redaction, drawing comparison/measurement, and exporting to Word, Excel, and Markdown).
- **Sustainable open source:** the full source code is public under the MIT License and can be built and run for free. The paid official Windows installer funds ongoing development, code signing, and updates.

## What you can do

| Area | Features |
| --- | --- |
| **Read & navigate** | Detachable multi-window tabs, continuous scroll or **two-page view (`Ctrl+2`)**, light & dark themes, full screen, thumbnails, bookmark filtering, quick find (`Ctrl+F`) with accent/operator support, and command palette (`Ctrl+K`). |
| **Organize, merge & split** | **Visual page grid** with drag-and-drop reordering, rotation, and deletion; merge multiple PDFs with an automatic outline, **split PDF** by ranges or every N pages, extract pages, multiple pages per sheet, and batch workspace. |
| **Compress PDF** | **3 simple presets** (*Low*, *Recommended*, *Extreme*) plus **Advanced options**: compresses `RGB`, `ICCBased`, `CMYK`, `JPEG2000`, and transparent (`SMask`) images, optional grayscale conversion, private editing bloat/thumbnail/metadata cleanup, **size estimator**, and **100% side-by-side visual comparison** before saving. |
| **Edit & annotate** | Edit supported text, add new text, fill and flatten **AcroForm** fields, headers, footers, and page numbering; highlights, underlines, sticky notes, shapes, and filterable annotations panel. |
| **Digital signatures** | **PAdES (RSA & ECDSA)** signing with Windows certificate store or `.pfx`/`.p12` files, visible signature box, **batch signing**, and signature explorer with integrity verification. |
| **Protect & privacy** | **Unlock PDFs**, encrypt copies with **AES-256** passwords, **irreversible redaction** (removes real underlying content with optional OCR), and **prepare a clean copy for sharing** without metadata. |
| **Offline OCR & export** | **Local OCR** in English and Spanish (Tesseract) on one page or the entire document. Export to **Word (`.docx`)**, **Excel (`.xlsx`)**, **CSV**, **Markdown (`.md`)** with preview, **TXT**, **PNG**, **PDF/A**, and **copy page as image** (`Ctrl+Shift+C`). |
| **Drawings & printing** | Compare revisions side by side, overlaid, or with color-coded diffs; calibrate `1:N` scales and measure lengths, perimeters, and areas. Print preview with actual size, tiled sheets, and booklets. |

[User guide](USER_GUIDE.en.md) · [Build guide](packaging/LEEME.en.md) · [Privacy policy](PRIVACY.md) · [Changelog](CHANGELOG.md)

## Get PDFiu

### Official Store app (Microsoft Store · Windows x64)

The ready-to-use Windows 10/11 package (no Python setup required, English & Spanish OCR models bundled, one-time purchase with a **15-day free trial**) is available on the [Microsoft Store](https://apps.microsoft.com/detail/9NK06R3SRRW3) and funds ongoing development and updates.

### Run for free from source

The public repository contains the complete source code. The installer recipe targets Windows x64; build the macOS package on macOS and validate it on the target architecture.

1. Open a PowerShell terminal with Git and 64-bit Python 3.12.
2. Clone the repository and run these commands:

```powershell
git clone https://github.com/mfcb89/pdfiu.git
cd pdfiu
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe pdfiu.py
```

To enable English and Spanish OCR, place `spa.traineddata` and `eng.traineddata` in `runtime/tessdata`. [Set up OCR models](USER_GUIDE.en.md#set-up-ocr-models)

## Compatibility

- Form editing uses AcroForm. Forms that rely entirely on dynamic XFA need an XFA-compatible reader.
- Basic signing uses P12/PFX files and, on Windows, supported certificates from the system store. The signatures panel displays available certificate details. Chain trust, timestamping, and long-term validation are outside this version.
- Word export reconstructs the layout approximately. Complex drawings, columns, and scans may need manual adjustment.
- PDF/A needs Ghostscript, veraPDF, and Java. Redaction rasterizes marked pages and offers OCR to recover visible text. [Usage details](USER_GUIDE.en.md)

## Contribute, security, and license

- Open an [issue](https://github.com/mfcb89/pdfiu/issues) or submit a pull request (Spanish and English are welcome). [Contribution guide](CONTRIBUTING.md)
- To report a security vulnerability privately, see [SECURITY.md](SECURITY.md#english).
- PDFiu's original source code is available under the [MIT License](LICENSE). You can use, modify, and redistribute the code, including commercially, if you keep the copyright and license notice.
- The **PDFiu** name and logos in `assets/brand/` are reserved and are not covered by the MIT License. See the [brand policy](TRADEMARKS.md#pdfiu-trademark-and-brand-policy).
- Third-party libraries and assets have their own terms (including Qt and PySide6 under LGPLv3). Review the [third-party notices](THIRD_PARTY_NOTICES.md#english) before redistributing a binary.
