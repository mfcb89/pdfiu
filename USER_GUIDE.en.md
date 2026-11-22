# PDFiu user guide

[Español](LEEME.md) · **English** · [Home](README.en.md)

## Open and read a PDF

Press **Ctrl+O** or drag PDFs onto the window. On Windows, **File → Recent documents** lists the last ten documents. Under **Edit → Preferences**, choose English, Spanish, or the system language and restart. To practice with the sample PDFs, open **Help → Guided tour**. Use the panel icons to show files, page thumbnails, bookmarks, layers, comments, and signatures.

Scroll to move between pages. Use **Ctrl + mouse wheel** to zoom or enter a percentage in the left bar. Hold **Space** and drag to pan when zoomed in. Use **Ctrl+F** to search and **F3** or **Shift+F3** to move between matches. Turn on accent matching to distinguish `medicion` from `medición`. In advanced search, use uppercase operators and quotes, for example `(plan OR drawing) AND NOT "draft only"`.

Press **Ctrl+S** to save or **Ctrl+Shift+S** to save a separate copy. Use **Ctrl+W** to close the document. PDFiu asks before overwriting a file and offers recovery of eligible unsaved copies after an unexpected exit.

## Organize and edit pages

Select files in the workspace and choose **Merge PDFs**. Set the order and add an index if you want a bookmark for each input. Drag thumbnails to reorder pages. Drop a PDF between thumbnails to insert it or drag pages from another PDFiu window. Select a range such as `1,3-5` to extract pages. Choose **Multiple pages per sheet** to create a copy with a page grid. Press **Delete** in the workspace to remove a file from the list. The file remains on disk.

Use **Edit text** on supported text blocks. Editing keeps the original font where it supports the new characters and does not reflow paragraphs. Click highlighted AcroForm fields to fill them. Use the forms menu to clear values or flatten fields. A hybrid XFA form can be copied as AcroForm when compatible fields are available. Keep the original if you need to submit dynamic XFA.

Use **Annotate** to highlight or underline selected text and add notes, rectangles, ovals, lines, or arrows. The comments panel helps you find and remove annotations. The header and footer editor supports page ranges, style, and page, total, and filename placeholders. Use **Number pages** for a page-number-only job.

## Sign, protect, and redact

- **Sign with certificate.** Draw a rectangle on the page and choose a supported certificate from the Windows certificate store or a P12/PFX file. Save a signed copy. To sign several PDFs, select them in the workspace or use batch signing. You can choose where the rectangle goes in each file or apply the same placement across the batch. Signing multiple pages creates a signature on each selected page.
- **Inspect signatures.** Use the signature banner, the sidebar, or the signature box in the document. The panel displays details available in the file, such as signer, issuer, validity dates, and coverage. Those details do not establish that the certificate chain is trusted.
- **Unlock a copy.** If a PDF opens without a password, PDFiu can remove its usage restrictions. If it requires a password to open, enter it first. PDFiu warns when an operation will remove signatures. Keep the signed original.
- **Redact a copy.** Draw the redaction boxes and save a new file. Marked pages are rasterized. The optional searchable mode runs OCR after redaction. The output omits interactive forms, annotations, bookmarks, and attachments. Inspect the saved copy before sharing it.

## Compare drawings and measure

Open an original and a revision in the comparison dialog. **Side by side** synchronizes navigation. **Overlay** tints the revision and makes white transparent. **Differences** highlights additions, removals, and color changes. Adjust tolerance and alignment when needed. To measure, enter a scale or pick two points a known distance apart. Save area measurements as annotations and find them later in the surfaces panel.

## Export, print, and compress

- Export all pages, the current page, or a range. PDFiu supports Word, Excel, CSV, Markdown with preview, plain text, and PNG. Word export with formatting reconstructs fonts, images, colors, and tables approximately. Use **Copy page** to paste an entire page as an image.
- With several documents selected, choose a format and an output folder. Images use page numbers in their filenames. When a filename already exists, PDFiu adds a suffix.
- Use **Ctrl+P** to preview print output and select actual size, fit, a custom scale, tiled sheets, multiple pages per sheet, or booklet printing. Printer properties open the driver panel on Windows. The print dialog's PDF output reproduces the print layout as images.
- Compare a compressed copy with the original at 100%. The size estimate samples up to eight pages. The reduced-size preset uses 150 dpi and the extreme preset uses 96 dpi. Review details closely on scanned drawings.
- Use **Save a PDF/A copy** with Ghostscript, veraPDF, and Java installed to create and validate PDF/A-1b, PDF/A-2b, or PDF/A-3b. Convert and validate before signing.

## Set up OCR models

After [installing the Python dependencies](README.en.md#run-for-free-from-source), download the models from PowerShell in the repository folder.

```powershell
New-Item -ItemType Directory -Force -Path .\runtime\tessdata | Out-Null
foreach ($lang in @('spa', 'eng')) {
    Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/$lang.traineddata" -OutFile ".\runtime\tessdata\$lang.traineddata"
}
```

Open PDFiu, choose **Recognize text (OCR)**, and select a language and the current page or the whole document. Save the result to keep the searchable text layer.
