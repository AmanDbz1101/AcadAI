import json
import os
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import List, Literal
from dotenv import load_dotenv

load_dotenv()

class ReadingStep(BaseModel):
    step_id: str = Field(..., description="Unique step identifier, e.g., FP-1, SP-2, TP-3")
    name: str = Field(..., description="Brief descriptive name for this step (3-7 words)")
    target_sections: List[str] = Field(..., description="Paper sections or subsections this step applies to")
    instruction: str = Field(..., description="Action the reader should perform at this step")
    reading_objective: str = Field(..., description="What the reader should aim to achieve conceptually")
    reader_checkpoint: str = Field(..., description="Observable outcome indicating the step was successfully completed")

class ReadingPass(BaseModel):
    pass_id: Literal["first_pass", "second_pass", "third_pass"]
    pass_name: str
    objective: str
    estimated_time_minutes: int
    steps: List[ReadingStep]

class StepsGeneratorOutput(BaseModel):
    paper_id: str
    reading_strategy: Literal["three-pass"] = "three-pass"
    passes: List[ReadingPass]

def generate_full_guide_llm(metadata_path, output_path):
    with open(metadata_path, 'r') as f:
        metadata = json.load(f)
    paper_title = metadata['paper_title']
    abstract = metadata['abstract']
    global_stats = metadata['global_stats']
    inference = metadata['inference']
    paper_id = metadata.get('paper_id', paper_title.replace(' ', '_'))
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
        ("system", """You are an expert research reading strategist.\n\nGenerate a structured reading plan using the three-pass methodology:\n\n**First Pass (5-10 min)**: Quick overview - read title, abstract, introduction, section headings, conclusion. **IMPORTANT: Include a dedicated step to skim ALL figures, tables, and their captions** to identify key visual results.\n\n**Second Pass (~1 hour)**: Read with care but skip deep details. Grasp main thrust. **Pay attention to figures and tables** while reading each section. Note which visuals support key claims. Mark relevant references.\n\n**Third Pass (4-5 hours)**: Deep dive - virtually re-implement the work. **CRITICAL: Include a dedicated step to thoroughly examine ALL formulas, tables, and figures.** Analyze each visual element in detail. Challenge assumptions and verify mathematical derivations.\n\n**Output Requirements:**\n- name: Brief, descriptive step name (3-7 words, e.g., \"Overview of Paper Structure\", \"Examine Experimental Results\", \"Analyze Mathematical Formulations\")\n- target_sections: Actual section names from the paper structure provided. For steps focusing on figures/tables, list sections that contain them.\n- instruction: Specific, actionable reading task. **Create explicit steps for examining figures, tables, and formulas** (e.g., \"Skim all figures, tables, and captions\", \"Examine all tables and figures to evaluate experimental evidence\")\n- reading_objective: Clear conceptual goal (e.g., \"Identify key visual results\", \"Assess empirical support through visual evidence\")\n- reader_checkpoint: How to verify completion (e.g., \"Can list main findings shown in figures\")\n\n**Pass Details:**\n- pass_id: \"first_pass\", \"second_pass\", \"third_pass\"\n- pass_name: E.g., \"First Pass - Overview\"\n- objective: Overall goal for this pass\n- estimated_time_minutes: Realistic estimate (First: 5-10, Second: 45-90, Third: 180-300)\n\n**CRITICAL**: The paper structure includes counts of [figures, tables, formulas, text_blocks] per section. Use this information to prioritize sections with visual content. Always include dedicated steps for examining visual elements."""),
        ("human", """Generate a three-pass reading plan for this paper:\n\n**Title:** {title}\n\n**Abstract:** {abstract}\n\n**Paper Structure (with [figures, tables, formulas, text_blocks] counts):**\n{sections_data}\n\n**Statistics:** {total_pages} pages, {total_sections} sections, **{total_figures} figures, {total_tables} tables**, {total_formulas} formulas\n\n**Classification:** {paper_type} | Difficulty: {difficulty} | Math-heavy: {math_heavy}\n\n---\n\nCreate a structured plan with:\n- **First Pass** (5-10 min): 3-4 steps for quick overview. **MUST include one step dedicated to skimming all figures and tables.**\n- **Second Pass** (45-90 min): 4-6 steps for thorough reading without deep details. Reference figures/tables when reading sections that contain them.\n- **Third Pass** (3-5 hours): 3-5 steps for complete understanding and verification. **MUST include dedicated steps for examining all formulas, tables, and figures in detail.**\n\nUse actual section names from the structure above. Prioritize sections with high figure/table counts. Be specific and actionable.""")
    ])
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.1
    )
    structured_llm = llm.with_structured_output(StepsGeneratorOutput)
    chain = prompt | structured_llm
    result = chain.invoke({
        "title": paper_title,
        "abstract": abstract,
        "sections_data": "\n".join([f"{s[0]}: {s[1]}" for s in sections_data]),
        "total_pages": global_stats['total_pages'],
        "total_sections": global_stats['total_sections'],
        "total_figures": global_stats['total_figures'],
        "total_tables": global_stats['total_tables'],
        "total_formulas": global_stats['total_formulas'],
        "total_text_blocks": global_stats['total_text_blocks'],
        "paper_type": inference['paper_type'],
        "difficulty": inference['difficulty'],
        "math_heavy": inference['math_heavy']
    })
    output_json = result.model_dump()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(output_json, f, indent=2)
    return output_json

def load_full_guide(output_path):
    with open(output_path, 'r') as f:
        return json.load(f)
