
"""
PDF loader with docling integration.

Loads PDF files and extracts text with layout signals using docling.
Detects machine-readability and determines if OCR is needed.
"""

import time
import logging
import os
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice

_loader_logger = logging.getLogger(__name__)

_MIN_FREE_GPU_GB = 1.5  # minimum free VRAM required to use GPU


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _other_gpu_compute_pids() -> List[int]:
    """Return PIDs with active CUDA compute contexts, excluding current PID."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []

    current_pid = os.getpid()
    pids: List[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid = int(line)
        except ValueError:
            continue
        if pid != current_pid:
            pids.append(pid)
    return sorted(set(pids))


def _parse_pid_list(raw: str) -> List[int]:
    """Parse comma-separated PID list from env var."""
    parsed: List[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            pid = int(token)
        except ValueError:
            continue
        if pid > 1:
            parsed.append(pid)
    return sorted(set(parsed))


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but ownership/permissions block signaling.
        return True
    return True


def _terminate_pid(pid: int, term_timeout_sec: float, force_kill: bool) -> bool:
    """Try to terminate a PID cleanly, optionally escalating to SIGKILL."""
    if pid <= 1:
        return False

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        _loader_logger.warning("No permission to SIGTERM competing GPU PID=%s", pid)
        return False

    deadline = time.time() + max(0.0, term_timeout_sec)
    while time.time() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.2)

    if not force_kill:
        return not _pid_exists(pid)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except PermissionError:
        _loader_logger.warning("No permission to SIGKILL competing GPU PID=%s", pid)
        return False

    # Give the kernel a short window to reap the process.
    for _ in range(15):
        if not _pid_exists(pid):
            return True
        time.sleep(0.1)
    return not _pid_exists(pid)


def _kill_competing_gpu_processes(
    pids: List[int],
    exclude_pids: List[int],
    term_timeout_sec: float,
    force_kill: bool,
) -> List[int]:
    """Terminate competing GPU compute processes and return killed PID list."""
    excluded = set(exclude_pids)
    killed: List[int] = []

    for pid in sorted(set(pids)):
        if pid in excluded or pid <= 1:
            continue
        if _terminate_pid(pid, term_timeout_sec=term_timeout_sec, force_kill=force_kill):
            killed.append(pid)

    return killed


def _cuda_ready(min_free_gpu_gb: float, require_exclusive: bool) -> tuple[bool, float, List[int]]:
    """
    Check whether CUDA can be used right now.

    Returns (ready, free_gb, competing_pids).
    """
    import torch

    free_bytes, _ = torch.cuda.mem_get_info()
    free_gb = free_bytes / (1024 ** 3)
    competing_pids = _other_gpu_compute_pids() if require_exclusive else []

    if free_gb < min_free_gpu_gb:
        return False, free_gb, competing_pids
    if require_exclusive and competing_pids:
        return False, free_gb, competing_pids
    return True, free_gb, competing_pids


def _get_accelerator_options(num_threads: int = 4) -> AcceleratorOptions:
    """Return accelerator options based on env override and runtime capacity."""
    forced_device = (os.getenv("DOCLING_DEVICE") or "").strip().lower()
    require_cuda = _env_flag("DOCLING_REQUIRE_CUDA", forced_device == "cuda")
    require_gpu_exclusive = _env_flag("DOCLING_GPU_EXCLUSIVE", True)
    wait_for_gpu = _env_flag("DOCLING_WAIT_FOR_GPU", True)
    wait_timeout_seconds = float(os.getenv("DOCLING_GPU_WAIT_TIMEOUT_SEC", "0"))
    poll_interval_seconds = float(os.getenv("DOCLING_GPU_POLL_INTERVAL_SEC", "2"))
    min_free_gpu_gb = float(os.getenv("DOCLING_MIN_FREE_GPU_GB", str(_MIN_FREE_GPU_GB)))
    kill_competing_gpu_procs = _env_flag("DOCLING_KILL_OTHER_GPU_PROCS", True)
    kill_term_timeout_sec = float(os.getenv("DOCLING_GPU_KILL_TERM_TIMEOUT_SEC", "5"))
    kill_force = _env_flag("DOCLING_GPU_FORCE_KILL", True)
    excluded_pids = _parse_pid_list(os.getenv("DOCLING_GPU_KILL_EXCLUDE_PIDS", ""))

    if os.getpid() not in excluded_pids:
        excluded_pids.append(os.getpid())

    if forced_device == "cpu":
        _loader_logger.info("DOCLING_DEVICE=cpu set; using CPU for docling")
        return AcceleratorOptions(num_threads=num_threads, device=AcceleratorDevice.CPU)

    try:
        import torch

        if not torch.cuda.is_available():
            if require_cuda:
                raise RuntimeError("CUDA is required but torch.cuda.is_available() is False")
            _loader_logger.info("Using CPU for docling (CUDA unavailable)")
            return AcceleratorOptions(num_threads=num_threads, device=AcceleratorDevice.CPU)

        deadline = None if wait_timeout_seconds <= 0 else time.time() + wait_timeout_seconds
        attempted_kill_pids: set[int] = set()
        while True:
            ready, free_gb, competing_pids = _cuda_ready(
                min_free_gpu_gb=min_free_gpu_gb,
                require_exclusive=require_gpu_exclusive,
            )
            if ready:
                _loader_logger.info(
                    "Using GPU for docling (free VRAM: %.2f GB, exclusive=%s)",
                    free_gb,
                    require_gpu_exclusive,
                )
                return AcceleratorOptions(num_threads=num_threads, device=AcceleratorDevice.CUDA)

            if kill_competing_gpu_procs:
                # Kill candidates include competing PIDs reported by exclusivity mode;
                # when VRAM is low without exclusivity, inspect all compute PIDs.
                kill_candidates = competing_pids or _other_gpu_compute_pids()
                kill_candidates = [
                    pid for pid in kill_candidates if pid not in attempted_kill_pids
                ]
                if kill_candidates:
                    attempted_kill_pids.update(kill_candidates)
                    killed = _kill_competing_gpu_processes(
                        pids=kill_candidates,
                        exclude_pids=excluded_pids,
                        term_timeout_sec=kill_term_timeout_sec,
                        force_kill=kill_force,
                    )
                    if killed:
                        _loader_logger.warning(
                            "Terminated competing GPU process(es): %s",
                            killed,
                        )
                        time.sleep(max(0.2, poll_interval_seconds))
                        continue

            if not wait_for_gpu or (deadline is not None and time.time() >= deadline):
                reason = (
                    f"GPU not ready (free VRAM={free_gb:.2f} GB, "
                    f"required>={min_free_gpu_gb:.2f} GB, competing_pids={competing_pids})"
                )
                if require_cuda or forced_device == "cuda":
                    raise RuntimeError(f"{reason}; refusing CPU fallback because CUDA is required")
                _loader_logger.warning("%s; falling back to CPU", reason)
                return AcceleratorOptions(num_threads=num_threads, device=AcceleratorDevice.CPU)

            _loader_logger.info(
                "Waiting for GPU availability (free VRAM: %.2f GB, competing_pids=%s)",
                free_gb,
                competing_pids,
            )
            time.sleep(max(0.2, poll_interval_seconds))
    except Exception as exc:
        _loader_logger.exception(
            "GPU accelerator selection failed with %s; evaluating CPU fallback",
            type(exc).__name__,
        )
        if require_cuda or forced_device == "cuda":
            raise
    _loader_logger.info("Using CPU for docling")
    return AcceleratorOptions(num_threads=num_threads, device=AcceleratorDevice.CPU)
from docling_core.types.doc import DoclingDocument, DocItem

from backend.extraction.models.document import (
    PageContent,
    LayoutSignals,
    BoundingBox,
    FontInfo,
)


@dataclass
class LoaderConfig:
    """Configuration for PDF loader."""
    do_ocr: bool = False  # Enable OCR for scanned PDFs
    extract_images: bool = True
    extract_tables: bool = True
    ocr_engine: str = "easyocr"  # "easyocr" or "tesseract"
    generate_page_images: bool = False
    generate_picture_images: bool = False
    timeout_seconds: int = 120
    parallel_page_processing: bool = False
    page_workers: int = 4


class PDFLoader:
    """
    Loads PDF files using docling and extracts structured content.
    
    Features:
    - Automatic text extraction with layout preservation
    - Machine-readability detection
    - Optional OCR for scanned documents
    - Bounding box and font signal extraction
    - Reading order preservation
    """
    
    def __init__(self, config: Optional[LoaderConfig] = None):
        """
        Initialize PDF loader.
        
        Args:
            config: Loader configuration (uses defaults if None)
        """
        self.config = config or LoaderConfig()
        self._initialize_converter()
    
    def _initialize_converter(self, force_cpu: bool = False):
        """Initialize docling converter with pipeline options."""
        accelerator_options = (
            AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU)
            if force_cpu
            else _get_accelerator_options()
        )

        # Configure pipeline options
        pipeline_options = PdfPipelineOptions(
            do_ocr=self.config.do_ocr,
            do_table_structure=self.config.extract_tables,
            images_scale=1.0,
            generate_page_images=self.config.generate_page_images,
            generate_picture_images=self.config.generate_picture_images,
            # do_formula_enrichment=True,
            accelerator_options=accelerator_options,
        )
        
        # Create converter with options
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options
                )
            }
        )

    @staticmethod
    def _is_meta_tensor_error(exc: Exception) -> bool:
        message = str(exc)
        return (
            "Cannot copy out of meta tensor" in message
            or "to_empty()" in message
            or "meta tensor" in message.lower()
        )
    
    def load(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Load PDF and extract content with layout signals.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dictionary containing:
                - pages: List of PageContent objects
                - full_text: Concatenated text
                - metadata: Document metadata
                - processing_time: Time taken in seconds
        """
        start_time = time.time()
        
        # Convert PDF. If a model was initialized on a meta device by an
        # upstream dependency, retry once on CPU to avoid hard API failures.
        try:
            result = self.converter.convert(pdf_path)
        except Exception as exc:
            if self._is_meta_tensor_error(exc):
                _loader_logger.warning(
                    "Docling conversion hit meta tensor device error. Retrying on CPU once."
                )
                self._initialize_converter(force_cpu=True)
                result = self.converter.convert(pdf_path)
            else:
                raise

        doc: DoclingDocument = result.document
        
        # Extract pages with layout information
        pages = self._extract_pages(doc)
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Build result
        return {
            "pages": pages,
            "full_text": "\n\n".join(page.text for page in pages),
            "metadata": self._extract_metadata(doc),
            "page_count": len(pages),
            "processing_time": processing_time,
            "docling_document": doc,  # Cache the DoclingDocument for downstream use
        }
    
    def _extract_pages(self, doc: DoclingDocument) -> List[PageContent]:
        """
        Extract page-wise content with layout signals.
        
        Args:
            doc: Docling document
            
        Returns:
            List of PageContent objects
        """
        pages_dict: Dict[int, List[str]] = {}
        pages_metadata: Dict[int, Dict[str, Any]] = {}
        
        # Group items by page
        for item, level in doc.iterate_items():
            if hasattr(item, 'prov') and item.prov:
                for prov in item.prov:
                    page_no = prov.page_no + 1  # Convert to 1-indexed
                    
                    # Initialize page if needed
                    if page_no not in pages_dict:
                        pages_dict[page_no] = []
                        pages_metadata[page_no] = {
                            'has_images': False,
                            'has_tables': False,
                            'has_formulas': False,
                        }
                    
                    # Extract text
                    text = self._get_item_text(item, doc)
                    if text:
                        pages_dict[page_no].append(text)
                    
                    # Track element types
                    if hasattr(item, 'label'):
                        label = item.label.lower() if item.label else ""
                        if 'picture' in label or 'figure' in label:
                            pages_metadata[page_no]['has_images'] = True
                        elif 'table' in label:
                            pages_metadata[page_no]['has_tables'] = True
                        elif 'formula' in label or 'equation' in label:
                            pages_metadata[page_no]['has_formulas'] = True
        
        def _build_page(page_no: int) -> PageContent:
            text = "\n".join(pages_dict[page_no])
            metadata = pages_metadata[page_no]
            return PageContent(
                page_number=page_no,
                text=text,
                word_count=len(text.split()),
                char_count=len(text),
                has_images=metadata['has_images'],
                has_tables=metadata['has_tables'],
                has_formulas=metadata['has_formulas'],
            )

        page_numbers = sorted(pages_dict.keys())
        if self.config.parallel_page_processing and len(page_numbers) > 1:
            workers = max(1, min(self.config.page_workers, len(page_numbers)))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                pages = list(executor.map(_build_page, page_numbers))
        else:
            pages = [_build_page(page_no) for page_no in page_numbers]

        return pages
    
    def _get_item_text(self, item: DocItem, doc: DoclingDocument) -> str:
        """
        Extract text from a document item.
        
        Args:
            item: Document item
            doc: Parent document (required for export_to_markdown)
            
        Returns:
            Extracted text
        """
        if hasattr(item, 'text') and item.text:
            return item.text
        elif hasattr(item, 'export_to_markdown'):
            try:
                return item.export_to_markdown(doc)
            except Exception:
                # Fallback if export_to_markdown fails
                return ""
        return ""
    
    def _extract_metadata(self, doc: DoclingDocument) -> Dict[str, Any]:
        """
        Extract document metadata.
        
        Args:
            doc: Docling document
            
        Returns:
            Metadata dictionary
        """
        metadata = {}
        
        # Try to extract title
        if hasattr(doc, 'name') and doc.name:
            metadata['title'] = doc.name
        
        # Extract other available metadata
        if hasattr(doc, 'origin'):
            metadata['origin'] = doc.origin
        
        return metadata
    
    def detect_readability(self, pages: List[PageContent]) -> Dict[str, Any]:
        """
        Detect if PDF is machine-readable or needs OCR.
        
        Args:
            pages: List of PageContent objects
            
        Returns:
            Dictionary with readability analysis:
                - is_machine_readable: bool
                - average_text_density: float
                - low_density_pages: List[int]
                - recommendation: str
        """
        if not pages:
            return {
                "is_machine_readable": False,
                "average_text_density": 0,
                "low_density_pages": [],
                "recommendation": "No pages found"
            }
        
        # Calculate text density per page (chars per page)
        densities = [page.char_count for page in pages]
        average_density = sum(densities) / len(densities)
        
        # Threshold: < 50 chars per page suggests scanned/image content
        OCR_THRESHOLD = 50
        low_density_pages = [
            page.page_number 
            for page in pages 
            if page.char_count < OCR_THRESHOLD
        ]
        
        is_machine_readable = average_density >= OCR_THRESHOLD
        
        # Generate recommendation
        if is_machine_readable:
            recommendation = "Digital PDF - no OCR needed"
        elif len(low_density_pages) == len(pages):
            recommendation = "Fully scanned PDF - OCR required for all pages"
        else:
            recommendation = f"Hybrid PDF - OCR needed for {len(low_density_pages)} pages"
        
        return {
            "is_machine_readable": is_machine_readable,
            "average_text_density": average_density,
            "low_density_pages": low_density_pages,
            "recommendation": recommendation,
            "total_pages": len(pages),
            "pages_needing_ocr": len(low_density_pages),
        }
    
    def reload_with_ocr(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Reload PDF with OCR enabled.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Same format as load() but with OCR applied
        """
        # Create new config with OCR enabled
        ocr_config = LoaderConfig(
            do_ocr=True,
            extract_images=self.config.extract_images,
            extract_tables=self.config.extract_tables,
            ocr_engine=self.config.ocr_engine,
            timeout_seconds=self.config.timeout_seconds,
        )
        
        # Create new loader with OCR enabled
        ocr_loader = PDFLoader(config=ocr_config)
        
        # Load with OCR
        return ocr_loader.load(pdf_path)
