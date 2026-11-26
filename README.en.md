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

- **100% local, zero cloud, no account:** your PDFs never leave your computer. Unlocking, irreversible redaction, digital & visual signing, offline OCR, and compression run locally with no daily task limits.
- **One-time purchase after a 15-day full trial:** no monthly subscriptions, no upgrade popups, and no paywalled everyday features.
- **Complete lightweight toolkit (~92 MB):** estimate compression savings before saving and compare side by side at 100%, sign with certificates (single or batch) or visual `PNG`/`JPG`/`PDF` signatures, compare two PDFs visually (documents, images, or drawings), run unlimited offline OCR, and export to Word, Excel, and Markdown.
- **Sustainable open source:** the full source code is public under the MIT License and can be built and run for free. The official Microsoft Store package funds ongoing development and updates.

## Feature screenshots

| Smart compression (3 presets + advanced) | Signatures panel in dark mode |
| :---: | :---: |
| ![Smart PDF compression dialog](docs/screenshots/compress.png) | ![Card-based signatures explorer in dark mode](docs/screenshots/signatures-dark.png) |

| Visual signature (PNG, JPG, or PDF) | Drag-and-drop page organizer |
| :---: | :---: |
| ![Visual signature with automatic white background removal](docs/screenshots/visual-sign.png) | ![Visual thumbnail grid to reorder, rotate, and delete pages](docs/screenshots/organize.png) |

## What you can do

| Area | Features |
| --- | --- |
| **Read & navigate** | Detachable multi-window tabs, always-visible **Page X of Y** indicator, continuous scroll or **two-page view (`Ctrl+2`)**, light & dark themes, resizable sidebar, bookmark filtering, quick find (`Ctrl+F`), and command palette (`Ctrl+K`). |
| **Organize, merge & split** | **Visual page grid** with drag-and-drop reordering, rotation, and deletion; merge multiple PDFs with an automatic outline, **split PDF** by ranges or every N pages, extract pages, multiple pages per sheet, and batch workspace. |
| **Compress PDF** | **3 simple presets** (*Low*, *Recommended*, *Extreme*) plus **Advanced options**: **estimate beforehand whether you'll save space**, compress `RGB`, `ICCBased`, `CMYK`, `JPEG2000`, and transparent (`SMask`) images, optional grayscale conversion, bloat/thumbnail/metadata cleanup, and **100% side-by-side visual comparison** before saving. |
| **Edit & annotate** | Edit supported text, add new text, fill and flatten **AcroForm** fields, headers, footers, and page numbering; highlights, underlines, sticky notes, shapes, and filterable annotations panel. |
| **Sign (certificate & visual)** | **PAdES (RSA & ECDSA)** single or **batch signing** with Windows certificates or `.pfx`/`.p12` files, **visual signatures from `PNG`, `JPG`, `WebP`, or `PDF`** with automatic white-background removal, and card-based signature explorer with integrity verification. |
| **Protect & privacy** | **Offline PDF unlock without subscriptions**, **AES-256** password protection, **true irreversible redaction** (removes underlying content with optional OCR), and **clean metadata-free copy for sharing**. |
| **Offline OCR & export** | **Unlimited offline OCR** in English and Spanish (Tesseract). Export to **Word (`.docx`)**, **Excel (`.xlsx`)**, **CSV**, **Markdown (`.md`)** with preview, **TXT**, **PNG**, **PDF/A**, and **copy page as image** (`Ctrl+Shift+C`). |
| **Compare PDFs, drawings & print** | **Compare two PDFs visually** (documents, images, or drawings) side by side, overlaid, or with color-coded diffs; calibrate `1:N` scales and measure lengths, perimeters, and areas. Print preview with actual size, tiled sheets, and booklets. |

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
