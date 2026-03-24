"""
Metadata extractor using Docling + Groq approach.

Extracts title, abstract, and section structure from research papers
using a combination of Docling layout analysis and Groq LLM classification.
"""

import os
import json
import re
import html
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
from groq import Groq

from backend.extraction.models.document import ValidatedDocument
from backend.extraction.models.metadata import (
    ExtractedMetadata,
    SectionInfo,
    SectionStats,
    GlobalStats,
    PaperInference
)


logger = logging.getLogger(__name__)

_MIN_FREE_GPU_GB = 1.5  # minimum free VRAM required to use GPU


def _get_accelerator_options(num_threads: int = 4) -> AcceleratorOptions:
    """Return GPU AcceleratorOptions if enough VRAM is free, else fall back to CPU."""
    try:
        import torch
        if torch.cuda.is_available():
            free_bytes, _ = torch.cuda.mem_get_info()
            free_gb = free_bytes / (1024 ** 3)
            if free_gb >= _MIN_FREE_GPU_GB:
                logger.info(f"Using GPU for docling (free VRAM: {free_gb:.2f} GB)")
                return AcceleratorOptions(num_threads=num_threads, device=AcceleratorDevice.CUDA)
            logger.warning(
                f"GPU free VRAM too low ({free_gb:.2f} GB < {_MIN_FREE_GPU_GB} GB), falling back to CPU"
            )
    except Exception:
        pass
    logger.info("Using CPU for docling")
    return AcceleratorOptions(num_threads=num_threads, device=AcceleratorDevice.CPU)



