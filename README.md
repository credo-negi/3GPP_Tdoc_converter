# 3GPP Tdoc converter

Tdoc list (xlsx) → download zips → unzip → docx/pptx → Markdown → Observation/Proposal list.

```
python3 -m tdoc_converter 10.5.2.2            # uses the xlsx in Tdoc_List/
python3 -m tdoc_converter 10.5.2.2 --limit 3  # try the first 3 Tdocs
python3 -m tdoc_converter 10.5.2.2 --check-urls  # only HEAD-check the download links
python3 -m unittest discover -s tests -t .    # offline tests
```

Needs: pandas, openpyxl, requests, markitdown, python-docx, python-pptx, Pillow (tests).

Output: `output/<meeting folder>/<agenda item>/{zip,extracted,markdown,results}`;
`markdown/<tdoc>.md` links its figures as `images/<tdoc>/imgNNN.png` (saved next to it; identical images stored once);
`results/observations_proposals.{md,json}` hold the extracted statements.

Notes
- Download URLs are the hyperlinks on the TDoc cells of the xlsx; see [docs/download_url.md](docs/download_url.md)
  (how they are read, the fallback rule, server quirks, verification results).
- EMF/WMF figures cannot be shown by browsers/Markdown viewers. They are converted to PNG if Inkscape or LibreOffice
  is installed; otherwise the original `.emf`/`.wmf` is kept and linked (the converter call is only covered by a mocked test; Inkscape/LibreOffice are not installed here).
- Many Tdocs store "Proposal N:" as Word auto-numbering; `numbering.py` writes those labels into the text before conversion.
- Statements inside tables (quoted earlier agreements) are skipped; a statement repeated in the Conclusion is merged.
- Legacy `.doc` needs macOS `textutil` or LibreOffice.
