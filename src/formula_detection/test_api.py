"""
Test script for the Formula Detection & Analysis API
"""
import requests
import json
from pathlib import Path

# API base URL
BASE_URL = "http://localhost:8000"

def test_health_check():
    """Test the health check endpoint"""
    print("Testing health check...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")

def test_single_formula(image_path: str):
    """Test single formula analysis"""
    print(f"Testing single formula analysis with: {image_path}")
    
    with open(image_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(f"{BASE_URL}/analyze-formula", files=files)
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"LaTeX Formula: {result['latex_formula']}")
        print(f"Description: {result['description']}")
        print(f"Variables: {len(result['variables'])} found")
        for var in result['variables']:
            print(f"  - {var['symbol']}: {var['name']} - {var['details']}")
    else:
        print(f"Error: {response.text}")
    print()

def test_batch_formulas(image_paths: list):
    """Test batch formula analysis"""
    print(f"Testing batch analysis with {len(image_paths)} images...")
    
    files = [('files', open(path, 'rb')) for path in image_paths]
    response = requests.post(f"{BASE_URL}/analyze-formulas-batch", files=files)
    
    # Close all files
    for _, file in files:
        file.close()
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        results = response.json()
        print(f"Processed {len(results)} formulas")
        for i, result in enumerate(results, 1):
            print(f"\nFormula {i}:")
            print(f"  LaTeX: {result['latex_formula']}")
            print(f"  Description: {result['description'][:100]}...")
            print(f"  Variables: {len(result['variables'])}")
    else:
        print(f"Error: {response.text}")
    print()

def test_folder_analysis(folder_path: str):
    """Test folder-based formula analysis"""
    print(f"Testing folder analysis: {folder_path}")
    
    data = {"folder_path": folder_path}
    response = requests.post(
        f"{BASE_URL}/analyze-formulas-folder",
        json=data
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Total formulas processed: {result['total']}")
        for item in result['results']:
            if 'error' in item:
                print(f"  {item['filename']}: ERROR - {item['error']}")
            else:
                print(f"  {item['filename']}: {item['latex_formula'][:50]}...")
    else:
        print(f"Error: {response.text}")
    print()

if __name__ == "__main__":
    # Test health check first
    test_health_check()
    
    # Define paths to your test images
    # Update these paths to match your actual formula images
    test_image = "../output/formulas/formula_page2_2.png"
    test_images = [
        "../output/formulas/formula_page2_2.png",
        "../output/formulas/formula_page2_3.png",
        "../output/formulas/formula_page3_4.png"
    ]
    test_folder = "../output/formulas"
    
    # Run tests if files exist
    if Path(test_image).exists():
        test_single_formula(test_image)
    else:
        print(f"Test image not found: {test_image}\n")
    
    if all(Path(p).exists() for p in test_images):
        test_batch_formulas(test_images)
    else:
        print(f"Some test images not found\n")
    
    if Path(test_folder).exists():
        test_folder_analysis(test_folder)
    else:
        print(f"Test folder not found: {test_folder}\n")
