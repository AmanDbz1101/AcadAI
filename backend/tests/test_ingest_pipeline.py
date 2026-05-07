from pathlib import Path

import pytest

from backend.extraction.app.validation import ValidationResult
from backend.extraction.models.document import OCRMetadata, PageContent
from backend.extraction.pipelines.ingest_pipeline import DeduplicationSkipped, IngestPipeline


class FakeValidator:
    def __init__(self, pdf_hash: str = "hash123"):
        self.pdf_hash = pdf_hash
        self.calls = 0

    def validate(self, pdf_path: Path) -> ValidationResult:
        self.calls += 1
        return ValidationResult(
            is_valid=True,
            pdf_path=Path(pdf_path),
            pdf_hash=self.pdf_hash,
            page_count=1,
            file_size_bytes=10,
            errors=[],
        )


class FakeLoader:
    def __init__(self):
        self.calls = 0

    def load(self, pdf_path: Path):
        self.calls += 1
        page = PageContent(
            page_number=1,
            text="hello world",
            word_count=2,
            char_count=11,
        )
        return {
            "pages": [page],
            "full_text": "hello world",
            "metadata": {},
            "page_count": 1,
            "processing_time": 0.01,
        }


class FakeOCRHandler:
    def process_if_needed(self, pdf_path: Path, pages):
        return {
            "pages": pages,
            "ocr_metadata": OCRMetadata(
                was_ocr_applied=False,
                text_density_ratio=100,
            ),
            "was_reprocessed": False,
        }


def test_incremental_cache_reuse(tmp_path: Path):
    validator = FakeValidator()
    loader = FakeLoader()
    pipeline = IngestPipeline(
        validator=validator,
        loader=loader,
        ocr_handler=FakeOCRHandler(),
        enable_ocr=False,
        enable_incremental=True,
        cache_dir=tmp_path,
    )

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"fake")

    first = pipeline.process(pdf_path)
    assert loader.calls == 1
    assert (tmp_path / "hash123_ingest.json").exists()

    second = pipeline.process(pdf_path)
    assert loader.calls == 1
    assert first.document_id == second.document_id


def test_deduplication_skips():
    validator = FakeValidator(pdf_hash="dupe_hash")
    loader = FakeLoader()
    pipeline = IngestPipeline(
        validator=validator,
        loader=loader,
        ocr_handler=FakeOCRHandler(),
        enable_ocr=False,
        dedup_checker=lambda _hash: 123,
    )

    with pytest.raises(DeduplicationSkipped):
        pipeline.process(Path("/tmp/dupe.pdf"), skip_if_exists=True)
