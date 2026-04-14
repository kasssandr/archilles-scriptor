"""OCR backend — deferred. Scan PDFs are out of scope for now."""


def extract(pdf_path, out_dir):
    raise NotImplementedError(
        "OCR backend is not implemented yet. Use pymupdf_backend for text PDFs."
    )
