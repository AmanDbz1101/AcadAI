import os
from dotenv import load_dotenv
from langchain_unstructured import UnstructuredLoader
from qdrant_vectorstore import QdrantStore, create_store_from_documents

def extract_and_store_pdf(
    pdf_path: str,
    collection_name: str = "research_papers_main",
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    partition_via_api: bool = True
):
    """
    Extracts data from a PDF using Unstructured API and stores it in Qdrant vectorstore.
    Args:
        pdf_path: Path to the PDF file.
        collection_name: Name of the Qdrant collection.
        embedding_model: Embedding model to use for vectorization.
        partition_via_api: Whether to use Unstructured API for partitioning.
    Returns:
        QdrantStore object for the created collection.
    """
    load_dotenv()
    # Load PDF using UnstructuredLoader
    loader = UnstructuredLoader(
        file_path=pdf_path,
        strategy="hi_res",
        partition_via_api=partition_via_api,
    )
    docs = [doc for doc in loader.lazy_load()]
    # Store in Qdrant
    store = create_store_from_documents(
        documents=docs,
        collection_name=collection_name,
        embedding_model=embedding_model
    )
    return store
