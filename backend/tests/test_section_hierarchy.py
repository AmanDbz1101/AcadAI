"""
Tests for section hierarchy detection module.

Tests the section detector and hierarchy building logic.
"""

import pytest
from pathlib import Path
from uuid import uuid4

from backend.models.document import ValidatedDocument, PageContent
from backend.models.metadata import ProcessedDocument, ExtractedMetadata, SectionInfo
from backend.models.section_hierarchy import SectionNode, SectionHierarchy
from backend.app.processing.section_detector import SectionDetector
from backend.pipelines.section_hierarchy_pipeline import SectionHierarchyPipeline


@pytest.fixture
def sample_sections_info():
    """Create sample section info for testing."""
    return [
        SectionInfo(original_name="1. Introduction", level=1, page_start=1),
        SectionInfo(original_name="1.1 Background", level=2, page_start=2),
        SectionInfo(original_name="1.2 Motivation", level=2, page_start=3),
        SectionInfo(original_name="2. Methodology", level=1, page_start=4),
        SectionInfo(original_name="2.1 Approach", level=2, page_start=5),
        SectionInfo(original_name="2.1.1 Details", level=3, page_start=6),
        SectionInfo(original_name="3. Experiments", level=1, page_start=7),
        SectionInfo(original_name="4. Conclusion", level=1, page_start=8),
    ]


@pytest.fixture
def sample_processed_document(sample_sections_info):
    """Create a sample ProcessedDocument for testing."""
    metadata = ExtractedMetadata(
        title="Test Paper",
        abstract="This is a test abstract.",
        sections=sample_sections_info
    )
    
    return ProcessedDocument(
        document_id=uuid4(),
        metadata=metadata,
        processing_time_seconds=1.0
    )


@pytest.fixture
def sample_validated_document():
    """Create a sample ValidatedDocument for testing."""
    pages = [
        PageContent(
            page_number=1,
            text="Title of the Paper\n\n1. Introduction\nThis is the introduction text.",
            word_count=10,
            char_count=100
        ),
        PageContent(
            page_number=2,
            text="1.1 Background\nBackground information goes here.\n\n1.2 Motivation\nMotivation text.",
            word_count=15,
            char_count=150
        ),
        PageContent(
            page_number=3,
            text="2. Methodology\nOur methodology is described here.",
            word_count=10,
            char_count=80
        ),
    ]
    
    return ValidatedDocument(
        pdf_path=Path("/fake/path/paper.pdf"),
        pdf_hash="fake_hash_123",
        pages=pages,
        page_count=3,
        file_size_bytes=10000
    )


