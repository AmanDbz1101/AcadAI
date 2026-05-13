#!/usr/bin/env python3
"""
Fill missing or null section_title values in QA and Answer files using keywords.
Sets section_title to a canonical form and updates section_id accordingly.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA_PATH = ROOT / 'backend' / 'evaluation' / 'dataset' / 'new_qa_pairs.json'
ANS_PATH = ROOT / 'backend' / 'evaluation' / 'results' / 'new_answer_results.json'

def detect_section_from_text(text):
    if not text:
        return None
    t = text.lower()
    if 'introduction' in t:
        return '1 Introduction'
    if 'ordinary' in t or 'pronoun' in t or 'pcr' in t:
        return '2 Ordinary PCR'
    if 'experiments' in t or 'results' in t or 'experiment' in t or 'gating' in t or 'gated' in t:
        return '3 Experiments'
    if 'analysis' in t or 'analy' in t:
        return '4 Analysis'
    if 'related' in t or 'related works' in t:
        return '5 Related Works'
    if 'conclusion' in t:
        return '6 Conclusion'
    if 'hard pcr' in t or 'wsc' in t:
        return '3 Hard PCR'
    if 'other pcr' in t or 'other' in t:
        return '4 Other PCR Tasks'
    return None

def section_number_from_title(title):
    if not title:
        return 0
    parts = title.split()
    try:
        return int(parts[0])
    except Exception:
        return 0

def normalize_question(q):
    if q is None:
        return ''
    return ' '.join(q.split()).strip()

def main():
    qa = json.loads(QA_PATH.read_text())
    updated_qa = 0
    for entry in qa:
        st = entry.get('section_title')
        if not st or not isinstance(st, str) or st.strip() == '' or not st[0].isdigit():
            # try detect from section_title itself
            detected = detect_section_from_text(entry.get('section_title') or '')
            if not detected:
                # try detect from question text
                detected = detect_section_from_text(entry.get('question') or '')
            if detected:
                entry['section_title'] = detected
                num = section_number_from_title(detected)
                docid = entry.get('document_id','')
                entry['section_id'] = f"{docid}_section_{num}"
                updated_qa += 1
            else:
                # fallback keep and set section_id number 0
                docid = entry.get('document_id','')
                entry['section_id'] = f"{docid}_section_0"
    QA_PATH.write_text(json.dumps(qa, indent=2, ensure_ascii=False))
    print(f"Updated QA entries: {updated_qa}")

    ans = json.loads(ANS_PATH.read_text())
    updated_ans = 0
    # Build mapping from normalized question to section data
    qmap = {normalize_question(e['question']): (e['section_id'], e.get('section_title')) for e in qa}
    for sample in ans.get('per_sample_results', []):
        nq = normalize_question(sample.get('question'))
        if nq in qmap:
            sid, stitle = qmap[nq]
            if not sample.get('section_title') or not isinstance(sample.get('section_title'), str) or not sample.get('section_title').strip():
                sample['section_title'] = stitle
                sample['section_id'] = sid
                updated_ans += 1
        else:
            # try detecting from question text
            detected = detect_section_from_text(sample.get('question') or '')
            if detected:
                num = section_number_from_title(detected)
                # prefer existing document id prefix if present
                docid = ''
                sid_old = sample.get('section_id') or ''
                if isinstance(sid_old, str) and '_section_' in sid_old:
                    docid = sid_old.split('_section_')[0]
                sample['section_title'] = detected
                sample['section_id'] = f"{docid}_section_{num}" if docid else f"_section_{num}"
                updated_ans += 1
    ANS_PATH.write_text(json.dumps(ans, indent=2, ensure_ascii=False))
    print(f"Updated Answer samples: {updated_ans}")

if __name__ == '__main__':
    main()
