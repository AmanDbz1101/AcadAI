"""
Deterministic section detection using heuristics.

This module detects sections ONLY using rules-based approaches.
NO LLM is used here.
"""

import re
from typing import List, Tuple, Optional, Set
from .models import QdrantPoint, SectionMetadata, SectionStats


class SectionDetector:
    """Detects section boundaries using deterministic heuristics."""
    
    # Patterns for detecting section numbering
    SECTION_PATTERNS = [
        r'^\d+\.?\s+',  # "1 Introduction" or "1. Introduction"
        r'^\d+\.\d+\.?\s+',  # "1.1 Background" or "1.1. Background"
        r'^\d+\.\d+\.\d+\.?\s+',  # "1.1.1 Details"
        r'^[IVX]+\.?\s+',  # Roman numerals "I Introduction"
        r'^[A-Z]\.?\s+',  # "A Appendix"
        r'^Appendix\s+[A-Z]',  # "Appendix A"
    ]
    
    # Special section keywords (case-insensitive)
    SPECIAL_SECTIONS = {
        'abstract', 'introduction', 'conclusion', 'conclusions',
        'references', 'bibliography', 'acknowledgments', 'acknowledgements',
        'appendix', 'supplementary', 'related work', 'background',
        'methods', 'methodology', 'experiments', 'results', 'discussion'
    }
    
    def detect_sections(self, points: List[QdrantPoint]) -> List[SectionMetadata]:
        """
        Detect all sections from document points, including a Title section.
        
        Args:
            points: Ordered list of document points
            
        Returns:
            List of detected section metadata (sorted by position) with Title section first
        """
        section_candidates = []
        
        for point in points:
            # Only consider Title category for sections
            if point.category != "Title":
                continue
            
            content = point.page_content.strip()
            if not content:
                continue
            
            # Detect section level
            level = self._detect_level(content)
            if level == 0:
                # Not a section heading
                continue
            
            # Extract position info
            y_position = self._get_y_position(point)
            x_position = self._get_x_position(point)
            
            section_candidates.append({
                'content': content,
                'level': level,
                'page': point.page_number,
                'y_pos': y_position,
                'x_pos': x_position,
                'point': point
            })
        
        # Sort by page, then y-position, then x-position
        section_candidates.sort(key=lambda s: (s['page'], s['y_pos'], s['x_pos']))
        
        # Create section metadata objects
        sections = []
        for candidate in section_candidates:
            section = SectionMetadata(
                original_name=candidate['content'],
                level=candidate['level'],
                page_start=candidate['page'],
                stats=SectionStats()
            )
            sections.append(section)
        
        # Create Title section at the beginning
        # It will be populated by compute_stats
        title_section = SectionMetadata(
            original_name="Title",
            level=1,
            page_start=1,
            stats=SectionStats()
        )
        
        # Insert Title section at the beginning
        sections.insert(0, title_section)
        
        return sections
    
    def _detect_level(self, text: str) -> int:
        """
        Detect section level from text.
        
        Args:
            text: Section heading text
            
        Returns:
            Level (1-5) or 0 if not a section
        """
        # Check for numbered sections
        for pattern in self.SECTION_PATTERNS:
            match = re.match(pattern, text)
            if match:
                # Count dots to determine depth
                dots = match.group(0).count('.')
                if dots == 0:
                    return 1
                else:
                    return min(dots + 1, 5)
        
        # Check for special keywords
        text_lower = text.lower()
        for keyword in self.SPECIAL_SECTIONS:
            if text_lower.startswith(keyword):
                return 1
        
        # Heuristic: all caps likely a section
        if text.isupper() and len(text.split()) <= 5:
            return 1
        
        return 0
    
    def _get_y_position(self, point: QdrantPoint) -> float:
        """Extract Y position from coordinates."""
        if not point.coordinates:
            return 0.0
        
        points_list = point.coordinates.get('points', [])
        if not points_list:
            return 0.0
        
        # Use minimum Y (top of element)
        y_coords = [p[1] for p in points_list if len(p) >= 2]
        return min(y_coords) if y_coords else 0.0
    
    def _get_x_position(self, point: QdrantPoint) -> float:
        """Extract X position from coordinates."""
        if not point.coordinates:
            return 0.0
        
        points_list = point.coordinates.get('points', [])
        if not points_list:
            return 0.0
        
        # Use minimum X (left edge)
        x_coords = [p[0] for p in points_list if len(p) >= 2]
        return min(x_coords) if x_coords else 0.0
    
    def _detect_layout(self, points: List[QdrantPoint]) -> str:
        """Detect if document has single or multi-column layout."""
        x_positions = []
        
        for point in points:
            if point.category in ("NarrativeText", "Title"):
                x_pos = self._get_x_position(point)
                if x_pos > 0:
                    x_positions.append(x_pos)
        
        if not x_positions:
            return "single"
        
        # Cluster X positions to detect columns
        x_positions.sort()
        if len(x_positions) < 5:
            return "single"
        
        # Check for distinct column groupings
        # If we have two distinct groups of X positions, it's multi-column
        median_x = x_positions[len(x_positions) // 2]
        left_column = [x for x in x_positions if x < median_x * 0.9]
        right_column = [x for x in x_positions if x > median_x * 1.1]
        
        if len(left_column) > 5 and len(right_column) > 5:
            return "multi"
        
        return "single"
    
    def _get_column_info(self, point: QdrantPoint, layout_width: float) -> str:
        """Determine which column a point belongs to."""
        x_pos = self._get_x_position(point)
        
        if not x_pos or not layout_width:
            return "left"
        
        # If x_pos is in left half, it's left column
        # If in right half, it's right column
        mid_point = layout_width / 2
        return "left" if x_pos < mid_point else "right"
    
    def compute_stats(
        self,
        sections: List[SectionMetadata],
        points: List[QdrantPoint]
    ) -> List[SectionMetadata]:
        """
        Compute statistics for each section using coordinates.
        Special handling for Title section: collects everything before Abstract.
        
        Args:
            sections: Detected sections (with Title section first)
            points: All document points
            
        Returns:
            Sections with computed statistics
        """
        if not sections:
            return sections
        
        # Detect layout type
        layout_type = self._detect_layout(points)
        layout_width = self._get_layout_width(points)
        
        # Find Abstract section to determine Title section boundaries
        abstract_section = None
        abstract_section_index = -1
        for i, section in enumerate(sections):
            if section.original_name.lower() == "abstract":
                abstract_section = section
                abstract_section_index = i
                break
        
        # Build section boundaries with positions
        section_info = []
        for i, section in enumerate(sections):
            # Special handling for Title section
            if section.original_name == "Title":
                # Title section goes from page 1 to just before Abstract
                if abstract_section:
                    # Find the abstract title point to get its y-position
                    abstract_y_pos = float('inf')
                    for point in points:
                        if (point.category == "Title" and 
                            point.page_content.strip().lower() == "abstract" and
                            point.page_number == abstract_section.page_start):
                            abstract_y_pos = self._get_y_position(point)
                            break
                    
                    section_info.append({
                        'index': i,
                        'section': section,
                        'page_start': 1,
                        'page_end': abstract_section.page_start,
                        'y_start': 0,
                        'y_end': abstract_y_pos,
                        'column': 'left',
                        'is_title_section': True
                    })
                else:
                    # No abstract found, Title section is page 1 only
                    section_info.append({
                        'index': i,
                        'section': section,
                        'page_start': 1,
                        'page_end': 1,
                        'y_start': 0,
                        'y_end': float('inf'),
                        'column': 'left',
                        'is_title_section': True
                    })
                continue
            
            # Regular section handling
            title_point = None
            for point in points:
                if (point.category == "Title" and 
                    point.page_content.strip() == section.original_name and
                    point.page_number == section.page_start):
                    title_point = point
                    break
            
            y_pos = self._get_y_position(title_point) if title_point else 0
            x_pos = self._get_x_position(title_point) if title_point else 0
            column = self._get_column_info(title_point, layout_width) if title_point else "left"
            
            section_info.append({
                'index': i,
                'section': section,
                'page_start': section.page_start,
                'y_start': y_pos,
                'x_start': x_pos,
                'column': column,
                'is_title_section': False
            })
        
        # Count elements per section
        for point in points:
            page = point.page_number
            y_pos = self._get_y_position(point)
            category = point.category
            
            # Find which section this point belongs to
            assigned = False
            for i, info in enumerate(section_info):
                # Special handling for Title section
                if info.get('is_title_section', False):
                    # Check if point is within Title section boundaries
                    if page < info['page_end']:
                        include_point = True
                    elif page == info['page_end']:
                        # Same page as abstract, check y-position
                        if y_pos < info['y_end']:
                            include_point = True
                        else:
                            include_point = False
                    else:
                        include_point = False
                    
                    if include_point:
                        section = info['section']
                        element_id = point.element_id
                        
                        # Update stats
                        if category == "Formula":
                            section.stats.formulas += 1
                            if element_id:
                                section.stats.formula_ids.append(element_id)
                        elif category == "Table":
                            section.stats.tables += 1
                            if element_id:
                                section.stats.table_ids.append(element_id)
                        elif category in ("Image", "FigureCaption"):
                            section.stats.figures += 1
                            if element_id:
                                section.stats.figure_ids.append(element_id)
                        elif category in ("NarrativeText", "CompositeElement", "UncategorizedText"):
                            section.stats.text_blocks += 1
                            if element_id:
                                section.stats.text_block_ids.append(element_id)
                        
                        assigned = True
                        break
                    else:
                        continue
                
                # Regular section handling
                # Get boundaries
                is_in_page_range = page >= info['page_start']
                
                # Check if it's before the next section
                if i + 1 < len(section_info):
                    next_info = section_info[i + 1]
                    if page > next_info['page_start']:
                        continue
                    elif page == next_info['page_start']:
                        # Same page - use Y position
                        if y_pos >= next_info['y_start']:
                            continue
                
                if is_in_page_range:
                    section = info['section']
                    
                    # For multi-column layout, check if point is in same column
                    if layout_type == "multi" and category in ("NarrativeText", "CompositeElement", "UncategorizedText"):
                        point_column = self._get_column_info(point, layout_width)
                        # Include side blocks in the section if they're in adjacent column
                        # This handles text that flows around the section
                    
                    # Update stats based on category and store element IDs
                    element_id = point.element_id
                    
                    if category == "Formula":
                        section.stats.formulas += 1
                        if element_id:
                            section.stats.formula_ids.append(element_id)
                    elif category == "Table":
                        section.stats.tables += 1
                        if element_id:
                            section.stats.table_ids.append(element_id)
                    elif category in ("Image", "FigureCaption"):
                        section.stats.figures += 1
                        if element_id:
                            section.stats.figure_ids.append(element_id)
                    elif category in ("NarrativeText", "CompositeElement", "UncategorizedText"):
                        section.stats.text_blocks += 1
                        if element_id:
                            section.stats.text_block_ids.append(element_id)
                    
                    assigned = True
                    break
        
        return sections
    
    def _get_layout_width(self, points: List[QdrantPoint]) -> float:
        """Get the layout width from coordinates."""
        max_width = 0.0
        
        for point in points:
            if point.coordinates:
                width = point.coordinates.get('layout_width', 0)
                if width > max_width:
                    max_width = width
        
        return max_width