class TestSectionDetector:
    """Tests for SectionDetector class."""
    
    def test_detector_initialization(self):
        """Test detector can be initialized with default parameters."""
        detector = SectionDetector()
        assert detector.min_heading_font_size == 10.0
        assert detector.use_docling_structure is True
    
    def test_detect_from_processed_document(self, sample_processed_document):
        """Test section detection from ProcessedDocument."""
        detector = SectionDetector()
        hierarchy = detector.detect_from_processed_document(sample_processed_document)
        
        assert isinstance(hierarchy, SectionHierarchy)
        assert hierarchy.total_sections == 8
        assert hierarchy.max_depth == 3
        assert len(hierarchy.root_sections) == 4  # 4 level-1 sections
        assert hierarchy.document_id == str(sample_processed_document.document_id)
    
    def test_section_hierarchy_structure(self, sample_processed_document):
        """Test that hierarchy correctly captures parent-child relationships."""
        detector = SectionDetector()
        hierarchy = detector.detect_from_processed_document(sample_processed_document)
        
        # Check introduction section
        intro = hierarchy.find_sections_by_title("Introduction")[0]
        assert intro.level == 1
        assert intro.has_subsections is True
        assert len(intro.child_section_ids) == 2
        
        # Check background subsection
        background = hierarchy.find_sections_by_title("Background")[0]
        assert background.level == 2
        assert background.parent_id == intro.section_id
        
        # Check deep nesting
        details = hierarchy.find_sections_by_title("Details")[0]
        assert details.level == 3
        
        # Test ancestor retrieval
        ancestors = hierarchy.get_ancestors(details.section_id)
        assert len(ancestors) == 2  # Should have 2 ancestors (Approach, Methodology)
    
    def test_section_numbering_extraction(self, sample_processed_document):
        """Test that section numbering is correctly extracted."""
        detector = SectionDetector()
        hierarchy = detector.detect_from_processed_document(sample_processed_document)
        
        intro = hierarchy.find_sections_by_title("Introduction")[0]
        assert intro.numbering is not None
        assert "1" in intro.numbering
        
        # Title should not include numbering
        assert intro.title == "Introduction"
    
    def test_page_ranges(self, sample_processed_document):
        """Test that page ranges are correctly calculated."""
        detector = SectionDetector()
        hierarchy = detector.detect_from_processed_document(sample_processed_document)
        
        intro = hierarchy.find_sections_by_title("Introduction")[0]
        assert intro.page_start == 1
        # page_end should be before next section starts
        
        conclusion = hierarchy.find_sections_by_title("Conclusion")[0]
        # Last section should have page_end = None
        assert conclusion.page_end is None
    
    def test_confidence_calculation(self, sample_processed_document):
        """Test confidence score calculation."""
        detector = SectionDetector()
        hierarchy = detector.detect_from_processed_document(sample_processed_document)
        
        # Should have high confidence with numbered sections
        assert hierarchy.confidence_score > 0.5
        assert 0 <= hierarchy.confidence_score <= 1.0
    
    def test_empty_sections_handling(self):
        """Test handling of documents with no sections."""
        metadata = ExtractedMetadata(
            title="Test Paper",
            abstract="Abstract",
            sections=[]  # No sections
        )
        
        processed_doc = ProcessedDocument(
            document_id=uuid4(),
            metadata=metadata,
            processing_time_seconds=1.0
        )
        
        detector = SectionDetector()
        hierarchy = detector.detect_from_processed_document(processed_doc)
        
        assert hierarchy.total_sections == 0
        assert hierarchy.max_depth == 0
        assert len(hierarchy.root_sections) == 0
        assert hierarchy.confidence_score == 0.0
    
    def test_numbering_pattern_detection(self):
        """Test various numbering pattern detections."""
        detector = SectionDetector()
        
        # Test decimal numbering
        assert detector._has_numbering("1.2.3 Section Title")
        assert detector._has_numbering("1. Introduction")
        
        # Test letter-based
        assert detector._has_numbering("A. Appendix")
        assert detector._has_numbering("B.1 Subsection")
        
        # Test Roman numerals
        assert detector._has_numbering("IV. Results")
        assert detector._has_numbering("II.A Subsection")
        
        # Test non-numbered
        assert not detector._has_numbering("Introduction")
        assert not detector._has_numbering("Related Work")
    
    def test_section_keyword_detection(self):
        """Test section keyword detection."""
        detector = SectionDetector()
        
        # Should detect common section keywords
        assert detector._has_section_keyword("Introduction")
        assert detector._has_section_keyword("Methodology")
        assert detector._has_section_keyword("Related Work")
        assert detector._has_section_keyword("Experiments")
        assert detector._has_section_keyword("Conclusion")
        
        # Should not detect random text
        assert not detector._has_section_keyword("Lorem ipsum dolor")
        assert not detector._has_section_keyword("This is just text")


class TestSectionHierarchy:
    """Tests for SectionHierarchy model and navigation methods."""
    
    def test_hierarchy_navigation(self, sample_processed_document):
        """Test hierarchy navigation methods."""
        detector = SectionDetector()
        hierarchy = detector.detect_from_processed_document(sample_processed_document)
        
        # Test get_section
        intro = hierarchy.find_sections_by_title("Introduction")[0]
        retrieved = hierarchy.get_section(intro.section_id)
        assert retrieved == intro
        
        # Test get_children
        children = hierarchy.get_children(intro.section_id)
        assert len(children) == 2
        assert all(child.level == 2 for child in children)
        
        # Test get_parent
        background = hierarchy.find_sections_by_title("Background")[0]
        parent = hierarchy.get_parent(background.section_id)
        assert parent == intro
    
    def test_section_path(self, sample_processed_document):
        """Test section path retrieval."""
        detector = SectionDetector()
        hierarchy = detector.detect_from_processed_document(sample_processed_document)
        
        details = hierarchy.find_sections_by_title("Details")[0]
        path = hierarchy.get_section_path(details.section_id)
        
        # Path should include Details -> Approach (its parent, level 2)
        # Note: "Details" is 2.1.1, so its ancestors are "Approach" (2.1) and "Methodology" (2)
        # The fixture shows: Details is level 3, child of Approach (level 2), which is child of Methodology (level 1)
        assert len(path) >= 2  # At least Details and its parent
        assert path[0].title == "Details"  # Current section is first
    
    def test_descendants_retrieval(self, sample_processed_document):
        """Test descendants retrieval."""
        detector = SectionDetector()
        hierarchy = detector.detect_from_processed_document(sample_processed_document)
        
        intro = hierarchy.find_sections_by_title("Introduction")[0]
        descendants = hierarchy.get_descendants(intro.section_id)
        
        # Introduction should have 2 descendants (Background, Motivation)
        assert len(descendants) == 2
    
    def test_find_sections_by_title(self, sample_processed_document):
        """Test title-based section search."""
        detector = SectionDetector()
        hierarchy = detector.detect_from_processed_document(sample_processed_document)
        
        # Exact match
        results = hierarchy.find_sections_by_title("Introduction")
        assert len(results) == 1
        assert results[0].title == "Introduction"
        
        # Partial match
        results = hierarchy.find_sections_by_title("Method")
        assert len(results) >= 1
        
        # Case insensitive
        results = hierarchy.find_sections_by_title("introduction", case_sensitive=False)
        assert len(results) == 1
    
    def test_get_sections_by_level(self, sample_processed_document):
        """Test level-based section retrieval."""
        detector = SectionDetector()
        hierarchy = detector.detect_from_processed_document(sample_processed_document)
        
        # Get all level-1 sections
        level1 = hierarchy.get_sections_by_level(1)
        assert len(level1) == 4
        
        # Get all level-2 sections
        level2 = hierarchy.get_sections_by_level(2)
        assert len(level2) == 3
        
        # Get all level-3 sections
        level3 = hierarchy.get_sections_by_level(3)
        assert len(level3) == 1
    
    def test_serialization(self, sample_processed_document):
        """Test hierarchy serialization and deserialization."""
        detector = SectionDetector()
        hierarchy = detector.detect_from_processed_document(sample_processed_document)
        
        # Serialize to dict
        hierarchy_dict = hierarchy.to_dict()
        assert isinstance(hierarchy_dict, dict)
        assert "sections" in hierarchy_dict
        assert "document_id" in hierarchy_dict
        
        # Deserialize back
        restored = SectionHierarchy.from_dict(hierarchy_dict)
        assert restored.document_id == hierarchy.document_id
        assert restored.total_sections == hierarchy.total_sections
        assert len(restored.sections) == len(hierarchy.sections)


