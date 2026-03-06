"""
Groq API fallback mechanism for metadata extraction.

Uses LLaMA-3.3-70B Versatile model to extract missing metadata fields
when heuristic extraction fails.
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any

from groq import Groq

from backend.extraction.models.document import ValidatedDocument
from backend.extraction.models.metadata import ExtractedMetadata, Author
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class GroqFallbackExtractor:
    """
    Fallback metadata extractor using Groq API and LLaMA-3.3-70B.
    
    Used when heuristic extraction fails to find certain metadata fields.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama-3.3-70b-versatile",
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ):
        """
        Initialize Groq fallback extractor.
        
        Args:
            api_key: Groq API key (defaults to GROQ_API_KEY env var)
            model: Model name to use
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (lower = more deterministic)
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Groq API key not found. Set GROQ_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.client = Groq(api_key=self.api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
    
    def extract_missing_fields(
        self,
        document: ValidatedDocument,
        missing_fields: List[str],
        existing_metadata: Optional[ExtractedMetadata] = None,
    ) -> Dict[str, Any]:
        """
        Extract missing metadata fields using LLM.
        
        Args:
            document: ValidatedDocument to extract from
            missing_fields: List of field names to extract
            existing_metadata: Already extracted metadata (for context)
            
        Returns:
            Dictionary with extracted field values
        """
        if not missing_fields:
            return {}
        
        logger.info(f"Using Groq fallback to extract: {missing_fields}")
        
        # Prepare document text (first 3 pages)
        text = self._prepare_text(document, max_pages=3)
        
        # Build prompt
        prompt = self._build_extraction_prompt(missing_fields, text, existing_metadata)
        
        # Query LLM
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise metadata extraction assistant. "
                        "Extract only the requested information from research papers. "
                        "Return valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            result = json.loads(response.choices[0].message.content)
            
            # Clean and validate results
            cleaned_result = self._clean_results(result, missing_fields)
            
            logger.info(f"Successfully extracted {len(cleaned_result)} fields via Groq")
            return cleaned_result
            
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            return {}
    
    def _prepare_text(self, document: ValidatedDocument, max_pages: int = 3) -> str:
        """
        Prepare document text for LLM extraction.
        
        Args:
            document: ValidatedDocument
            max_pages: Maximum number of pages to include
            
        Returns:
            Formatted text string
        """
        pages_text = []
        for page in document.pages[:max_pages]:
            pages_text.append(f"--- Page {page.page_number} ---\n{page.text}")
        
        return "\n\n".join(pages_text)
    
    def _build_extraction_prompt(
        self,
        missing_fields: List[str],
        text: str,
        existing_metadata: Optional[ExtractedMetadata] = None,
    ) -> str:
        """
        Build extraction prompt for LLM.
        
        Args:
            missing_fields: Fields to extract
            text: Document text
            existing_metadata: Already extracted metadata
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = []
        
        prompt_parts.append("Extract the following metadata from this research paper:")
        prompt_parts.append("")
        
        # List requested fields with descriptions
        field_descriptions = {
            'title': "The full title of the paper",
            'authors': "List of author names (as array of objects with 'name' field)",
            'abstract': "The abstract or summary of the paper",
            'keywords': "List of keywords or key terms (as array of strings)",
            'doi': "The DOI (Digital Object Identifier)",
            'publication_venue': "Journal or conference name",
            'publication_year': "Year of publication (as integer)",
        }
        
        prompt_parts.append("**Fields to extract:**")
        for field in missing_fields:
            desc = field_descriptions.get(field, f"The {field} of the paper")
            prompt_parts.append(f"- {field}: {desc}")
        
        prompt_parts.append("")
        prompt_parts.append("**Instructions:**")
        prompt_parts.append("- Extract ONLY the requested fields")
        prompt_parts.append("- If a field is not found, omit it from the response")
        prompt_parts.append("- Return valid JSON with the extracted fields")
        prompt_parts.append("- For authors, use format: [{\"name\": \"John Doe\"}, ...]")
        prompt_parts.append("- For keywords, use format: [\"keyword1\", \"keyword2\", ...]")
        
        if existing_metadata:
            prompt_parts.append("")
            prompt_parts.append("**Already extracted fields (for context):**")
            if existing_metadata.title:
                prompt_parts.append(f"- Title: {existing_metadata.title}")
            if existing_metadata.authors:
                author_names = [a.name for a in existing_metadata.authors]
                prompt_parts.append(f"- Authors: {', '.join(author_names[:3])}")
        
        prompt_parts.append("")
        prompt_parts.append("**Document text:**")
        prompt_parts.append(text[:6000])  # Limit text length
        
        if len(text) > 6000:
            prompt_parts.append("\n[... text truncated ...]")
        
        return "\n".join(prompt_parts)
    
    def _clean_results(
        self,
        result: Dict[str, Any],
        requested_fields: List[str]
    ) -> Dict[str, Any]:
        """
        Clean and validate LLM extraction results.
        
        Args:
            result: Raw LLM response
            requested_fields: Fields that were requested
            
        Returns:
            Cleaned result dictionary
        """
        cleaned = {}
        
        for field in requested_fields:
            if field in result and result[field]:
                value = result[field]
                
                # Field-specific cleaning
                if field == 'authors':
                    # Ensure it's a list of Author objects
                    if isinstance(value, list):
                        cleaned_authors = []
                        for author_data in value[:20]:  # Limit to 20 authors
                            if isinstance(author_data, dict) and 'name' in author_data:
                                name = str(author_data['name']).strip()
                                if name and len(name) > 2:
                                    cleaned_authors.append(Author(
                                        name=name,
                                        email=author_data.get('email'),
                                        affiliation=author_data.get('affiliation')
                                    ))
                        if cleaned_authors:
                            cleaned[field] = cleaned_authors
                
                elif field == 'keywords':
                    # Ensure it's a list of strings
                    if isinstance(value, list):
                        cleaned_keywords = []
                        for kw in value[:15]:  # Limit to 15 keywords
                            kw_str = str(kw).strip()
                            if kw_str and 2 <= len(kw_str) <= 50:
                                cleaned_keywords.append(kw_str)
                        if cleaned_keywords:
                            cleaned[field] = cleaned_keywords
                
                elif field in ['title', 'abstract', 'doi', 'publication_venue']:
                    # String fields
                    str_value = str(value).strip()
                    if str_value:
                        # Length validation
                        if field == 'title' and 10 <= len(str_value) <= 500:
                            cleaned[field] = str_value
                        elif field == 'abstract' and 100 <= len(str_value) <= 5000:
                            cleaned[field] = str_value
                        elif field == 'doi' and 7 <= len(str_value) <= 100:
                            cleaned[field] = str_value
                        elif field == 'publication_venue' and 3 <= len(str_value) <= 200:
                            cleaned[field] = str_value
                
                elif field == 'publication_year':
                    # Integer field
                    try:
                        year = int(value)
                        if 1900 <= year <= 2030:
                            cleaned[field] = year
                    except (ValueError, TypeError):
                        pass
        
        return cleaned
    
    def merge_with_existing(
        self,
        existing_metadata: ExtractedMetadata,
        llm_extracted: Dict[str, Any]
    ) -> ExtractedMetadata:
        """
        Merge LLM-extracted fields with existing metadata.
        
        Args:
            existing_metadata: Metadata from heuristic extraction
            llm_extracted: Fields extracted by LLM
            
        Returns:
            Updated ExtractedMetadata
        """
        # Update missing fields
        for field, value in llm_extracted.items():
            if hasattr(existing_metadata, field):
                current_value = getattr(existing_metadata, field)
                
                # Only update if current value is empty/None
                if not current_value or (isinstance(current_value, list) and len(current_value) == 0):
                    setattr(existing_metadata, field, value)
        
        # Update extraction metadata
        existing_metadata.fallback_used = True
        existing_metadata.extraction_method = "heuristic+llm"
        
        # Recalculate missing fields
        missing = []
        if not existing_metadata.title:
            missing.append('title')
        if not existing_metadata.authors:
            missing.append('authors')
        if not existing_metadata.abstract:
            missing.append('abstract')
        if not existing_metadata.keywords:
            missing.append('keywords')
        if not existing_metadata.doi:
            missing.append('doi')
        
        existing_metadata.missing_fields = missing
        existing_metadata.confidence_score = existing_metadata.get_field_coverage()
        
        return existing_metadata
