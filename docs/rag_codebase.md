multiagent-rag/
│
├── app/
│   ├── main.py
│   ├── config.py
│   └── settings.yaml
│
├── agents/
│   ├── router_agent.py
│   ├── retriever_agent.py
│   ├── reasoning_agent.py
│   ├── critic_agent.py
│   └── query_agent.py
│
├── graph/
│   ├── graph_builder.py
│   ├── state.py
│   └── nodes.py
│
├── rag/
│   ├── document_loader.py
│   ├── text_splitter.py
│   ├── embeddings.py
│   ├── vector_store.py
│   └── retriever.py
│
├── tools/
│   ├── search_tool.py
│   ├── calculator_tool.py
│   └── database_tool.py
│
├── prompts/
│   ├── router_prompt.txt
│   ├── reasoning_prompt.txt
│   ├── critique_prompt.txt
│   └── retrieval_prompt.txt
│
├── memory/
│   ├── conversation_memory.py
│   └── agent_state_memory.py
│
├── models/
│   ├── llm_loader.py
│   └── embedding_loader.py
│
├── evaluation/
│   ├── rag_metrics.py
│   └── test_queries.json
│
├── api/
│   ├── routes.py
│   └── schemas.py
│
├── utils/
│   ├── logger.py
│   ├── helpers.py
│   └── constants.py
│
├── data/
│   ├── raw_docs/
│   └── processed_docs/
│
├── vector_db/
│   └── chroma_db/
│
├── tests/
│   ├── test_agents.py
│   ├── test_retrieval.py
│   └── test_graph.py
│
├── requirements.txt
├── README.md
└── .env