class TestSectionHierarchyPipeline:
    """Tests for SectionHierarchyPipeline."""
    
    def test_pipeline_initialization(self):
        """Test pipeline initialization."""
        pipeline = SectionHierarchyPipeline()
        assert pipeline.detector is not None
    
    def test_process_from_processed_document(self, sample_processed_document):
        """Test pipeline processing from ProcessedDocument."""
        pipeline = SectionHierarchyPipeline()
        result = pipeline.process_from_processed_document(sample_processed_document)
        
        assert result.hierarchy is not None
        assert result.processing_time_seconds >= 0
        assert isinstance(result.warnings, list)
    
    def test_process_from_validated_document(self, sample_validated_document):
        """Test pipeline processing from ValidatedDocument."""
        pipeline = SectionHierarchyPipeline()
        result = pipeline.process_from_validated_document(sample_validated_document)
        
        assert result.hierarchy is not None
        assert result.processing_time_seconds >= 0
        assert isinstance(result.warnings, list)
    
    def test_warnings_generation(self):
        """Test that warnings are generated for low-quality results."""
        metadata = ExtractedMetadata(
            title="Test Paper",
            abstract="Abstract",
            sections=[
                SectionInfo(original_name="Introduction", level=1, page_start=1)
            ]  # Only 1 section - should trigger warning
        )
        
        processed_doc = ProcessedDocument(
            document_id=uuid4(),
            metadata=metadata,
            processing_time_seconds=1.0
        )
        
        pipeline = SectionHierarchyPipeline()
        result = pipeline.process_from_processed_document(processed_doc)
        
        # Should have warning about low section count
        assert len(result.warnings) > 0
        assert any("sections detected" in w.lower() for w in result.warnings)
    
    def test_save_and_load_hierarchy(self, sample_processed_document, tmp_path):
        """Test saving and loading hierarchy to/from JSON."""
        pipeline = SectionHierarchyPipeline()
        result = pipeline.process_from_processed_document(sample_processed_document)
        
        # Save to file
        output_file = tmp_path / "hierarchy.json"
        pipeline.save_hierarchy(result.hierarchy, output_file)
        
        assert output_file.exists()
        
        # Load back
        loaded = pipeline.load_hierarchy(output_file)
        
        assert loaded.document_id == result.hierarchy.document_id
        assert loaded.total_sections == result.hierarchy.total_sections
        assert len(loaded.sections) == len(result.hierarchy.sections)


class TestSectionNode:
    """Tests for SectionNode model."""
    
    def test_section_node_creation(self):
        """Test SectionNode creation."""
        node = SectionNode(
            section_id="test_1",
            title="Introduction",
            level=1,
            numbering="1.",
            page_start=1,
            reading_order=0
        )
        
        assert node.section_id == "test_1"
        assert node.title == "Introduction"
        assert node.level == 1
        assert node.depth == 1  # Alias for level
    
    def test_full_path_property(self):
        """Test full_path property."""
        node = SectionNode(
            section_id="test_1",
            title="Introduction",
            level=1,
            numbering="1.",
            page_start=1,
            reading_order=0
        )
        
        assert "1." in node.full_path
        assert "Introduction" in node.full_path
    
    def test_full_path_without_numbering(self):
        """Test full_path when no numbering."""
        node = SectionNode(
            section_id="test_1",
            title="Introduction",
            level=1,
            page_start=1,
            reading_order=0
        )
        
        assert node.full_path == "Introduction"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
