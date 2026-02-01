"""
Tools for Executor Agent
Provides document search, element retrieval, and diagram explanation capabilities
"""
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class DocumentSearchInput(BaseModel):
    """Input schema for document search tool"""
    query: str = Field(..., description="Natural language search query")
    document_id: str = Field(..., description="Document ID to search within")
    categories: Optional[List[str]] = Field(
        default=None,
        description="Filter by categories: NarrativeText, Table, FigureCaption, Formula, Image, etc."
    )
    sections: Optional[List[str]] = Field(
        default=None,
        description="Filter by section names"
    )
    limit: int = Field(default=5, description="Maximum number of results")


class GetElementInput(BaseModel):
    """Input schema for get element by ID tool"""
    element_id: str = Field(..., description="Element ID hash from metadata")
    document_id: str = Field(..., description="Document ID")


class DiagramExplainerInput(BaseModel):
    """Input schema for diagram explainer tool"""
    element_id: str = Field(..., description="Element ID of the figure/table/formula")
    element_type: Literal["figure", "table", "formula"] = Field(..., description="Type of visual element")
    document_id: str = Field(..., description="Document ID")
    context_query: Optional[str] = Field(
        default=None,
        description="Optional context about what to look for in the diagram"
    )


class AgenticTools:
    """Tool implementations for executor agent"""
    
    def __init__(self, collection_name: str = "research_papers_main"):
        # Use QdrantStore from the project
        from qdrant_vectorstore import QdrantStore
        self.store = QdrantStore.from_existing(collection_name=collection_name)
        self.collection_name = collection_name
        
    def document_search(
        self,
        query: str,
        document_id: str,
        categories: Optional[List[str]] = None,
        sections: Optional[List[str]] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant content in the document using semantic search with filters.
        
        Args:
            query: Natural language search query
            document_id: Document ID to search within
            categories: Filter by content categories
            sections: Filter by section names
            limit: Maximum number of results
            
        Returns:
            List of retrieved documents with content and metadata
        """
        try:
            # Use QdrantStore.similarity_search method
            results = self.store.similarity_search(query, k=limit * 3)
            
            # Format and post-filter results
            formatted_results = []
            for doc in results:
                # Post-filter by document_id (filename)
                if doc.metadata.get('filename') != document_id:
                    continue
                
                # Post-filter by categories
                if categories and doc.metadata.get('category') not in categories:
                    continue
                
                # Post-filter by sections (check if section name in content)
                if sections:
                    section_match = any(sec.lower() in doc.page_content.lower() for sec in sections)
                    if not section_match:
                        continue
                
                formatted_results.append({
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "source": {
                        "page": doc.metadata.get("page_number", "unknown"),
                        "category": doc.metadata.get("category", "unknown"),
                        "element_id": doc.metadata.get("element_id", "unknown"),
                    }
                })
                
                if len(formatted_results) >= limit:
                    break
            
            return formatted_results[:limit]
            
        except Exception as e:
            print(f"Error in document_search: {e}")
            return []
    
    def get_element_by_id(
        self,
        element_id: str,
        document_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific element by its ID.
        
        Args:
            element_id: Element ID hash
            document_id: Document ID
            
        Returns:
            Element content and metadata, or None if not found
        """
        try:
            # Search broadly, then post-filter for the specific element
            results = self.store.similarity_search("", k=200)
            
            for doc in results:
                # Match both filename and element_id
                if (doc.metadata.get('filename') == document_id and 
                    doc.metadata.get('element_id') == element_id):
                    return {
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "source": {
                            "page": doc.metadata.get("page_number", "unknown"),
                            "category": doc.metadata.get("category", "unknown"),
                            "element_id": doc.metadata.get("element_id", "unknown"),
                            "coordinates": doc.metadata.get("coordinates")
                        }
                    }
            
            return None
            
        except Exception as e:
            print(f"Error in get_element_by_id: {e}")
            return None
    
    def diagram_explainer(
        self,
        element_id: str,
        element_type: Literal["figure", "table", "formula"],
        document_id: str,
        context_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Explain a diagram/table/formula using retrieval and analysis.
        
        Args:
            element_id: Element ID
            element_type: Type of visual element
            document_id: Document ID
            context_query: Optional context about what to look for
            
        Returns:
            Explanation with element details
        """
        try:
            # Get the element itself
            element = self.get_element_by_id(element_id, document_id)
            
            if not element:
                return {
                    "error": f"Element {element_id} not found",
                    "element_id": element_id
                }
            
            # Get surrounding context
            page = element["source"]["page"]
            category_map = {
                "figure": "FigureCaption",
                "table": "Table",
                "formula": "Formula"
            }
            
            # Search for context on the same page
            context_results = self.store.similarity_search(
                context_query or f"{element_type} explanation",
                k=10
            )
            
            # Post-filter for same page and relevant categories
            context_text = ""
            for doc in context_results:
                if (doc.metadata.get('filename') == document_id and 
                    doc.metadata.get('page_number') == page):
                    context_text += doc.page_content + "\n"
            
            explanation = {
                "element_id": element_id,
                "element_type": element_type,
                "element_content": element["content"],
                "page": page,
                "surrounding_context": context_text[:500],
                "coordinates": element["source"].get("coordinates"),
                "analysis": f"This {element_type} appears on page {page}. "
            }
            
            # Add type-specific analysis
            if element_type == "figure":
                explanation["analysis"] += "The figure should be examined in the PDF for visual details. "
            elif element_type == "table":
                explanation["analysis"] += f"Table content: {element['content'][:500]}... "
            elif element_type == "formula":
                explanation["analysis"] += f"Formula: {element['content']}. "
                
            explanation["analysis"] += f"Context: {context_text[:300]}..."
            
            return explanation
            
        except Exception as e:
            print(f"Error in diagram_explainer: {e}")
            return {
                "error": str(e),
                "element_id": element_id
            }
    
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """
        Get tool schemas for LLM function calling.
        
        Returns:
            List of tool definitions in OpenAI function calling format
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "document_search",
                    "description": "Search for relevant content in the research paper using semantic search. Use this to find specific sections, concepts, or information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Natural language search query describing what you're looking for"
                            },
                            "document_id": {
                                "type": "string",
                                "description": "Document ID to search within"
                            },
                            "categories": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional: Filter by categories like 'NarrativeText', 'Table', 'FigureCaption', 'Formula'"
                            },
                            "sections": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional: Filter by section names"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results (default: 5)"
                            }
                        },
                        "required": ["query", "document_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_element_by_id",
                    "description": "Retrieve a specific element (figure, table, formula, or text block) by its unique ID from the metadata.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "element_id": {
                                "type": "string",
                                "description": "Element ID hash from the metadata"
                            },
                            "document_id": {
                                "type": "string",
                                "description": "Document ID"
                            }
                        },
                        "required": ["element_id", "document_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "diagram_explainer",
                    "description": "Get detailed explanation of a diagram, table, or formula including its context and analysis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "element_id": {
                                "type": "string",
                                "description": "Element ID of the figure/table/formula"
                            },
                            "element_type": {
                                "type": "string",
                                "enum": ["figure", "table", "formula"],
                                "description": "Type of visual element"
                            },
                            "document_id": {
                                "type": "string",
                                "description": "Document ID"
                            },
                            "context_query": {
                                "type": "string",
                                "description": "Optional: What to look for in the diagram"
                            }
                        },
                        "required": ["element_id", "element_type", "document_id"]
                    }
                }
            }
        ]
