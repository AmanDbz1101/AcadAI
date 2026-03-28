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
        "document_id": "30c88170-fd15-5486-bf70-bbab16747183",      # fill in your actual Qdrant document_id
        "title": "Another generalization of Hadamard test: Optimal sample complexities for learning functions on the unitary group"             # fill in paper title
    },
    {
        "paper_id": "paper_applied",
        "paper_type": "Applied",
        "document_id": "bd077a96-5a38-5281-993e-10cf869afcde",
        "title": "Attention Is All You Need"
    },
    {
        "paper_id": "paper_survey",
        "paper_type": "Survey",
        "document_id": "e0960904-0d88-57cb-a52e-f60e01df2c7b",
        "title": "Pre-trained Models for Natural Language Processing: A Survey"
    },
    {
        "paper_id": "paper_memgpt",
        "paper_type": "Applied",
        "document_id": "a85211d3-4ad5-52d0-9a49-7d351a58fe31",
        "title": "MemGPT: Towards LLMs as Operating Systems"
    }
]
