
### **Current Groq Usage Summary**

**Total API Call Sites: 5 distinct locations** (creating multiple requests per document processed)

---

### **1. 🔴 EXCESSIVE: Reading Guide Generation** 
**Files:** graph.py  
**Calls Per Document:** **1 API call (PRIMARY PURPOSE - AS INTENDED)**

- **Location:** `_run_guide_node()` function (~line 2068)
- **Model:** `llama-3.3-70b-versatile`
- **Usage:** Structured guide generation with validation loop
- **Details:**
  - Uses `with_structured_output()` for JSON parsing
  - **Validation loop:** Makes up to 2 attempts (line says `_GUIDE_VALIDATION_ATTEMPTS = 2`)
  - Each attempt = 1 API call if validation fails
  - **Issue:** If guide validation fails, it retries immediately, potentially causing 429 errors

---

### **2. 🔴 EXCESSIVE: Q&A Answer Generation (Parallel)**
**File:** graph.py  
**Calls Per Document:** **Multiple (1 per question × parallel workers)**

- **Location:** `retrieve_and_qa_node()` → `_process_single_question()` (line 1881)
- **Model:** `llama-3.3-70b-versatile`
- **Usage:** Generating answers for each reading guide question
- **Details:**
  - Uses **ThreadPoolExecutor** with parallel workers (line 1748)
  - Default: `MAX_PARALLEL_QUESTIONS = 3` (parallel simultaneous requests)
  - `MAX_GUIDE_QUESTIONS = 12` total questions per guide
  - **Worst case:** 12 questions × 3 parallel = 36 API calls in a burst
  - Rate limiting fallback exists (line 1935-1948) but only after hitting the limit
  - **Problem:** Questions fire in parallel → rapid rate limit hit

---

### **3. 🟡 MODERATE: Summarization (Alternative Path)**
**File:** graph.py  
**Calls Per Document:** **1 API call (if no query provided)**

- **Location:** `summarizer_node()` (line 2000)
- **Model:** `llama-3.3-70b-versatile`
- **Usage:** Generate structured summary as alternative to Q&A
- **Details:**
  - Called only when: No user query + Unknown category
  - Single call per paper (not parallel)
  - Used as fallback path, not primary

---

### **4. 🔴 **OVER-AGGRESSIVE**: Metadata Extraction (Section Hierarchy & Title/Abstract Detection)**
**File:** metadata_extractor.py  
**Calls Per Document:** **3-4 API calls minimum**

#### **Call 1: Heading Classification (Always)**
- **Location:** `_classify_headings_llm()` (line 580)
- **Triggers:** Every document processing
- **Purpose:** Extract title, abstract, sections, keywords
- **1 API call per document**

#### **Call 2: Title/Abstract Recovery (Conditional)**
- **Location:** `_recover_title_abstract_from_prefix()` (line 748)
- **Triggers:** When initial title/abstract extraction is incomplete
- **Condition:** `if missing_title or missing_abstract`
- **1 API call per document (if fields missing)**

#### **Call 3: Keyword Extraction (Conditional)**
- **Location:** `_extract_keywords_llm()` (line 987)
- **Triggers:** When keywords not in primary extraction
- **1 API call if keywords missing**

#### **Call 4: Paper Properties Inference (Always)**
- **Location:** `_infer_paper_properties()` (line 1132)
- **Purpose:** Classify paper type, difficulty, math-heavy status
- **1 API call per document**

**Metadata Total: 2-4 calls per document** ✋ **(NOT AS INTENDED - Should be fallback only)**

---

### **5. 🟡 MODERATE: Groq Fallback Extractor**
**File:** groq_fallback.py  
**Calls Per Document:** **Conditional (1 call if heuristics fail)**

- **Location:** `extract_missing_fields()` (line 75 in groq_fallback.py)
- **Triggers:** When metadata pipeline can't extract title/abstract via heuristics
- **Model:** `llama-3.3-70b-versatile`
- **Used by:** `MetadataExtractionPipeline._recover_missing_title_abstract()` 
- **Details:**
  - Called from metadata_pipeline.py
  - Fallback mechanism (as intended)
  - 1 call per document if needed

---

### **The Bottleneck Summary**

| Stage | Location | Calls/Doc | Why Excessive? |
|-------|----------|-----------|---|
| **Metadata Title/Abstract** | metadata_extractor.py | 2-3 | Called on every extraction, not fallback-only |
| **Metadata Keywords** | metadata_extractor.py | 1 | Called if not extracted |
| **Metadata Inference** | metadata_extractor.py | 1 | Called on every extraction |
| **Reading Guide** | graph.py:2068 | 1-2 | Validation loop can retry |
| **Q&A Answers** | graph.py:1881 | 12× (parallel) | **Parallel burst of requests** |
| **Summarization** | graph.py:2000 | 1 | Fallback only |
| | | **TOTAL: 18-21 calls/doc** | **Way above intended 1-3** |

---

### **Why You're Getting 429 Errors**

1. **Parallel Q&A requests** (12 questions × 3 workers) create burst spike
2. **Every extraction** calls metadata LLM 4 times (should be fallback-only)
3. **No request throttling** between parallel workers
4. **Groq rate limit:** ~50-100 requests/min on free tier
5. **Your system:** Firing 18-21 requests per document = easily hits limits

---

### **Mismatch with Your Intended Design**

❌ **Expected Use Cases (1-3 calls total):**
- Guide generation: 1 prompt
- Section hierarchy detection: 1 prompt (fallback)
- Title/abstract detection: 1 prompt (fallback)

✅ **Actual Usage (18-21 calls per document):**
- Metadata title/abstract: 2-3 calls (always, not fallback)
- Metadata inference: 1 call (always)
- Metadata keywords: 1 call (always)
- Guide generation: 1-2 calls (validation)
- Q&A per question: 12 parallel calls
- Summary: 1 call (if no query)

---

### **Key Problem Areas to Address**

1. **Metadata extraction is over-eager** → Use heuristics-first, make LLM calls true fallback
2. **Q&A parallel requests too aggressive** → Reduce workers or throttle
3. **No request batching/caching** → Same metadata could be extracted twice
4. **Guide validation retries without backoff** → Add exponential backoffYou've used 99% of your weekly rate limit. Your weekly rate limit will reset on May 11 at 5:45 AM. [Learn More](https://aka.ms/github-copilot-rate-limit-error)