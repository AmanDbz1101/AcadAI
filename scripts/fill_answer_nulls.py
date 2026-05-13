#!/usr/bin/env python3
"""
Fill any remaining null `section_title` in new_answer_results.json by keyword detection on the question.
Also ensure `section_id` uses the pattern {document_id}_section_{number} where possible.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANS_PATH = ROOT / 'backend' / 'evaluation' / 'results' / 'new_answer_results.json'

def detect_section_from_text(text):
    if not text:
        return None
    t = text.lower()
    if 'introduction' in t:
        return '1 Introduction'
    if 'ordinary' in t or 'pronoun' in t or 'pcr' in t:
        return '2 Ordinary PCR'
    if 'experiments' in t or 'results' in t or 'experiment' in t:
        return '3 Experiments'
    if 'analysis' in t:
        return '4 Analysis'
    if 'related' in t:
        return '5 Related Works'
    if 'conclusion' in t:
        return '6 Conclusion'
    if 'hard pcr' in t or 'wsc' in t:
        return '3 Hard PCR'
    if 'other pcr' in t or 'other' in t:
        return '4 Other PCR Tasks'
    return '1 Introduction'

def section_number_from_title(title):
    parts = title.split()
    try:
        return int(parts[0])
    except Exception:
        return 0

def main():
    ans = json.loads(ANS_PATH.read_text())
    updated = 0
    for sample in ans.get('per_sample_results', []):
        if sample.get('section_title') is None:
            detected = detect_section_from_text(sample.get('question') or '')
            sample['section_title'] = detected
            num = section_number_from_title(detected)
            # derive docid from existing section_id if possible
            sid_old = sample.get('section_id') or ''
            docid = ''
            if isinstance(sid_old, str) and '_section_' in sid_old:
                docid = sid_old.split('_section_')[0]
            sample['section_id'] = f"{docid}_section_{num}" if docid else f"_section_{num}"
            updated += 1
    ANS_PATH.write_text(json.dumps(ans, indent=2, ensure_ascii=False))
    print(f"Filled {updated} null section_title entries in {ANS_PATH}")

if __name__ == '__main__':
    main()
