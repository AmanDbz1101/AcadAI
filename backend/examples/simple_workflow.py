"""
Simple Workflow Examples - Research Paper Assistant
====================================================
Demonstrates the unified LangGraph workflow with different modes:

1. Basic extraction + categorization
2. Q&A mode with user query
3. Summarization mode

Usage:
    python backend/examples/simple_workflow.py
"""

import sys
from pathlib import Path

# Add project root to path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_BACKEND_DIR))

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from backend.run import PaperAnalysisPipeline


def example_basic_extraction():
    """Example 1: Basic extraction + categorization."""
    print("\n" + "=" * 70)
    print("  EXAMPLE 1: Basic Extraction + Categorization")
    print("=" * 70 + "\n")
    
    # Note: Replace with actual PDF path
    pdf_path = "path/to/your/paper.pdf"
    
    if not Path(pdf_path).exists():
        print(f"⚠️  PDF not found: {pdf_path}")
        print("   Please update the pdf_path variable with a valid PDF file.")
        return
    
    pipeline = PaperAnalysisPipeline()
    
    result = pipeline.run(pdf_path=pdf_path)
    
    print(f"✅ Document ID: {result.get('document_id')}")
    print(f"📄 Title: {result.get('title', 'N/A')[:80]}")
    print(f"📚 Category: {result.get('category', 'N/A')}")
    print(f"🎯 Confidence: {result.get('confidence', 'N/A')}")
    print(f"💭 Reasoning: {result.get('category_reasoning', 'N/A')[:150]}")
    
    if result.get('errors'):
        print(f"\n⚠️  Errors: {result['errors']}")
    
    print("\n" + "-" * 70)


def example_qa_mode():
    """Example 2: Q&A mode with user query."""
    print("\n" + "=" * 70)
    print("  EXAMPLE 2: Q&A Mode")
    print("=" * 70 + "\n")
    
    pdf_path = "path/to/your/paper.pdf"
    
    if not Path(pdf_path).exists():
        print(f"⚠️  PDF not found: {pdf_path}")
        print("   Please update the pdf_path variable with a valid PDF file.")
        return
    
    pipeline = PaperAnalysisPipeline()
    
    # Ask a question about the paper
    query = "What is the main contribution of this paper?"
    
    print(f"❓ Query: {query}\n")
    
    result = pipeline.run(
        pdf_path=pdf_path,
        query=query
    )
    
    print(f"✅ Document ID: {result.get('document_id')}")
    print(f"📄 Title: {result.get('title', 'N/A')[:80]}")
    print(f"📚 Category: {result.get('category', 'N/A')}")
    
    if result.get('answer'):
        print(f"\n💬 Answer:")
        print("-" * 70)
        print(result['answer'])
        print("-" * 70)
        print(f"🎯 Answer Confidence: {result.get('answer_confidence', 'N/A')}")
    
    if result.get('errors'):
        print(f"\n⚠️  Errors: {result['errors']}")
    
    print("\n" + "-" * 70)


def example_summarization():
    """Example 3: Summarization mode."""
    print("\n" + "=" * 70)
    print("  EXAMPLE 3: Summarization Mode")
    print("=" * 70 + "\n")
    
    pdf_path = "path/to/your/paper.pdf"
    
    if not Path(pdf_path).exists():
        print(f"⚠️  PDF not found: {pdf_path}")
        print("   Please update the pdf_path variable with a valid PDF file.")
        return
    
    pipeline = PaperAnalysisPipeline()
    
    result = pipeline.run(
        pdf_path=pdf_path,
        summarize=True
    )
    
    print(f"✅ Document ID: {result.get('document_id')}")
    print(f"📄 Title: {result.get('title', 'N/A')[:80]}")
    print(f"📚 Category: {result.get('category', 'N/A')}")
    
    if result.get('summary'):
        print(f"\n📝 Summary:")
        print("=" * 70)
        print(result['summary'])
        print("=" * 70)
    
    if result.get('key_contributions'):
        print(f"\n🎯 Key Contributions:")
        for contrib in result['key_contributions']:
            print(f"  • {contrib}")
    
    if result.get('errors'):
        print(f"\n⚠️  Errors: {result['errors']}")
    
    print("\n" + "-" * 70)


def example_langsmith_tracing():
    """Example 4: Check LangSmith tracing configuration."""
    print("\n" + "=" * 70)
    print("  EXAMPLE 4: LangSmith Tracing Configuration")
    print("=" * 70 + "\n")
    
    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    api_key = os.getenv("LANGCHAIN_API_KEY")
    project = os.getenv("LANGCHAIN_PROJECT", "ResearchPaperAssistant")
    
    print(f"🔍 Tracing Enabled: {tracing_enabled}")
    print(f"🔑 API Key Set: {bool(api_key)}")
    print(f"📊 Project Name: {project}")
    
    if tracing_enabled and api_key:
        print("\n✅ LangSmith tracing is properly configured!")
        print(f"   View traces at: https://smith.langchain.com/o/YOUR_ORG/projects/p/{project}")
    elif tracing_enabled:
        print("\n⚠️  Tracing enabled but API key not set")
        print("   Set LANGCHAIN_API_KEY in your .env file")
    else:
        print("\n💡 To enable tracing:")
        print("   1. Set LANGCHAIN_TRACING_V2=true in .env")
        print("   2. Set LANGCHAIN_API_KEY=<your-key> in .env")
        print("   3. Get your API key from: https://smith.langchain.com/")
    
    print("\n" + "-" * 70)


def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("  RESEARCH PAPER ASSISTANT - WORKFLOW EXAMPLES")
    print("=" * 70)
    
    # Check configuration
    example_langsmith_tracing()
    
    print("\n" + "=" * 70)
    print("  NOTE: Update pdf_path variables in each example function")
    print("  with actual PDF files to run the workflows.")
    print("=" * 70)
    
    # Uncomment to run examples (after setting valid pdf_path):
    # example_basic_extraction()
    # example_qa_mode()
    # example_summarization()
    
    print("\n✅ Examples module loaded successfully!")
    print("   Import and run individual example functions:\n")
    print("   from backend.examples.simple_workflow import example_basic_extraction")
    print("   example_basic_extraction()\n")


if __name__ == "__main__":
    main()
