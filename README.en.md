<img src="assets/brand/pdfiu-wordmark.svg" alt="PDFiu" width="220">

# PDFiu

[Español](README.md) · **English**

An open-source PDF reader and editor created by **mfcb89**. Open, organize, sign, and convert documents from a desktop app. PDFiu processes PDF files on your computer and requires no account. The interface and guided tour are available in Spanish and English.

![PDFiu in English showing the welcome document, thumbnails, and tools](docs/pdfiu-en.png)

## What you can do

| Area | Features |
| --- | --- |
| Read | Continuous scrolling, zoom, full screen, thumbnails, bookmarks, layers, and search with context, optional accent matching, and operators. |
| Organize pages and batches | Keep several PDFs in a workspace, merge with an index, extract or reorder pages, insert them by dragging, rotate pages, and arrange multiple pages per sheet. |
| Edit and review | Edit supported text, fill AcroForm fields, and add comments, highlights, shapes, headers, footers, and page numbers. |
| Sign and protect | Add visible certificate signatures to pages or batches, inspect signature details, protect copies, and redact areas. |
| Work with drawings | Compare side by side, overlay drawings, or highlight changes. Calibrate a known distance or drawing scale and measure length, perimeter, and area. |
| OCR and export | Recognize English and Spanish on one page or throughout a PDF. Export to Word, Excel, CSV, Markdown with preview, TXT, or PNG. Copy a page as an image. |
| Print and prepare copies | Preview print output, print at actual size, fit, tile, or make a booklet. Estimate compression and export PDF/A with external tools. |

[User guide](USER_GUIDE.en.md) · [Build guide](packaging/LEEME.en.md)

## Run from source

The public repository contains the source code. The installer recipe targets Windows x64. Build the macOS package on macOS and validate it on the target architecture.

1. Open a PowerShell terminal with Git and 64-bit Python 3.12.
2. Clone the repository and run these commands.

```powershell
git clone https://github.com/mfcb89/pdfiu.git
cd pdfiu
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe pdfiu.py
```

If you already have a clone open in an editor such as Antigravity, start in the repository folder. For OCR, place `spa.traineddata` and `eng.traineddata` in `runtime/tessdata`. [Set up OCR models](USER_GUIDE.en.md#set-up-ocr-models)

## Compatibility

- Form editing uses AcroForm. Forms that rely entirely on dynamic XFA need an XFA-compatible reader.
- Basic signing uses P12/PFX files and, on Windows, supported certificates from the system store. The signatures panel displays available certificate details. Chain trust, timestamping, and long-term validation are outside this version.
- Word export reconstructs the layout approximately. Complex drawings, columns, and scans may need manual adjustment.
- PDF/A needs Ghostscript, veraPDF, and Java. Redaction rasterizes marked pages and offers OCR to recover visible text. [Usage details](USER_GUIDE.en.md)

## Contribute and license

Open an [issue](https://github.com/mfcb89/pdfiu/issues) or submit a pull request. Spanish and English are welcome. [Contribution guide](CONTRIBUTING.md)

The original PDFiu code and logo are available under the [MIT License](LICENSE). You can use, modify, and redistribute the code, including commercially, if you keep the copyright and license notice. Third-party libraries and assets have their own terms. Review the [third-party notices](THIRD_PARTY_NOTICES.md#english) before redistributing an installer.
