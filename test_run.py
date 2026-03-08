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
result = pipeline.run('input/attention.pdf')

print()
print('=' * 70)
print('  CATEGORY')
print('=' * 70)
print(f'  Category   : {result.get("category")}')
print(f'  Confidence : {result.get("confidence")}')

print()
print('=' * 70)
print(f'  GUIDE QUESTIONS ({len(result.get("questions_to_answer") or [])})')
print('=' * 70)
for i, q in enumerate(result.get('questions_to_answer') or [], 1):
    print(f'  {i:2}. {q}')

print()
print('=' * 70)
print('  PRIORITY SECTIONS')
print('=' * 70)
for s in result.get('sections_to_read') or []:
    print(f'  • {s}')

print()
print('=' * 70)
per_q = result.get('per_question_results') or []
total_chunks = sum(len(pq.get('chunks', [])) for pq in per_q)
print(f'  PER-QUESTION RESULTS  —  {len(per_q)} questions, {total_chunks} total chunks')
print('=' * 70)
for i, pq in enumerate(per_q, 1):
    q = pq.get('question', '')
    chunks = pq.get('chunks') or []
    sections = pq.get('sections') or []
    print(f'  [{i:2}] Q: {q[:90]}')
    print(f'        sections={sections}  chunks={len(chunks)}')
    for j, c in enumerate(chunks[:3], 1):
        meta = c.get('metadata', {})
        section = meta.get('section_title') or meta.get('section') or '—'
        score = c.get('score', 0.0)
        preview = c.get('content', '')[:160].replace('\n', ' ')
        print(f'          [{j}] score={score:.4f}  section="{section}"')
        print(f'              {preview}')
    if len(chunks) > 3:
        print(f'          ... +{len(chunks) - 3} more chunks')
    print()

errors = result.get('errors') or []
if errors:
    print('Errors:', errors)
