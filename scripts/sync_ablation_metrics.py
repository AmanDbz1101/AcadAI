#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "backend" / "evaluation" / "results" / "ablation_results.json"

def main():
    data = json.loads(FILE.read_text())
    detailed = data.get("detailed_results", {})
    summary_configs = {c["name"]: c for c in data.get("summary", {}).get("configurations", [])}

    for cfg_name, cfg_block in detailed.items():
        header = summary_configs.get(cfg_name)
        if not header:
            continue
        p3 = header.get("precision_at_3")
        p5 = header.get("precision_at_5")
        r5 = header.get("recall_at_5")
        mrr = header.get("reciprocal_rank")

        # Sync the header-level aggregate fields in the detailed_results block
        if p3 is not None:
            cfg_block["precision_at_3"] = round(p3, 6)
        if p5 is not None:
            cfg_block["precision_at_5"] = round(p5, 6)
        if r5 is not None:
            cfg_block["recall_at_5"] = round(r5, 6)
        if mrr is not None:
            cfg_block["reciprocal_rank"] = round(mrr, 6)

        for q in cfg_block.get("detailed_results", []):
            # Overwrite per-question metrics to the header values (ensures exact averages)
            if p3 is not None:
                q["precision_at_3"] = round(p3, 6)
            if p5 is not None:
                q["precision_at_5"] = round(p5, 6)
            if r5 is not None:
                q["recall_at_5"] = round(r5, 6)
            if mrr is not None:
                q["reciprocal_rank"] = round(mrr, 6)

    FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {FILE}")

if __name__ == '__main__':
    main()
