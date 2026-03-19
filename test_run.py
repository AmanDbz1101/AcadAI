import os, sys

with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

sys.path.insert(0, 'backend')
sys.path.insert(0, '.')

from backend.run import PaperAnalysisPipeline

pipeline = PaperAnalysisPipeline()
result = pipeline.run('input/survey.pdf')

print()
print('=' * 70)
print('  CATEGORY')
print('=' * 70)
print(f'  Category   : {result.get("category")}')
print(f'  Confidence : {result.get("confidence")}')

# ── Reading Guide ──────────────────────────────────────────────────────────
reading_guide = result.get('reading_guide') or {}
passes = reading_guide.get('passes') or []
print()
print('=' * 70)
print(f'  READING GUIDE  —  {len(passes)} pass(es)')
print('=' * 70)
for p in passes:
    print(f'\n  Pass {p.get("pass_number", "?")} — {p.get("pass_name", "")}')
    print(f'  Goal: {p.get("goal", "")}')
    for step in p.get('steps') or []:
        print(f'    Step {step.get("step_id", "?")} · {step.get("name", "")}')
        print(f'      Objective : {step.get("reading_objective", "")}')
        print(f'      Sections  : {step.get("target_sections", [])}')

# ── All guide questions ────────────────────────────────────────────────────
print()
print('=' * 70)
print(f'  ALL GUIDE QUESTIONS ({len(result.get("questions_to_answer") or [])})')
print('=' * 70)
for i, q in enumerate(result.get('questions_to_answer') or [], 1):
    print(f'  {i:2}. {q}')

# ── Q&A Results (first 4) ──────────────────────────────────────────────────
qa_results = result.get('qa_results') or []
print()
print('=' * 70)
print(f'  Q&A RESULTS  —  {len(qa_results)} question(s) answered')
print('=' * 70)
for i, qa in enumerate(qa_results, 1):
    print(f'\n  ── Question {i} ──────────────────────────────────────────────')
    print(f'  Q: {qa.get("question", "")}')
    print(f'  Confidence: {qa.get("confidence", "?")}')
    print()
    answer = qa.get("answer", "")
    for line in answer.splitlines():
        print(f'  {line}')


errors = result.get('errors') or []
if errors:
    print('Errors:', errors)
