# 🚀 Quick Start Guide

Get up and running with the Research Paper Metadata Extractor API in 3 easy steps!

## Prerequisites

- Python 3.8+
- A Groq API key ([Get one here](https://console.groq.com))

## Step 1: Setup Environment

```bash
# Clone or navigate to the project
cd "Research Paper Assistant"

# Create virtual environment (if not already created)
python -m venv env_research

# Activate it
source env_research/bin/activate  # On Linux/Mac
# or
env_research\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Configure API Key

Create a `.env` file in the project root:

```bash
GROQ_API_KEY=your_groq_api_key_here
```

## Step 3: Launch the Application

```bash
# Option A: Use the start script
./start.sh

# Option B: Start manually
python app.py
```

## 📱 Access the API

Once running, access:

- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## 🎯 Using the API

Use cURL, Python requests, or any HTTP client:

```bash
# Health check
curl http://localhost:8000/health

# Extract metadata
curl -X POST "http://localhost:8000/extract" \
  -F "file=@/path/to/your/paper.pdf"
```

Or with Python:

```python
import requests

with open("paper.pdf", "rb") as f:
    files = {"file": ("paper.pdf", f, "application/pdf")}
    response = requests.post("http://localhost:8000/extract", files=files)
    metadata = response.json()

print(f"Title: {metadata['title']}")
print(f"Type: {metadata['inference']['paper_type']}")
```

## 📊 What You'll Get

For each paper, the system extracts:

- ✅ **Title** - Paper title
- ✅ **Abstract** - Full abstract text
- ✅ **Sections** - All detected sections with normalized names
- ✅ **Paper Type** - Survey, System, Theoretical, Empirical, etc.
- ✅ **Difficulty Level** - Easy, Medium, or Hard
- ✅ **Math-Heavy Indicator** - Whether the paper is mathematically intensive

## 🐛 Troubleshooting

### Port Already in Use

If you see an error about ports 8000 or 8501 being in use:

```bash
# Find and kill the process
lsof -ti:8000 | xargs kill -9  # Kill process on port 8000
lsof -ti:8501 | xargs kill -9  # Kill process on port 8501
```

### GROQ API Key Issues

Make sure your `.env` file is in the project root and contains:
```
GROQ_API_KEY=gsk_...
```

You can verify it's loaded by visiting: http://localhost:8000/health

### PDF Upload Fails

- Ensure the file is a valid PDF
- Check that it's a research paper (the system is optimized for academic papers)
- Try a different PDF if the extraction fails

## 📚 Example Papers

Try these types of papers:

- ✅ Conference papers (ACL, NeurIPS, CVPR, etc.)
- ✅ Journal articles
- ✅ ArXiv preprints
- ✅ Technical reports

## 🔗 Need More Help?

- Read the [full API documentation](README_API.md)
- Check the [implementation details](IMPLEMENTATION_SUMMARY.md)
- Review the [architecture](ARCHITECTURE.md)

## 🎉 That's It!

You're all set! Upload your first research paper and see the magic happen! ✨
