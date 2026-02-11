# Testing Guide

## Overview
This directory contains comprehensive unit and integration tests for the PDF Ingestion module of the Research Paper Assistant.

## Test Structure

```
tests/
├── conftest.py                    # Shared fixtures and configuration
├── test_validation.py             # Tests for PDF validation
├── test_pdf_loader.py             # Tests for PDF loading and extraction
├── test_ingestion_pipeline.py     # Tests for pipeline orchestration
└── test_integration.py            # End-to-end integration tests
```

## Setup

### 1. Install Dependencies

```bash
# Install backend requirements
pip install -r backend/requirements.txt

# Install testing requirements
pip install -r tests/requirements.txt
```

### 2. Environment Setup

Ensure you're in the project root directory:
```bash
cd /path/to/Research\ Paper\ Assistant
```

## Running Tests

### Run All Tests
```bash
pytest
```

### Run Specific Test File
```bash
pytest tests/test_validation.py
pytest tests/test_pdf_loader.py
pytest tests/test_ingestion_pipeline.py
pytest tests/test_integration.py
```

### Run Specific Test Class
```bash
pytest tests/test_validation.py::TestPDFValidator
```

### Run Specific Test Function
```bash
pytest tests/test_validation.py::TestPDFValidator::test_validate_valid_pdf
```

### Run with Coverage Report
```bash
pytest --cov=backend --cov-report=html
```

Coverage report will be available at `htmlcov/index.html`

### Run Tests in Parallel
```bash
pytest -n auto
```

### Run Tests with Verbose Output
```bash
pytest -v
```

### Run Only Fast Tests (exclude slow tests)
```bash
pytest -m "not slow"
```

### Run Tests by Category
```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Validation tests
pytest -m validation

# Pipeline tests
pytest -m pipeline
```

## Test Categories

### 1. Validation Tests (`test_validation.py`)
- PDF file validation
- File format checking
- Size constraints
- Page count validation
- Encryption detection
- Hash calculation

### 2. PDF Loader Tests (`test_pdf_loader.py`)
- Text extraction
- Page processing
- Word/character counting
- Readability detection
- Multi-page handling

### 3. Pipeline Tests (`test_ingestion_pipeline.py`)
- Pipeline orchestration
- Component integration
- Error handling
- Batch processing
- Document model creation
- Deduplication logic

### 4. Integration Tests (`test_integration.py`)
- End-to-end workflows
- Service layer integration
- Performance testing
- Robustness testing
- Data consistency validation

## Test Fixtures

The `conftest.py` file provides shared fixtures:

- `sample_pdf_path`: A valid PDF with text content
- `empty_pdf_path`: An empty PDF (no pages)
- `scanned_pdf_path`: A simulated scanned PDF (low text density)
- `encrypted_pdf_path`: An encrypted PDF file
- `large_pdf_path`: A multi-page PDF (5 pages)
- `corrupted_pdf_path`: A corrupted/invalid PDF
- `non_pdf_path`: A non-PDF file

## Coverage Goals

Target coverage metrics:
- **Overall**: 85%+
- **Critical paths**: 95%+
- **Validation module**: 90%+
- **Pipeline module**: 90%+

View current coverage:
```bash
pytest --cov=backend --cov-report=term-missing
```

## Writing New Tests

### Test Naming Convention
- Test files: `test_<module_name>.py`
- Test classes: `Test<ComponentName>`
- Test functions: `test_<what_is_being_tested>`

### Example Test Structure
```python
def test_validate_valid_pdf(sample_pdf_path):
    """Test validation of a valid PDF file."""
    validator = PDFValidator()
    result = validator.validate(sample_pdf_path)
    
    assert result.is_valid is True
    assert result.page_count > 0
```

### Best Practices
1. **One assertion per test** (when possible)
2. **Use descriptive test names**
3. **Include docstrings** explaining what is tested
4. **Use fixtures** for common setup
5. **Test edge cases** and error conditions
6. **Keep tests independent** (no test should depend on another)

## Continuous Integration

These tests can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Run Tests
  run: |
    pip install -r backend/requirements.txt
    pip install -r tests/requirements.txt
    pytest --cov=backend --cov-report=xml

- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

## Troubleshooting

### Tests Fail with Import Errors
Ensure the project root is in your Python path:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### PyMuPDF Installation Issues
If PyMuPDF fails to install:
```bash
pip install --upgrade pymupdf
```

### Fixture Not Found
Ensure `conftest.py` is in the `tests/` directory and pytest can discover it.

## Performance Testing

Run performance benchmarks:
```bash
pytest tests/test_integration.py::TestPerformance -v
```

## Debugging Tests

Run with debugger:
```bash
pytest --pdb
```

Stop at first failure:
```bash
pytest -x
```

Show local variables on failure:
```bash
pytest -l
```

## Contact

For questions about testing or to report issues, please refer to the project documentation or open an issue.
