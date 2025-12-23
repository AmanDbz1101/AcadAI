"""
Section name normalization to canonical labels.

This module maps detected section names to a standard set of canonical labels.
"""

from typing import Optional
import re


class SectionNormalizer:
    """Normalizes section names to canonical labels."""
    
    # Canonical section names
    CANONICAL_SECTIONS = {
        'Introduction',
        'Related Work',
        'Background',
        'Methodology',
        'Experiments',
        'Results',
        'Discussion',
        'Limitations',
        'Conclusion'
    }
    
    # Mapping patterns: lowercase patterns -> canonical name
    NORMALIZATION_RULES = {
        # Introduction
        'Introduction': [
            r'\bintro\b',
            r'\bintroduction\b',
            r'\bmotivation\b',
            r'\boverview\b',
        ],
        # Related Work
        'Related Work': [
            r'\brelated work\b',
            r'\bprior work\b',
            r'\bliterature review\b',
            r'\bprevious work\b',
            r'\brelated research\b',
        ],
        # Background
        'Background': [
            r'\bbackground\b',
            r'\bpreliminaries\b',
            r'\bfoundation\b',
            r'\bnotation\b',
            r'\bproblem statement\b',
            r'\bproblem definition\b',
            r'\bformulation\b',
        ],
        # Methodology
        'Methodology': [
            r'\bmethodology\b',
            r'\bmethod\b',
            r'\bapproach\b',
            r'\bproposed method\b',
            r'\bour approach\b',
            r'\btechnique\b',
            r'\bsystem design\b',
            r'\barchitecture\b',
            r'\bimplementation\b',
            r'\balgorithm\b',
            r'\bmodel\b',
        ],
        # Experiments
        'Experiments': [
            r'\bexperiment\b',
            r'\bexperimental setup\b',
            r'\bevaluation setup\b',
            r'\bsetup\b',
            r'\bdataset\b',
            r'\bbenchmark\b',
        ],
        # Results
        'Results': [
            r'\bresult\b',
            r'\bfinding\b',
            r'\bevaluation\b',
            r'\bperformance\b',
            r'\banalysis\b',
        ],
        # Discussion
        'Discussion': [
            r'\bdiscussion\b',
            r'\banalysis and discussion\b',
            r'\binterpretation\b',
        ],
        # Limitations
        'Limitations': [
            r'\blimitation\b',
            r'\bfuture work\b',
            r'\bfuture direction\b',
            r'\bthreat to validity\b',
        ],
        # Conclusion
        'Conclusion': [
            r'\bconclusion\b',
            r'\bconcluding remark\b',
            r'\bsummary\b',
            r'\bfinal remark\b',
        ],
    }
    
    def __init__(self):
        """Initialize the section normalizer."""
        # Compile regex patterns for efficiency
        self.compiled_rules = {}
        for canonical, patterns in self.NORMALIZATION_RULES.items():
            self.compiled_rules[canonical] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]
    
    def normalize(self, section_name: str) -> Optional[str]:
        """Normalize a section name to canonical label.
        
        Args:
            section_name: Original section name from paper
            
        Returns:
            Canonical section name, or None if no clear mapping
        """
        # Clean the section name
        cleaned = self._clean_section_name(section_name)
        
        if not cleaned:
            return None
        
        # Try to match against normalization rules
        for canonical, patterns in self.compiled_rules.items():
            for pattern in patterns:
                if pattern.search(cleaned):
                    return canonical
        
        # No match found
        return None
    
    def _clean_section_name(self, section_name: str) -> str:
        """Clean section name by removing numbering and extra whitespace.
        
        Args:
            section_name: Raw section name
            
        Returns:
            Cleaned section name
        """
        text = section_name.strip()
        
        # Remove leading numbers: "1.", "1.1", "I.", etc.
        text = re.sub(r'^[\dIVXivx]+[\.\)]\s*', '', text)
        text = re.sub(r'^[\dIVXivx]+\s+', '', text)
        
        # Remove trailing numbers
        text = re.sub(r'\s+[\d]+$', '', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text.lower()
    
    def get_canonical_sections(self) -> set[str]:
        """Get the set of canonical section names.
        
        Returns:
            Set of canonical section names
        """
        return self.CANONICAL_SECTIONS.copy()
