"""
Clean Snopes JSON files by extracting only published dates (not updated dates).

This script:
1. Reads JSON files from outputs_clean/
2. Normalizes all publish_date fields using the date_extractor module
3. Saves cleaned files to outputs_clean/snopesCleanTrial/

Usage:
    python data_cleaning/clean_snopes_dates.py

Input location:
    - Place JSON files in: outputs_clean/
    - Or modify INPUT_DIR variable below

Output location:
    - Cleaned files are saved to: outputs_clean/snopesCleanTrial/
"""

import json
import os
import sys
from pathlib import Path

# Add workspace root to path so imports work correctly
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_cleaning.date_extractor import normalize_publish_date


# ============================================================================
# CONFIGURATION - CHANGE THESE TO SPECIFY WHICH FILE TO CLEAN
# ============================================================================

# Specify the JSON filename to clean (just the filename, not the full path)
# Examples: "SnopesFactChecks.json", "SnopesNews.json", "SnopesFactChecksNoVerdict.json"
INPUT_FILE = "SnopesNews.json"

# The script will:
# - Read from:  outputs_clean/[INPUT_FILE]
# - Save to:    outputs_clean/snopesCleanTrial/[INPUT_FILE]
# - Original file in outputs_clean/ will NOT be modified (safe backup)
# ============================================================================

INPUT_DIR = "outputs_clean"                    # Directory where raw JSON files are stored
OUTPUT_DIR = "outputs_clean/snopesCleanTrial"  # Directory to save cleaned files


def clean_json_file(input_path: str, output_path: str) -> int:
    """
    Clean a JSON file by normalizing all publish_date fields.
    
    Args:
        input_path: Path to input JSON file
        output_path: Path to save cleaned JSON file
        
    Returns:
        Number of records processed
    """
    print(f"\n{'='*70}")
    print(f"Processing: {input_path}")
    print(f"{'='*70}")
    
    # Read input JSON
    with open(input_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to parse JSON: {e}")
            return 0
    
    # Ensure data is a list
    if not isinstance(data, list):
        print(f"ERROR: JSON is not a list, skipping...")
        return 0
    
    # Clean each record
    cleaned_count = 0
    unchanged_count = 0
    failed_count = 0
    
    for i, record in enumerate(data):
        if not isinstance(record, dict):
            print(f"  Record {i}: Skipped (not a dict)")
            continue
        
        # Skip empty records
        if not record:
            continue
        
        # Get original publish_date
        original_date = record.get('publish_date')
        
        # Normalize the publish_date
        if original_date:
            normalized_date = normalize_publish_date(original_date)
            
            if normalized_date:
                if normalized_date != original_date:
                    record['publish_date'] = normalized_date
                    cleaned_count += 1
                    if cleaned_count <= 5:  # Show first 5 conversions
                        print(f"  Record {i}: {original_date[:50]}... → {normalized_date}")
                else:
                    unchanged_count += 1
            else:
                failed_count += 1
                if failed_count <= 5:  # Show first 5 failures
                    print(f"  Record {i}: FAILED to normalize: {original_date[:50]}...")
        else:
            unchanged_count += 1
    
    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # Write cleaned JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Cleaned:   {cleaned_count} records")
    print(f"✓ Unchanged: {unchanged_count} records")
    print(f"✗ Failed:    {failed_count} records")
    print(f"✓ Saved to:  {output_path}")
    
    return len(data)


def main():
    """Main entry point."""
    print("\n" + "="*70)
    print("SNOPES JSON DATE CLEANER")
    print("="*70)
    print(f"Input file:      {INPUT_DIR}/{INPUT_FILE}")
    print(f"Output file:     {OUTPUT_DIR}/{INPUT_FILE}")
    print(f"Status:          Original file will NOT be modified (safe)")
    
    # Build full paths
    input_path = os.path.join(INPUT_DIR, INPUT_FILE)
    output_path = os.path.join(OUTPUT_DIR, INPUT_FILE)
    
    # Check if input file exists
    if not os.path.exists(input_path):
        print(f"\nERROR: Input file not found: {input_path}")
        print(f"Available files in {INPUT_DIR}:")
        if os.path.exists(INPUT_DIR):
            for f in os.listdir(INPUT_DIR):
                if f.endswith('.json'):
                    print(f"  - {f}")
        return
    
    print(f"\n✓ Input file found: {input_path}")
    print(f"✓ Will save to:    {output_path}")
    
    # Process the file
    records = clean_json_file(input_path, output_path)
    
    print("\n" + "="*70)
    print(f"COMPLETE: Processed {records} records")
    print(f"✓ Cleaned file saved to: {output_path}")
    print(f"✓ Original file intact:  {input_path}")
    print("="*70 + "\n")


if __name__ == '__main__':
    main()