class MetadataExtractor:
    """
    Extracts metadata using Docling structure analysis + Groq LLM classification.
    
    This approach is more accurate than pure heuristics by:
    1. Using Docling to extract document structure (headings, elements)
    2. Using Groq LLM to classify and organize the extracted structure
    3. Fallback to pattern matching for abstract extraction
    """
    
    HEADING_CLASSIFICATION_PROMPT = """You are an expert research paper analyst. Given a list of headings and opening paragraphs extracted from a research paper, classify and extract the following:

1. **title**: Identify which heading is the main paper title (usually the first major heading)
2. **abstract**: Extract the paper abstract from headings OR opening paragraphs
3. **keywords**: Extract 5-12 concise research keywords/phrases from title + abstract
4. **sections**: Identify the main content sections ONLY

**EXCLUDE these sections:**
- References / Bibliography
- Acknowledgements / Acknowledgments
- Appendix / Appendices
- Supplementary Material
- Funding / Funding Information
- Author Contributions
- Competing Interests / Conflict of Interest
- Data Availability
- Code Availability
- Ethical Statement / Ethics Statement

**INCLUDE main content sections like:**
- Introduction
- Related Work / Background / Literature Review
- Methodology / Methods / Approach
- Experiments / Evaluation / Results
- Discussion / Analysis
- Conclusion / Future Work
- Any numbered sections that appear to contain main content

## Headings Extracted from Paper

{headings_json}

## Opening Context (first few paragraphs)

{context_excerpt}

## Instructions

- Identify the paper title (usually first heading, might be unnumbered)
- Title must be the actual paper title, not a document type label (e.g., "Invited Review", "Review Article"), author names, affiliations, or venue text
- Extract a non-empty abstract. Prefer the explicit "Abstract" section; if missing, infer from opening paragraphs before Introduction.
- Abstract should be a concise summary paragraph only; exclude title lines, author/affiliation lines, and keyword lists
- Extract 5-12 specific keywords (avoid generic words like "paper", "method", "results")
- List main content sections with their level (1-5) and page_start
- Assign appropriate section levels based on heading hierarchy
- Be precise and only include sections that contain main paper content

Respond in JSON format:
{{
    "title": "paper title here",
    "abstract": "non-empty abstract text",
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "sections": [
        {{"original_name": "Introduction", "level": 1, "page_start": 1}},
        {{"original_name": "Methodology", "level": 1, "page_start": 3}}
    ]
}}
"""
    
    INFERENCE_PROMPT = """You are an expert research paper analyst. Based on the paper title, abstract, and sections, infer the following properties:

1. **paper_type**: Classify as one of: Survey, System, Theoretical, Empirical, Experimental, Position Paper, Tool Paper, Case Study, or Other
2. **difficulty**: Rate reading difficulty as: easy, medium, or hard
3. **math_heavy**: Determine if the paper contains heavy mathematical content (true/false)

**Title:** {title}

**Abstract:** {abstract}

**Sections:** {sections}

Respond in JSON format:
{{
    "paper_type": "one of the types above",
    "difficulty": "easy, medium, or hard",
    "math_heavy": true or false
}}
"""

    REFERENCE_SECTION_KEYWORDS = (
        "reference",
        "references",
        "bibliography",
        "works cited",
    )
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama-3.3-70b-versatile",
    ):
        """
        Initialize metadata extractor.
        
        Args:
            api_key: Groq API key (defaults to GROQ_API_KEY env var)
            model: Groq model name
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.warning("Groq API key not found. LLM features will be disabled.")
            self.client = None
        else:
            self.client = Groq(api_key=self.api_key)
        
        self.model = model
        _pipeline_options = PdfPipelineOptions(
            do_ocr=False,
            generate_picture_images=True,
            accelerator_options=_get_accelerator_options(),
        )
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=_pipeline_options
                )
            }
        )
    
    def extract(self, document: ValidatedDocument) -> ExtractedMetadata:
        """
        Extract metadata from a validated document.
        
        Args:
            document: ValidatedDocument from ingestion pipeline
            
        Returns:
            ExtractedMetadata with extracted fields
        """
        logger.info(f"Extracting metadata from document {document.document_id}")
        
        # Extract structured data using Docling
        image_output_dir = Path(os.getenv("EXTRACTED_IMAGE_DIR", "output/images")) / document.pdf_path.stem
        structured_data = self._extract_structured_data(document.pdf_path, image_output_dir=image_output_dir)
        
        markdown = structured_data["markdown"]
        headings = structured_data["headings"]
        element_counts = structured_data["element_counts"]
        elements = structured_data["elements"]
        
        logger.info(f"Extracted {len(headings)} headings from document")
        
        # Classify headings using Groq LLM
        if self.client and headings:
            classification = self._classify_headings_llm(headings, markdown)
        else:
            classification = self._classify_headings_fallback(headings, markdown)

        if not self._is_valid_abstract(classification.get("abstract", "")):
            raise ValueError("Abstract extraction failed: abstract is required.")

        # Docling often emits bibliography entries as list_item blocks.
        # Normalize these into explicit reference blocks and ensure a dedicated
        # top-level "Reference" section is always present.
        self._normalize_reference_blocks(elements)
        classification["sections"] = self._ensure_reference_section(
            classification.get("sections", []),
            elements,
            document.page_count,
        )
        
        logger.info(f"Classified: Title='{classification['title'][:50]}...', {len(classification['sections'])} sections")
        
        # Build global stats
        global_stats = GlobalStats(
            total_formulas=element_counts.get("formulas", 0),
            total_tables=element_counts.get("tables", 0),
            total_figures=element_counts.get("pictures", 0),
            total_text_blocks=element_counts.get("text_blocks", 0),
            total_pages=document.page_count,
            total_sections=len(classification['sections'])
        )
        
        # Calculate section-wise statistics
        sections_with_stats = self._add_section_statistics(
            classification['sections'],
            elements
        )
        
        # Infer paper properties (uses formula counts and other stats)
        if self.client:
            inference = self._infer_paper_properties(
                classification['title'],
                classification['abstract'],
                classification['sections'],
                global_stats
            )
        else:
            # Fallbacsections_with_statsence without LLM
            inference = self._infer_paper_properties_heuristic(global_stats)
        
        # Build metadata
        metadata = ExtractedMetadata(
            title=classification['title'],
            abstract=classification['abstract'],
            keywords=classification.get('keywords', []),
            sections=classification['sections'],
            global_stats=global_stats,
            inference=inference,
            extracted_elements=elements,
            extraction_method="docling+groq" if self.client else "docling",
            fallback_used=not bool(self.client),
            missing_fields=self._identify_missing_fields(classification)
        )
        
        metadata.confidence_score = metadata.get_field_coverage()
        
        logger.info(
            f"Extracted metadata with {len(metadata.missing_fields)} missing fields. "
            f"Confidence: {metadata.confidence_score:.2f}"
        )
        
        return metadata
    
    def _extract_structured_data(
        self,
        pdf_path: Path,
        image_output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Extract structured document data using Docling.
        
        Returns:
            Dict with markdown, headings, element counts, and detailed elements
        """
        result = self.converter.convert(str(pdf_path))
        doc = result.document
        
        # Extract markdown
        markdown = doc.export_to_markdown()
        
        # Extract all headings with levels and page info
        headings = []
        for item, level in doc.iterate_items():
            if item.label == "section_header":
                page_no = 1
                if item.prov:
                    page_no = getattr(item.prov[0], "page_no", 0) + 1  # 1-indexed
                
                headings.append({
                    "text": item.text if hasattr(item, 'text') else "",
                    "level": level,
                    "page": page_no
                })
        
        # Extract detailed elements with IDs and page numbers
        elements = {
            "formulas": [],
            "tables": [],
            "figures": [],
            "text_blocks": []
        }
        
        element_counts = {
            "formulas": 0,
            "tables": 0,
            "pictures": 0,
            "text_blocks": 0
        }

        current_section_title: Optional[str] = None
        
        for item, level in doc.iterate_items():
            label = str(getattr(item, "label", "")).lower()
            item_text = self._item_to_text(item, doc)

            page_no = 1
            if item.prov:
                page_no = getattr(item.prov[0], "page_no", 0) + 1

            if label in ["section_header", "title"]:
                heading_text = item_text.strip()
                if heading_text:
                    current_section_title = heading_text
                continue
            
            # Generate element ID (using hash of content or position)
            stable_repr = f"{label}|{item_text}|{page_no}|{level}"
            element_id = hashlib.md5(stable_repr.encode()).hexdigest()
            
            if label in ["formula", "equation"]:
                element_counts["formulas"] += 1
                elements["formulas"].append({
                    "id": element_id,
                    "page": page_no,
                    "label": label,
                    "text": self._item_to_text(item, doc),
                })
            elif label == "table":
                table_text = self._item_to_text(item, doc)
                element_counts["tables"] += 1
                elements["tables"].append({
                    "id": element_id,
                    "page": page_no,
                    "label": label,
                    "text": table_text,
                    "markdown": table_text,
                })
            elif label == "picture":
                element_counts["pictures"] += 1
                image_path = self._save_picture_asset(
                    item=item,
                    doc=doc,
                    output_dir=image_output_dir,
                    element_id=element_id,
                    page_no=page_no,
                )
                elements["figures"].append({
                    "id": element_id,
                    "page": page_no,
                    "label": label,
                    "caption": self._item_to_text(item, doc),
                    "image_path": str(image_path) if image_path else None,
                })
            elif label in ["text", "paragraph", "list_item", "list_items", "reference", "bibliography"]:
                text = item_text
                if not text.strip():
                    continue
                element_counts["text_blocks"] += 1
                elements["text_blocks"].append({
                    "id": element_id,
                    "page": page_no,
                    "label": label,
                    "text": text,
                    "section_title": current_section_title,
                    "section": current_section_title,
                })
        
        return {
            "markdown": markdown,
            "headings": headings,
            "element_counts": element_counts,
            "elements": elements
        }

    def _item_to_text(self, item: Any, doc: Any) -> str:
        """Extract best-effort text/markdown representation for an item."""
        if hasattr(item, "text") and item.text:
            return str(item.text)

        if hasattr(item, "export_to_markdown"):
            try:
                return item.export_to_markdown(doc)
            except Exception:
                return ""

        return ""

    def _save_picture_asset(
        self,
        *,
        item: Any,
        doc: Any,
        output_dir: Optional[Path],
        element_id: str,
        page_no: int,
    ) -> Optional[Path]:
        """Persist figure image to PNG when available from Docling."""
        if output_dir is None:
            return None

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return None

    @classmethod
    def _is_reference_section_name(cls, section_name: str) -> bool:
        section_norm = str(section_name or "").strip().lower()
        if not section_norm:
            return False
        return any(keyword in section_norm for keyword in cls.REFERENCE_SECTION_KEYWORDS)

    @classmethod
    def _is_reference_block(cls, block: Dict[str, Any]) -> bool:
        label = str(block.get("label") or "").strip().lower()
        section_name = str(block.get("section_title") or block.get("section") or "").strip().lower()
        text_value = str(block.get("text") or "").strip()

        if label in {"reference", "bibliography"}:
            return True
        if cls._is_reference_section_name(section_name):
            return True
        if text_value and re.match(r"^\s*(references|bibliography|works cited)\b", text_value, flags=re.I):
            return True
        return False

    def _normalize_reference_blocks(self, elements: Dict[str, List[Dict[str, Any]]]) -> None:
        text_blocks = elements.get("text_blocks") or []
        references: List[Dict[str, Any]] = []

        for block in text_blocks:
            if not isinstance(block, dict):
                continue
            if not self._is_reference_block(block):
                continue

            original_label = block.get("label")
            if original_label and original_label != "reference":
                block["docling_label"] = original_label

            block["label"] = "reference"
            block["section_title"] = "Reference"
            block["section"] = "Reference"

            references.append(
                {
                    "id": block.get("id"),
                    "page": block.get("page"),
                    "text": block.get("text"),
                    "label": "reference",
                    "section_id": block.get("section_id"),
                    "section_title": "Reference",
                }
            )

        elements["references"] = references

    def _ensure_reference_section(
        self,
        sections: List[SectionInfo],
        elements: Dict[str, List[Dict[str, Any]]],
        total_pages: int,
    ) -> List[SectionInfo]:
        normalized_sections = list(sections or [])
        reference_page = self._resolve_reference_page(elements, total_pages)

        found_reference_section = False
        for section in normalized_sections:
            if self._is_reference_section_name(section.original_name):
                section.original_name = "Reference"
                if section.level < 1:
                    section.level = 1
                if section.page_start < 1:
                    section.page_start = reference_page
                found_reference_section = True

        if not found_reference_section:
            normalized_sections.append(
                SectionInfo(
                    original_name="Reference",
                    level=1,
                    page_start=reference_page,
                )
            )

        return normalized_sections

    def _resolve_reference_page(
        self,
        elements: Dict[str, List[Dict[str, Any]]],
        total_pages: int,
    ) -> int:
        reference_candidates = elements.get("references") or []
        if not reference_candidates:
            reference_candidates = elements.get("text_blocks") or []

        pages: List[int] = []
        for item in reference_candidates:
            if not isinstance(item, dict):
                continue
            if reference_candidates is elements.get("text_blocks") and not self._is_reference_block(item):
                continue
            page = item.get("page")
            if isinstance(page, int) and page >= 1:
                pages.append(page)

        if pages:
            return min(pages)

        return max(int(total_pages or 1), 1)

        image_obj = None

        # Try common Docling image access patterns (method first, then attributes).
        try:
            if hasattr(item, "get_image"):
                image_obj = item.get_image(doc)
        except Exception:
            image_obj = None

        if image_obj is None and hasattr(item, "image"):
            image_obj = getattr(item, "image")

        if image_obj is not None and hasattr(image_obj, "pil_image"):
            image_obj = image_obj.pil_image

        if image_obj is None:
            return None

        try:
            target_path = output_dir / f"page_{page_no:03d}_{element_id}.png"
            image_obj.save(target_path, format="PNG")
            return target_path
        except Exception:
            return None
    
    def _classify_headings_llm(
        self,
        headings: List[Dict[str, Any]],
        markdown: str
    ) -> Dict[str, Any]:
        """
        Classify headings using Groq LLM.
        
        Args:
            headings: List of heading dicts from Docling
            markdown: Full markdown text
            
        Returns:
            Dict with title, abstract, and sections
        """
        headings_json = json.dumps(headings, indent=2)
        context_excerpt = self._build_opening_context(markdown)

        prompt = self.HEADING_CLASSIFICATION_PROMPT.format(
            headings_json=headings_json,
            context_excerpt=context_excerpt,
        )
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise metadata extraction assistant. Return valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=2048,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Convert sections to SectionInfo objects
            sections = [
                SectionInfo(**section)
                for section in result.get("sections", [])
            ]
            
            # If abstract is empty or too short, try extracting from markdown
            abstract = result.get("abstract", "")
            if not abstract or len(abstract.strip()) < 50:
                fallback_abstract = self._extract_abstract_from_markdown(markdown)
                if fallback_abstract:
                    abstract = fallback_abstract

            title = str(result.get("title", "") or "").strip()
            abstract = str(abstract or "").strip()
            keywords = self._normalize_keywords(result.get("keywords", []))

            title, abstract = self._recover_title_abstract_from_prefix(
                title=title,
                abstract=abstract,
                markdown=markdown,
                headings=headings,
            )
            title = self._clean_title_text(title)
            if not self._is_valid_title(title):
                title = self._extract_title_from_headings(headings) or title
            title, abstract = self._postprocess_title_abstract(title=title, abstract=abstract)
            if not keywords:
                keywords = self._extract_keywords(title=title, abstract=abstract, markdown=markdown)
            
            return {
                "title": title,
                "abstract": abstract,
                "keywords": keywords,
                "sections": sections
            }
            
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return self._classify_headings_fallback(headings, markdown)
    
    def _classify_headings_fallback(
        self,
        headings: List[Dict[str, Any]],
        markdown: str
    ) -> Dict[str, Any]:
        """
        Fallback classification without LLM using pattern matching.
        
        Args:
            headings: List of heading dicts
            markdown: Full markdown text
            
        Returns:
            Dict with title, abstract, and sections
        """
        # Extract title (first heading)
        title = headings[0]["text"] if headings else "Unknown Title"
        
        # Extract abstract from markdown
        abstract = self._extract_abstract_from_markdown(markdown)
        
        # Filter sections
        exclude_keywords = [
            'reference', 'bibliography', 'acknowledgement', 'acknowledgment',
            'appendix', 'supplementary', 'funding', 'author contribution',
            'competing interest', 'conflict of interest', 'data availability',
            'code availability', 'ethical', 'ethics'
        ]
        
        sections = []
        for heading in headings[1:]:  # Skip first (title)
            text_lower = heading["text"].lower()
            
            # Check if should exclude
            if any(keyword in text_lower for keyword in exclude_keywords):
                continue
            
            sections.append(SectionInfo(
                original_name=heading["text"],
                level=heading["level"],
                page_start=heading["page"]
            ))
        
        title, abstract = self._recover_title_abstract_from_prefix(
            title=str(title or "").strip(),
            abstract=str(abstract or "").strip(),
            markdown=markdown,
            headings=headings,
        )

        title = self._clean_title_text(title)
        if not self._is_valid_title(title):
            title = self._extract_title_from_headings(headings) or title
        title, abstract = self._postprocess_title_abstract(title=title, abstract=abstract)

        keywords = self._extract_keywords(title=title, abstract=abstract, markdown=markdown)

        return {
            "title": title,
            "abstract": abstract,
            "keywords": keywords,
            "sections": sections
        }

    def _recover_title_abstract_from_prefix(
        self,
        title: str,
        abstract: str,
        markdown: str,
        headings: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[str, str]:
        """
        Recover missing title/abstract from opening markdown context via Groq.

        This is only used when heuristic/primary extraction leaves title or abstract empty.
        """
        title = self._clean_title_text(title)
        missing_title = not self._is_valid_title(title)
        missing_abstract = not self._is_valid_abstract(abstract)

        # Always try deterministic abstract recovery first so rate limits do not
        # block extraction when an abstract exists in raw text.
        if missing_abstract:
            heuristic_abstract = self._extract_abstract_from_markdown(markdown)
            if self._is_valid_abstract(heuristic_abstract):
                abstract = heuristic_abstract
                missing_abstract = False

        if not (missing_title or missing_abstract):
            return title, abstract

        if not self.client:
            return title, abstract

        context_excerpt = self._build_opening_context(markdown, char_limit=8000, max_paragraphs=14)
        if not context_excerpt:
            return title, abstract

        prompt = (
            "Extract the paper title and abstract from the opening paper content below. "
            "Prioritize the explicit abstract section; otherwise infer the abstract from the opening summary paragraphs before Introduction. "
            "Do not return document labels (like 'Invited Review'), author names, affiliations, venue headers, or keyword lists as title/abstract content. "
            "Return valid JSON only.\n\n"
            f"Opening content:\n{context_excerpt}\n\n"
            "Return JSON with keys: title, abstract."
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise metadata extraction assistant. Return valid JSON only.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0,
                max_tokens=700,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)

            if missing_title:
                candidate_title = self._clean_title_text(str(result.get("title", "") or ""))
                if self._is_valid_title(candidate_title):
                    title = candidate_title

            if missing_abstract:
                candidate_abstract = str(result.get("abstract", "") or "").strip()
                candidate_abstract = self._clean_abstract_text(candidate_abstract)
                if self._is_valid_abstract(candidate_abstract):
                    abstract = candidate_abstract

        except Exception as exc:
            logger.warning("Title/abstract prefix recovery failed: %s", exc)

        # If LLM recovery is unavailable or rate-limited, retry deterministic
        # extraction once more before giving up.
        if not self._is_valid_abstract(abstract):
            heuristic_abstract = self._extract_abstract_from_markdown(markdown)
            if self._is_valid_abstract(heuristic_abstract):
                abstract = heuristic_abstract

        if not self._is_valid_title(title):
            heading_title = self._extract_title_from_headings(headings or [])
            if self._is_valid_title(heading_title):
                title = heading_title

        return self._clean_title_text(title), self._clean_abstract_text(abstract)

    def _postprocess_title_abstract(self, title: str, abstract: str) -> tuple[str, str]:
        """Final cleanup for title/abstract pair to remove common front-matter noise."""
        clean_title = self._clean_title_text(title)
        candidate = self._clean_abstract_text(abstract)

        # If abstract starts by repeating title, trim that duplicate prefix.
        if clean_title and candidate.lower().startswith(clean_title.lower()):
            candidate = candidate[len(clean_title):].lstrip(" .,:;-")

        # Remove author/affiliation preamble when a clear abstract opener appears later.
        start_match = re.search(
            r"(?i)\b(recently|in this paper|in this survey|this paper|we\s+(?:propose|present|introduce|show|study|investigate|develop)|our\s+paper)\b",
            candidate,
        )
        if start_match and start_match.start() > 20:
            prefix = candidate[:start_match.start()]
            if re.search(r"(?i)\b(university|department|school|laboratory|institute|@)\b", prefix) or prefix.count(",") >= 3:
                candidate = candidate[start_match.start():].lstrip(" .,:;-")

        return clean_title, self._clean_abstract_text(candidate)

    def _build_opening_context(
        self,
        markdown: str,
        char_limit: int = 6000,
        max_paragraphs: int = 12,
    ) -> str:
        """Build opening-context text using first few non-empty paragraphs."""
        text = str(markdown or "")
        if not text.strip():
            return ""

        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        selected: List[str] = []
        for para in paragraphs:
            cleaned = self._clean_noise_text(para)
            if not cleaned:
                continue
            selected.append(cleaned)
            if len(selected) >= max_paragraphs:
                break

        excerpt = "\n\n".join(selected).strip()
        return excerpt[:char_limit]

    @staticmethod
    def _clean_noise_text(text: str) -> str:
        """Remove noisy OCR/markdown artifacts that harm metadata extraction."""
        cleaned = str(text or "")
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", cleaned)
        cleaned = re.sub(r"GLYPH<\d+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _clean_title_text(text: str) -> str:
        """Normalize title text and strip common non-title labels."""
        candidate = MetadataExtractor._clean_noise_text(text)
        candidate = re.sub(r"(?m)^\s*#{1,6}\s*", "", candidate)
        candidate = re.sub(
            r"(?i)^\s*(invited\s+review|review\s+article|tutorial\s+paper|editorial)\s*[\.:;\-|]+\s*",
            "",
            candidate,
        )
        candidate = candidate.strip(" \t\n\r'\"`.,;:-")
        return candidate

    @staticmethod
    def _is_valid_title(title: str) -> bool:
        """Return True when title appears to be a real paper title."""
        candidate = MetadataExtractor._clean_title_text(title)
        if not candidate:
            return False

        lower = candidate.lower()
        if lower in {"unknown title", "unknown", "n/a"}:
            return False
        if re.fullmatch(r"(?i)(invited\s+review|review\s+article|editorial)", candidate):
            return False

        words = candidate.split()
        if len(words) < 3 or len(words) > 35:
            return False
        if re.search(r"(?i)\b(university|department|school|laboratory|email|@)\b", candidate):
            return False

        return True

    def _extract_title_from_headings(self, headings: List[Dict[str, Any]]) -> str:
        """Pick the most likely paper title from extracted headings."""
        best_title = ""
        best_score = -10

        for heading in headings or []:
            text = self._clean_title_text(str(heading.get("text", "") or ""))
            if not text:
                continue

            text_lower = text.lower()
            if re.match(r"^\d+(\.\d+)*\s+", text):
                continue
            if re.search(r"\b(abstract|introduction|reference|references|bibliography|appendix|acknowledg)\b", text_lower):
                continue

            score = 0
            page = int(heading.get("page", 99) or 99)
            if page <= 2:
                score += 3
            if self._is_valid_title(text):
                score += 3
            if 20 <= len(text) <= 220:
                score += 1
            if ":" in text:
                score += 1

            if score > best_score:
                best_score = score
                best_title = text

        return best_title

    @staticmethod
    def _normalize_keywords(raw_keywords: Any) -> List[str]:
        """Normalize candidate keywords to a clean, unique list."""
        if not raw_keywords:
            return []

        if isinstance(raw_keywords, str):
            candidates = re.split(r",|;|\n", raw_keywords)
        elif isinstance(raw_keywords, list):
            candidates = raw_keywords
        else:
            return []

        normalized: List[str] = []
        seen = set()
        for item in candidates:
            kw = re.sub(r"\s+", " ", str(item or "")).strip(" .,:;\t\n\r").lower()
            if len(kw) < 3 or len(kw) > 64:
                continue
            if kw in seen:
                continue
            seen.add(kw)
            normalized.append(kw)

        return normalized[:15]

    @staticmethod
    def _is_valid_abstract(abstract: str) -> bool:
        """Return True when abstract has meaningful length/content."""
        cleaned = re.sub(r"\s+", " ", str(abstract or "")).strip()
        word_count = len(cleaned.split()) if cleaned else 0
        return len(cleaned) >= 50 or word_count >= 12

    @staticmethod
    def _clean_abstract_text(text: str) -> str:
        """Normalize abstract text and trim common trailing noise."""
        candidate = MetadataExtractor._clean_noise_text(text)
        candidate = re.sub(r"\r\n?", "\n", candidate)
        # Remove markdown heading markers that can leak into extracted text.
        candidate = re.sub(r"(?m)^\s*#{1,6}\s*", "", candidate)
        # Remove leading labels and non-abstract boilerplate that can leak into candidate.
        candidate = re.sub(r"(?i)^\s*abstract\s*[:\-]?\s*", "", candidate)
        candidate = re.sub(r"(?i)^\s*invited\s+review\s*[\.:;\-|]*\s*", "", candidate)
        # Trim explicit keyword/index-terms tails often present after abstracts.
        candidate = re.split(r"(?i)\b(keywords?|index\s+terms?)\b\s*[:\-]?", candidate, maxsplit=1)[0]
        # Trim trailing comma-separated keyword-like tails when no explicit keyword label exists.
        candidate = re.sub(
            r"(?i)([\.!?])\s*[A-Z][A-Za-z\- ]+(?:\s*,\s*[A-Z][A-Za-z\- ]+){4,}\s*$",
            r"\1",
            candidate,
        )
        candidate = re.sub(r"\s+", " ", candidate).strip(" .;:-\n\t")
        return candidate

    def _extract_keywords(self, title: str, abstract: str, markdown: str) -> List[str]:
        """Extract keywords via LLM when available, else use heuristic fallback."""
        if self.client:
            context_excerpt = self._build_opening_context(markdown, char_limit=2500, max_paragraphs=6)
            prompt = (
                "Extract 5-12 high-signal research keywords from the paper content. "
                "Prefer terms from title and abstract, include technical phrases, and avoid generic words. "
                "Return JSON with a single key 'keywords' as an array of strings.\n\n"
                f"Title:\n{title}\n\n"
                f"Abstract:\n{abstract}\n\n"
                f"Opening paragraphs:\n{context_excerpt}"
            )

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a precise metadata extraction assistant. Return valid JSON only.",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    temperature=0,
                    max_tokens=256,
                    response_format={"type": "json_object"},
                )
                result = json.loads(response.choices[0].message.content)
                normalized = self._normalize_keywords(result.get("keywords", []))
                if normalized:
                    return normalized
            except Exception as exc:
                logger.warning("Keyword extraction failed: %s", exc)

        # Heuristic keyword fallback from title + abstract
        text = f"{title} {abstract}".lower()
        tokens = re.findall(r"[a-z][a-z0-9\-]{2,}", text)
        stopwords = {
            "the", "and", "for", "with", "from", "this", "that", "are", "was", "were", "into", "using",
            "paper", "study", "result", "results", "method", "methods", "approach", "based", "analysis",
            "model", "models", "data", "new", "novel", "our", "their", "than", "also", "show", "shows",
        }
        freq: Dict[str, int] = {}
        for tok in tokens:
            if tok in stopwords:
                continue
            freq[tok] = freq.get(tok, 0) + 1

        ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [kw for kw, _ in ranked[:10]]
    
    def _extract_abstract_from_markdown(self, markdown: str) -> str:
        """
        Extract abstract from markdown text using pattern matching.
        
        Args:
            markdown: Full markdown text
            
        Returns:
            Abstract text or empty string
        """
        text = str(markdown or "")
        if not text.strip():
            return ""

        normalized = re.sub(r"\r\n?", "\n", text)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)

        # 1) Standard markdown heading form: "## Abstract" + body
        heading_pattern = r"(?is)(?:^|\n)#{1,6}\s*abstract\s*\n(.{60,6000}?)(?=\n#{1,6}\s|\Z)"
        match = re.search(heading_pattern, normalized)
        if match:
            candidate = self._clean_abstract_text(match.group(1))
            if self._is_valid_abstract(candidate):
                return candidate

        # 2) Plain-text / OCR form where Abstract is not a markdown heading.
        # Stop at common boundaries: keywords/index terms/introduction/section 1.
        plain_pattern = (
            r"(?is)\babstract\b\s*[:\-]?\s*(.{60,8000}?)"
            r"(?=\bkeywords?\b|\bindex\s+terms\b|\bintroduction\b|\n\s*1\.?\s+[A-Za-z]|\n\s*#{1,6}\s|\Z)"
        )
        match = re.search(plain_pattern, normalized)
        if match:
            candidate = self._clean_abstract_text(match.group(1))
            if self._is_valid_abstract(candidate):
                return candidate

        # 3) Last fallback: take first substantive paragraphs before Introduction.
        paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
        collected: List[str] = []
        for p in paragraphs[:12]:
            lower = p.lower()
            if "introduction" in lower:
                break
            if re.fullmatch(r"#{1,6}\s*abstract\s*", p, flags=re.IGNORECASE):
                continue
            collected.append(p)
            if len(" ".join(collected)) > 1800:
                break

        if collected:
            candidate = self._clean_abstract_text(" ".join(collected))
            if self._is_valid_abstract(candidate):
                return candidate

        return ""

    def _infer_paper_properties(
        self,
        title: str,
        abstract: str,
        sections: List[SectionInfo],
        global_stats: GlobalStats
    ) -> PaperInference:
        """
        Infer paper properties using Groq LLM with formula counts.
        
        Args:
            title: Paper title
            abstract: Paper abstract
            sections: List of sections
            global_stats: Document statistics including formula count
            
        Returns:
            PaperInference
        """
        sections_str = ", ".join([s.original_name for s in sections[:10]])
        
        # Enhanced prompt with formula count information
        enhanced_prompt = f"""{self.INFERENCE_PROMPT.format(
            title=title,
            abstract=abstract,
            sections=sections_str
        )}

**Additional Context:**
- Total Formulas: {global_stats.total_formulas}
- Formulas per Page: {global_stats.total_formulas / global_stats.total_pages if global_stats.total_pages > 0 else 0:.2f}
- Total Tables: {global_stats.total_tables}
- Total Figures: {global_stats.total_figures}

Use the formula density to help determine if the paper is math_heavy:
- >= 2.0 formulas/page: Definitely math-heavy
- >= 1.0 formulas/page: Likely math-heavy
- >= 10 total formulas: Consider math-heavy
- < 0.5 formulas/page: Probably not math-heavy
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise paper classification assistant. Return valid JSON only. Use the formula counts to accurately determine if a paper is math-heavy."
                    },
                    {
                        "role": "user",
                        "content": enhanced_prompt
                    }
                ],
                temperature=0.1,
                max_tokens=512,
                response_format={"type": "json_object"}
            )
            
            inference_data = json.loads(response.choices[0].message.content)
            
            return PaperInference(
                paper_type=inference_data.get("paper_type", "Unknown"),
                difficulty=inference_data.get("difficulty", "medium"),
                math_heavy=inference_data.get("math_heavy", False)
            )
            
        except Exception as e:
            logger.error(f"Inference failed: {e}")
            return self._infer_paper_properties_heuristic(global_stats)
    
    def _infer_paper_properties_heuristic(
        self,
        global_stats: GlobalStats
    ) -> PaperInference:
        """
        Infer paper properties using heuristics when LLM is unavailable.
        
        Args:
            global_stats: Document statistics
            
        Returns:
            PaperInference
        """
        formulas_per_page = (
            global_stats.total_formulas / global_stats.total_pages 
            if global_stats.total_pages > 0 else 0
        )
        
        # Determine if math-heavy based on formula density
        if formulas_per_page >= 2.0:
            math_heavy = True
            difficulty = "advanced"
            paper_type = "theoretical_research"
        elif formulas_per_page >= 1.0 or global_stats.total_formulas >= 10:
            math_heavy = True
            difficulty = "intermediate"
            paper_type = "research_article"
        elif formulas_per_page >= 0.3 or global_stats.total_formulas >= 5:
            math_heavy = False
            difficulty = "intermediate"
            paper_type = "research_article"
        else:
            math_heavy = False
            # Use section count and page count for difficulty
            if global_stats.total_pages > 20 or global_stats.total_sections > 10:
                difficulty = "intermediate"
            else:
                difficulty = "beginner"
            paper_type = "research_article"
        
        logger.info(
            f"Heuristic inference: formulas={global_stats.total_formulas}, "
            f"density={formulas_per_page:.2f}, math_heavy={math_heavy}, "
            f"difficulty={difficulty}"
        )
        
        return PaperInference(
            paper_type=paper_type,
            difficulty=difficulty,
            math_heavy=math_heavy
        )
    
    def _identify_missing_fields(self, classification: Dict[str, Any]) -> List[str]:
        """Identify which core metadata fields are missing."""
        missing = []
        
        if not classification.get('title'):
            missing.append('title')
        if not self._is_valid_abstract(classification.get('abstract', '')):
            missing.append('abstract')
        if not classification.get('keywords'):
            missing.append('keywords')
        if not classification.get('sections'):
            missing.append('sections')
        
        return missing
    
    def _add_section_statistics(
        self,
        sections: List[SectionInfo],
        elements: Dict[str, List[Dict[str, Any]]]
    ) -> List[SectionInfo]:
        """
        Add section-wise statistics to each section.
        
        Args:
            sections: List of sections from classification
            elements: Dictionary of elements (formulas, tables, figures, text_blocks) with page numbers
            
        Returns:
            List of SectionInfo with stats populated
        """
        # Build hierarchical structure first
        hierarchical_sections = self._build_section_hierarchy(sections)
        
        # Add statistics to hierarchical sections
        self._populate_section_stats(hierarchical_sections, elements)
        
        return hierarchical_sections
    
    def _build_section_hierarchy(self, sections: List[SectionInfo]) -> List[SectionInfo]:
        """
        Build hierarchical section structure from flat list.
        
        Args:
            sections: Flat list of sections
            
        Returns:
            Hierarchical list of sections with nested subsections
        """
        if not sections:
            return []
        
        # Stack to track parent sections at each level
        stack: List[SectionInfo] = []
        root_sections: List[SectionInfo] = []
        
        for section in sections:
            # Pop stack until we find the appropriate parent
            while stack and stack[-1].level >= section.level:
                stack.pop()
            
            # If stack is empty or parent is at a lower level, it's a root or child of current parent
            if not stack:
                # Root level section
                root_sections.append(section)
                stack.append(section)
            else:
                # Child section
                parent = stack[-1]
                if parent.sections is None:
                    parent.sections = []
                parent.sections.append(section)
                stack.append(section)
        
        return root_sections
    
    def _populate_section_stats(
        self,
        sections: List[SectionInfo],
        elements: Dict[str, List[Dict[str, Any]]],
        start_page: Optional[int] = None,
        end_page: Optional[int] = None
    ) -> None:
        """
        Recursively populate statistics for sections and their subsections.
        
        Args:
            sections: List of sections (may contain nested sections)
            elements: Dictionary of elements with page numbers
            start_page: Override start page for calculation
            end_page: Override end page for calculation
        """
        for i, section in enumerate(sections):
            # Determine page range for this section
            section_start = start_page if start_page else section.page_start
            
            # End page is either the next section's start page - 1 or the document end
            if i + 1 < len(sections):
                section_end = sections[i + 1].page_start - 1
            else:
                section_end = end_page if end_page else 9999  # Large number for last section
            
            # If this section has subsections, handle them first
            if section.sections:
                # Get the end page for the last subsection
                last_subsection_start = section.sections[-1].page_start
                subsection_end = section_end
                
                # Recursively populate subsection stats
                self._populate_section_stats(section.sections, elements, None, section_end)
            
            # Calculate stats for this section (excluding subsections if any)
            stats = SectionStats()
            
            # Filter elements for this section's page range
            for formula in elements.get("formulas", []):
                if section_start <= formula["page"] <= section_end:
                    stats.formulas += 1
                    stats.formula_ids.append(formula["id"])
            
            for table in elements.get("tables", []):
                if section_start <= table["page"] <= section_end:
                    stats.tables += 1
                    stats.table_ids.append(table["id"])
            
            for figure in elements.get("figures", []):
                if section_start <= figure["page"] <= section_end:
                    stats.figures += 1
                    stats.figure_ids.append(figure["id"])
            
            for text_block in elements.get("text_blocks", []):
                page = text_block.get("page")
                if page is None or not (section_start <= page <= section_end):
                    continue

                block_is_reference = self._is_reference_block(text_block)
                is_reference_section = self._is_reference_section_name(section.original_name)

                # Keep references isolated to the explicit Reference section.
                if is_reference_section and not block_is_reference:
                    continue
                if not is_reference_section and block_is_reference:
                    continue

                stats.text_blocks += 1
                stats.text_block_ids.append(text_block["id"])
            
            section.stats = stats
