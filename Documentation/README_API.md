# Research Paper Metadata Extractor - API

This project includes a **FastAPI backend** for easy extraction of research paper metadata via a RESTful API.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

Make sure you have a `.env` file with your GROQ API key:

```bash
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Start the FastAPI Backend

```bash
python app.py
# or
./start.sh
```

The API will be available at: `http://localhost:8000`

## 📋 Features

### FastAPI Backend (`app.py`)

- **POST /extract** - Upload a PDF and get structured metadata
- **GET /health** - Check API and configuration status
- **GET /** - API information
- **DELETE /cleanup** - Clean up uploaded files

## 🎯 What Gets Extracted

- **Title** - Paper title
- **Abstract** - Full abstract text
- **Sections** - Detected sections with:
  - Original names from the paper
  - Normalized canonical names
  - Starting page numbers
- **Paper Properties**:
  - Paper type (Survey, System, Theoretical, Empirical, etc.)
  - Difficulty level (easy, medium, hard)
  - Math-heavy indicator

## 📖 API Usage Examples

### Using cURL

```bash
# Health check
curl http://localhost:8000/health

# Extract metadata
curl -X POST "http://localhost:8000/extract" \
  -F "file=@/path/to/your/paper.pdf"
```

### Using Python requests

```python
import requests

# Upload and extract
with open("paper.pdf", "rb") as f:
    files = {"file": ("paper.pdf", f, "application/pdf")}
    response = requests.post("http://localhost:8000/extract", files=files)
    metadata = response.json()
    
print(f"Title: {metadata['title']}")
print(f"Type: {metadata['inference']['paper_type']}")
```

## 🏗️ Architecture

```
┌─────────────────┐
│   Client App    │
│  (Your Code)    │
└────────┬────────┘
         │ HTTP POST /extract
         │
┌────────▼────────┐
│   FastAPI       │  (Port 8000)
│   (Backend)     │
└────────┬────────┘
         │
         ├─► PDF Text Extraction
         ├─► Section Detection
         ├─► Abstract Extraction
         ├─► LLM Inference (via Groq)
         └─► Metadata Assembly
```

## 🔧 Configuration

### FastAPI Settings

Edit [app.py](app.py) to change:
- Port (default: 8000)
- Upload directory (default: `uploads/`)
- CORS settings
- Timeout values

### Streamlit Settings

Edit [streamlit_app.py](streamlit_app.py) to change:
- API URL (default: http://localhost:8000)
- Page layout and styling
- Display options

## 🐛 Troubleshooting

### "Cannot connect to API"
- Make sure the FastAPI server is running: `python app.py`
- Check that port 8000 is not in use by another application

### "GROQ_API_KEY not found"
- Ensure you have a `.env` file in the project root
- Add your Groq API key: `GROQ_API_KEY=your_key_here`

### "Extraction failed"
- Check that the PDF is a valid research paper
- Some PDFs with complex formatting may fail
- Check the FastAPI logs for detailed error messages

## 📝 Development

### Running in Production

For production deployment:

1. **FastAPI with Gunicorn**:
```bash
gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

2. **Update CORS settings** in [app.py](app.py) to specify allowed origins

### Running with Docker (Optional)

Create a `Dockerfile` for the FastAPI backend and another for Streamlit, or use docker-compose to orchestrate both services.

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Streamlit Documentation](https://docs.streato containerize the application.

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com
Feel free to open issues or submit pull requests for improvements!

## 📄 License

See the main project README for license information.
