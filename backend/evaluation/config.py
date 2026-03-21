EVAL_DATASET_PATH = "evaluation/dataset/qa_pairs.json"
RESULTS_DIR = "evaluation/results/"
TOP_K = 5
TOP_N = 5
MIN_RELEVANCE_THRESHOLD = 0.35
JUDGE_MODEL = "llama-3.3-70b-versatile"
PAPERS = [
    {
        "paper_id": "paper_theory",
        "paper_type": "Theory",
        "document_id": "",      # fill in your actual Qdrant document_id
        "title": ""             # fill in paper title
    },
    {
        "paper_id": "paper_applied",
        "paper_type": "Applied",
        "document_id": "",
        "title": ""
    },
    {
        "paper_id": "paper_survey",
        "paper_type": "Survey",
        "document_id": "",
        "title": ""
    }
]
