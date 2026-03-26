# Deferred Answer Generation API

This backend flow supports:
- Initial extraction pipeline: generate guide + questions + retrieval payloads only.
- No immediate LLM answer generation.
- One-click one-answer generation via API endpoint.

## Flow

1. Run pipeline on PDF (normal run).
2. Backend stores:
- guide JSON
- per-question rows with `status=pending`
- retrieval payload for each question
3. UI loads guide/questions from API and shows a button per question.
4. Clicking one button calls one endpoint for one question.
5. Backend generates answer for that question only and persists it.

## Endpoints

### 1) Get guide + question statuses

`GET /api/papers/{paper_id}/guide`

Response (shape):

```json
{
  "paper": {"id": 123, "title": "..."},
  "guide": {
    "id": 10,
    "paper_id": 123,
    "guide_json": {"paper_title": "...", "pass1_quick_scan": {"steps": []}},
    "guide_plan_json": {},
    "question_section_pairs_json": []
  },
  "questions": [
    {
      "id": 1001,
      "paper_id": 123,
      "question_text": "What is the main contribution?",
      "scoped_sections_json": ["Abstract", "1 Introduction"],
      "status": "pending",
      "answer_text": null,
      "confidence": null,
      "error_message": null
    }
  ]
}
```

### 2) Get question list only

`GET /api/papers/{paper_id}/questions`

Useful for polling statuses after generation calls.

### 3) Generate one answer (button action)

`POST /api/papers/{paper_id}/questions/{question_id}/generate`

Request body:

```json
{
  "force_regenerate": false
}
```

Response:

```json
{
  "paper": {"id": 123, "title": "..."},
  "question": {
    "id": 1001,
    "status": "completed",
    "question_text": "What is the main contribution?",
    "answer_text": "...",
    "confidence": "HIGH",
    "error_message": null
  }
}
```

## Question Status Lifecycle

- `pending`: ready to be generated
- `running`: generation in progress
- `completed`: answer generated and stored
- `failed`: generation failed; inspect `error_message`

## Suggested UI Behavior

- Render one button per question: `Generate Answer`.
- Disable button while `status=running`.
- Show answer panel only when `status=completed`.
- Show retry button when `status=failed`.
- For refresh, call `GET /api/papers/{paper_id}/questions` after each generate action.

## Notes

- This version is backend-first. Frontend wiring is intentionally deferred.
- Retrieval is prepared during initial pipeline run and reused during generation.
- Use `force_regenerate=true` to overwrite an existing completed answer.
