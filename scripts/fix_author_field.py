import json
import os
import re
from pathlib import Path


def fix_author_field_in_file(file_path: Path):
    """Convert 'author' field to 'authors' list in a JSON file."""
    print(f"Processing {file_path.name}...", end=" ")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"✗ JSON Error: {e}")
        print(f"  Attempting to fix malformed JSON...")
        
        # Read raw content and fix unquoted datetime values
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Fix unquoted ISO datetime values in publish_date field
        # Pattern: "publish_date": 2025-09-18T21:23:00+00:00,
        content = re.sub(
            r'"publish_date":\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+\-]\d{2}:\d{2})',
            r'"publish_date": "\1"',
            content
        )
        
        # Try parsing again
        try:
            data = json.loads(content)
            # Write the fixed content back
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("✓ Fixed JSON syntax")
        except json.JSONDecodeError as e2:
            print(f"✗ Still invalid: {e2}")
            return
    
    # Now continue with the author field fix
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    modified = False
    for item in data:
        if 'author' in item and 'authors' not in item:
            author = item.pop('author')
            # If author is already a list, use it as-is; otherwise wrap in list
            if isinstance(author, list):
                item['authors'] = author
            else:
                item['authors'] = [author] if author else []
            modified = True
    
    if modified:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("✓ Fixed")
    else:
        print("- No changes needed")


def main():
    outputs_clean_dir = Path(__file__).parent.parent / "outputs_clean"
    
    if not outputs_clean_dir.exists():
        print(f"Error: {outputs_clean_dir} does not exist")
        return
    
    json_files = list(outputs_clean_dir.glob("*.json"))
    
    if not json_files:
        print("No JSON files found in outputs_clean/")
        return
    
    print(f"Found {len(json_files)} JSON files\n")
    
    for json_file in json_files:
        try:
            fix_author_field_in_file(json_file)
        except Exception as e:
            print(f"✗ Error: {e}")
    
    print(f"\nDone! Processed {len(json_files)} files")


if __name__ == "__main__":
    main()
