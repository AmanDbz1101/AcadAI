#!/bin/bash

# Cleanup script to remove old files after reorganization

cd "/home/aman/storage/Python/Projects/Research Paper Assistant/backend"

echo "Deleting old directories and files..."

# Delete old app directories
rm -rf app/ingestion
rm -rf app/processing
echo "✓ Deleted app/ingestion/ and app/processing/"

# Delete old pipeline files
rm -f pipelines/chunking_pipeline.py
rm -f pipelines/guide_generation_pipeline.py
rm -f pipelines/ingest_pipeline.py
rm -f pipelines/metadata_pipeline.py
rm -f pipelines/section_hierarchy_pipeline.py
rm -f pipelines/SECTION_HIERARCHY_QUICKSTART.md
rm -f pipelines/SECTION_HIERARCHY_README.md
echo "✓ Deleted old pipeline files"

# Delete old service files
rm -f services/embedding_service.py
rm -f services/ingestion_service.py
rm -f services/processing_service.py
echo "✓ Deleted old service files"

# Delete old model files
rm -f models/chunking.py
rm -f models/document.py
rm -f models/guide.py
rm -f models/metadata.py
rm -f models/section_hierarchy.py
echo "✓ Deleted old model files"

# Delete old config file
rm -f config/settings.py
echo "✓ Deleted old config/settings.py"

# Delete old API route files
rm -f api/routes/upload.py
rm -f api/routes/processing.py
echo "✓ Deleted old API route files"

# Delete old example files
rm -f examples/ingestion_usage.py
rm -f examples/example_section_hierarchy.py
echo "✓ Deleted old example files"

echo ""
echo "Cleanup complete! Old files removed."
echo "New structure is in extraction/, rag/, and shared/ directories."
