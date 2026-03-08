research-assistant/
│
├── backend/
│   ├── app/                # Application logic (core system)
│   ├── api/                # API layer (FastAPI / Flask)
│   ├── pipelines/          # Orchestrated workflows
│   ├── services/           # Reusable domain services
│   ├── models/             # Data schemas (Pydantic / dataclasses)
│   ├── storage/            # Vector DB, file system, cache
│   ├── config/             # Configuration & constants
│   ├── utils/              # Shared utilities
│   └── main.py             # App entrypoint
│
├── playground/            # Research experiments & ablations
│
├── docs/                   # Documentation (architecture, plans)
│
├── scripts/                # One-off scripts (ingest, reindex, eval)
│
├── tests/                  # Unit + integration tests
│
├── data/                   # Local data (gitignored)
│
├── README.md
├── pyproject.toml / requirements.txt
└── .gitignore



backend/app/
├── ingestion/
│   ├── pdf_loader.py
│   ├── ocr.py
│   └── validation.py
│
├── processing/
│   ├── text_extraction.py
│   ├── layout_analysis.py
│   ├── metadata_extraction.py
│   └── figure_table_extraction.py
│
├── structure/
│   ├── section_detector.py
│   ├── hierarchy_builder.py
│   └── confidence.py
│
├── chunking/
│   ├── chunker.py
│   └── chunk_metadata.py
│
├── embeddings/
│   ├── dense.py
│   ├── sparse.py
│   └── embedder_factory.py
│
├── indexing/
│   ├── dense_index.py
│   ├── sparse_index.py
│   └── hybrid_index.py
│
├── guides/
│   ├── outline_generator.py
│   ├── three_pass_logic.py
│   └── guide_models.py
│
├── queries/
│   ├── query_generator.py
│   ├── intent_classifier.py
│   └── query_models.py
│
├── retrieval/
│   ├── hybrid_retriever.py
│   ├── fusion.py
│   └── retrieval_diagnostics.py
│
├── answering/
│   ├── prompt_builder.py
│   ├── answer_generator.py
│   ├── confidence_estimator.py
│   └── citation_tracker.py
│
├── feedback/
│   ├── loop_controller.py
│   └── failure_analysis.py
│
└── orchestration/
    ├── paper_pipeline.py
    └── step_runner.py



backend/pipelines/
├── ingest_pipeline.py
├── index_pipeline.py
├── guide_pipeline.py
├── query_pipeline.py
└── full_paper_pipeline.py


backend/services/
├── llm_service.py
├── embedding_service.py
├── token_budget_manager.py
├── cache_service.py
└── logging_service.py


backend/models/
├── document.py
├── chunk.py
├── section.py
├── query.py
├── retrieval.py
├── answer.py
└── evaluation.py


backend/api/
├── routes/
│   ├── upload.py
│   ├── query.py
│   └── status.py
│
└── app.py


docs/
├── architecture/
│   ├── system_overview.md
│   ├── data_flow.md
│   └── failure_modes.md
│
├── design/
│   ├── chunking_strategy.md
│   ├── retrieval_strategy.md
│   └── confidence_model.md
│
├── experiments/
│   ├── evaluation_plan.md
│   └── ablation_studies.md
│
└── roadmap.md


playground/
├── chunking_ablation/
├── retrieval_comparison/
├── token_cost_analysis/
└── notebooks/


tests/
├── unit/
│   ├── test_chunking.py
│   ├── test_section_detection.py
│   └── test_retrieval.py
│
└── integration/
    ├── test_full_pipeline.py
    └── test_feedback_loop.py


