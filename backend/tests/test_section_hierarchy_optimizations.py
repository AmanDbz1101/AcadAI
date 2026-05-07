from uuid import uuid4

from backend.extraction.app.section_detector import SectionDetector
from backend.extraction.models.metadata import ExtractedMetadata, ProcessedDocument, SectionInfo


def _build_processed_doc(sections, text_blocks):
    metadata = ExtractedMetadata(
        title="Test",
        abstract="Abstract",
        keywords=[],
        sections=sections,
        extracted_elements={"text_blocks": text_blocks},
    )
    return ProcessedDocument(document_id=uuid4(), metadata=metadata)


def test_reading_order_uses_text_block_order():
    detector = SectionDetector()
    sections = [
        SectionInfo(original_name="1 Introduction", level=1, page_start=1),
        SectionInfo(original_name="2 Method", level=1, page_start=2),
    ]
    text_blocks = [
        {"text": "Method text", "section_title": "Method"},
        {"text": "Intro text", "section_title": "Introduction"},
    ]
    processed = _build_processed_doc(sections, text_blocks)

    hierarchy = detector.detect_from_processed_document(processed)
    titles = [s.title for s in hierarchy.sections]
    assert titles[0] == "Method"
    assert titles[1] == "Introduction"


def test_appendix_tagging():
    detector = SectionDetector()
    sections = [
        SectionInfo(original_name="1 Introduction", level=1, page_start=1),
        SectionInfo(original_name="Appendix A Extra", level=1, page_start=10),
    ]
    processed = _build_processed_doc(sections, [])

    hierarchy = detector.detect_from_processed_document(processed)
    appendix_nodes = [s for s in hierarchy.sections if s.section_type == "appendix"]
    assert len(appendix_nodes) == 1
    assert appendix_nodes[0].title.startswith("Appendix")


def test_cross_references_detected():
    detector = SectionDetector()
    sections = [
        SectionInfo(original_name="1 Introduction", level=1, page_start=1),
        SectionInfo(original_name="2 Method", level=1, page_start=2),
        SectionInfo(original_name="Appendix A Extra", level=1, page_start=10),
    ]
    text_blocks = [
        {
            "text": "See Section 2 for details and Appendix A for tables.",
            "section_title": "Introduction",
        }
    ]
    processed = _build_processed_doc(sections, text_blocks)

    hierarchy = detector.detect_from_processed_document(processed)
    mentions = {ref["mention"] for ref in hierarchy.cross_references}
    assert "Section 2" in mentions
    assert "Appendix A" in mentions
