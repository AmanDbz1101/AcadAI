import json
import os
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import List, Literal
from dotenv import load_dotenv

load_dotenv()

class ReadingStep(BaseModel):
    step_id: str = Field(..., description="Step ID: FP-1, SP-2, TP-3")
    name: str = Field(..., description="Step name (3-7 words)")
    target_sections: List[str] = Field(..., description="Sections to focus on")
    focus_type: Literal["overview", "figures_tables", "formulas", "methodology", "results", "deep_analysis"] = Field(
        ..., description="Type of reading focus"
    )

class ReadingPass(BaseModel):
    pass_id: Literal["first_pass", "second_pass", "third_pass"]
    estimated_time_minutes: int
    steps: List[ReadingStep]

class StepsGeneratorOutput(BaseModel):
    paper_id: str
    passes: List[ReadingPass]

def generate_minimal_guide_llm(metadata_path, output_path):
    with open(metadata_path, 'r') as f:
        metadata = json.load(f)
    paper_title = metadata['paper_title']
    paper_id = metadata.get('paper_id', paper_title.replace(' ', '_'))
    global_stats = metadata['global_stats']
    inference = metadata['inference']
    sections_data = []
    for section in metadata['sections']:
        section_name = section['original_name']
        stats = section['stats']
        counts = [
            stats['figures'],
            stats['tables'],
            stats['formulas'],
            stats['text_blocks']
        ]
        sections_data.append([section_name, counts])
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Generate minimal 3-pass reading plan. Output only essentials for next agent.\n\n**Pass 1 (5-10min)**: Overview - title, abstract, intro, headings, conclusion, skim figures/tables\n**Pass 2 (45-90min)**: Thorough reading - grasp main ideas, note figures/tables\n**Pass 3 (3-5hrs)**: Deep dive - analyze formulas, tables, figures in detail\n\n**focus_type options**: overview, figures_tables, formulas, methodology, results, deep_analysis\n\nKeep step names brief. Use actual section names. Prioritize sections with high figure/table/formula counts."""),
        ("human", """Paper: {title}\n\nStructure: {sections_data}\n\nStats: {total_pages}p, {total_sections}sec, {total_figures}fig, {total_tables}tbl, {total_formulas}formula | {paper_type}, {difficulty}, math-heavy: {math_heavy}\n\nGenerate: Pass 1 (3-4 steps), Pass 2 (4-6 steps), Pass 3 (3-5 steps).""")
    ])
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.1
    )
    structured_llm = llm.with_structured_output(StepsGeneratorOutput)
    chain = prompt | structured_llm
    result = chain.invoke({
        "title": paper_title,
        "sections_data": "\n".join([f"{s[0]}: {s[1]}" for s in sections_data]),
        "total_pages": global_stats['total_pages'],
        "total_sections": global_stats['total_sections'],
        "total_figures": global_stats['total_figures'],
        "total_tables": global_stats['total_tables'],
        "total_formulas": global_stats['total_formulas'],
        "paper_type": inference['paper_type'],
        "difficulty": inference['difficulty'],
        "math_heavy": inference['math_heavy']
    })
    output_json = result.model_dump()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(output_json, f, indent=2)
    return output_json

def load_minimal_guide(output_path):
    with open(output_path, 'r') as f:
        return json.load(f)
