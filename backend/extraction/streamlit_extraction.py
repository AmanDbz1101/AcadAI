"""
Streamlit UI for PDF Extraction.

Allows users to upload PDFs and extract:
- Metadata (title, abstract, sections)
- Section hierarchy
- Full text
- Images, formulas, tables (if found)
"""

import streamlit as st
import json
import os
from pathlib import Path
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.extraction.extraction import PDFExtractor


def display_metadata(metadata: dict):
    """Display extracted metadata in a nice format."""
    st.subheader("📄 Metadata")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Title:**")
        st.info(metadata.get('title', 'N/A'))
        
    with col2:
        st.markdown("**Paper Type:**")
        st.info(metadata.get('inferences', {}).get('paper_type', 'Unknown'))
    
    st.markdown("**Abstract:**")
    abstract = metadata.get('abstract', 'N/A')
    if abstract and abstract != 'N/A':
        st.success(abstract)
    else:
        st.warning("No abstract found")
    
    # Sections
    sections = metadata.get('sections', [])
    if sections:
        st.markdown(f"**Sections ({len(sections)}):**")
        for i, section in enumerate(sections, 1):
            st.text(f"{i}. {section.get('original_name', 'Unknown')} (Level {section.get('level', '?')}, Page {section.get('page_start', '?')})")


def display_hierarchy(hierarchy: dict):
    """Display section hierarchy."""
    st.subheader("🌲 Section Hierarchy")
    
    def render_node(node: dict, depth: int = 0):
        """Recursively render hierarchy tree."""
        indent = "  " * depth
        title = node.get('title', 'Unknown')
        level = node.get('level', '?')
        page = node.get('page_start', '?')
        
        st.text(f"{indent}{'└─' if depth > 0 else '●'} {title} (Level {level}, Page {page})")
        
        children = node.get('children', [])
        for child in children:
            render_node(child, depth + 1)
    
    root_sections = hierarchy.get('root_sections', [])
    if root_sections:
        for root in root_sections:
            render_node(root)
    else:
        st.warning("No hierarchy found")


def display_stats(stats: dict):
    """Display extraction statistics."""
    st.subheader("📊 Statistics")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Pages", stats.get('pages', 0))
    with col2:
        st.metric("Sections", stats.get('sections', 0))
    with col3:
        st.metric("Formulas", stats.get('formulas', 0))
    with col4:
        st.metric("Tables", stats.get('tables', 0))
    with col5:
        st.metric("Figures", stats.get('figures', 0))


def main():
    st.set_page_config(
        page_title="PDF Extraction",
        page_icon="📄",
        layout="wide"
    )
    
    st.title("📄 Research Paper Extraction")
    st.markdown("Extract metadata, hierarchy, and full text from research papers")
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Check if API key is available
        groq_api_key = os.getenv("GROQ_API_KEY")
        if groq_api_key:
            st.success("✓ Groq API Key loaded from .env")
        else:
            st.error("❌ GROQ_API_KEY not found in .env file")
        
        output_dir = st.text_input(
            "Output Directory",
            value="output",
            help="Directory to save extracted files"
        )
        
        force_ocr = st.checkbox(
            "Force OCR",
            value=False,
            help="Force OCR even if PDF has extractable text"
        )
    
    # Main content
    st.header("📤 Upload PDF")
    
    uploaded_file = st.file_uploader(
        "Choose a PDF file",
        type=['pdf'],
        help="Upload a research paper PDF"
    )
    
    if uploaded_file:
        # Save uploaded file temporarily
        temp_dir = Path("temp_uploads")
        temp_dir.mkdir(exist_ok=True)
        
        temp_pdf = temp_dir / uploaded_file.name
        with open(temp_pdf, 'wb') as f:
            f.write(uploaded_file.getbuffer())
        
        st.success(f"✓ Uploaded: {uploaded_file.name}")
        
        # Extract button
        if st.button("🚀 Extract", type="primary"):
            if not groq_api_key:
                st.error("❌ GROQ_API_KEY not found in .env file. Please add it to continue.")
                return
            
            with st.spinner("🔄 Extracting... This may take a few minutes..."):
                try:
                    # Initialize extractor (uses API key from environment)
                    extractor = PDFExtractor()
                    
                    # Run extraction
                    result = extractor.extract(
                        pdf_path=temp_pdf,
                        output_dir=output_dir,
                        force_ocr=force_ocr,
                        save_metadata_file=False,
                        save_fulltext_file=False,
                    )
                    
                    st.success("✅ Extraction completed!")
                    
                    # Display results
                    st.markdown("---")
                    
                    # Stats
                    display_stats(result['stats'])
                    
                    st.markdown("---")
                    
                    # Create tabs for different views
                    tab1, tab2, tab3, tab4 = st.tabs([
                        "📄 Metadata",
                        "🌲 Hierarchy",
                        "📝 Full Text",
                        "📁 Files"
                    ])
                    
                    with tab1:
                        display_metadata(result['metadata'])
                    
                    with tab2:
                        display_hierarchy(result['hierarchy'])
                    
                    with tab3:
                        st.subheader("📝 Full Text")
                        st.text_area(
                            "Full Text",
                            value=result['full_text'][:5000] + "..." if len(result['full_text']) > 5000 else result['full_text'],
                            height=400,
                            help="Showing first 5000 characters"
                        )
                        st.info(f"Total characters: {len(result['full_text'])}")
                    
                    with tab4:
                        st.subheader("📁 Saved Files")
                        st.markdown(f"**Document ID:** `{result['document_id']}`")
                        st.markdown("**Files:**")
                        for file_type, file_path in result['files'].items():
                            st.text(f"• {file_type}: {file_path}")
                        
                        # Download buttons
                        st.markdown("**Download:**")
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            metadata_json = json.dumps(result['metadata'], indent=2, ensure_ascii=False)
                            st.download_button(
                                "📄 Metadata JSON",
                                metadata_json,
                                f"{result['document_id']}_metadata.json",
                                "application/json"
                            )
                        
                        with col2:
                            hierarchy_json = json.dumps(result['hierarchy'], indent=2, ensure_ascii=False)
                            st.download_button(
                                "🌲 Hierarchy JSON",
                                hierarchy_json,
                                f"{result['document_id']}_hierarchy.json",
                                "application/json"
                            )
                        
                        with col3:
                            st.download_button(
                                "📝 Full Text",
                                result['full_text'],
                                f"{result['document_id']}_fulltext.txt",
                                "text/plain"
                            )
                
                except Exception as e:
                    st.error(f"❌ Extraction failed: {str(e)}")
                    st.exception(e)
                
                finally:
                    # Clean up temp file
                    if temp_pdf.exists():
                        temp_pdf.unlink()


if __name__ == "__main__":
    main()
