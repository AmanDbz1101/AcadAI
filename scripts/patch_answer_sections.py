#!/usr/bin/env python3
"""
Patch `new_answer_results.json` using normalized questions from `new_qa_pairs.json`.
This uses whitespace-normalized matching to reliably map section_id and section_title.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA_PATH = ROOT / 'backend' / 'evaluation' / 'dataset' / 'new_qa_pairs.json'
ANS_PATH = ROOT / 'backend' / 'evaluation' / 'results' / 'new_answer_results.json'

def normalize_text(s):
    if s is None:
        return ''
    return ' '.join(s.split()).strip()

qa = json.loads(QA_PATH.read_text())
ans = json.loads(ANS_PATH.read_text())

qmap = {normalize_text(e['question']): (e['section_id'], e.get('section_title')) for e in qa}

updated = 0
for sample in ans.get('per_sample_results', []):
    nq = normalize_text(sample.get('question'))
    if nq in qmap:
        sid, stitle = qmap[nq]
        sample['section_id'] = sid
        sample['section_title'] = stitle
        updated += 1

ANS_PATH.write_text(json.dumps(ans, indent=2, ensure_ascii=False))
print(f"Patched {ANS_PATH}: updated {updated} samples")
