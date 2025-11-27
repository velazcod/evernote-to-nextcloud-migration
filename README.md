# Evernote to Nextcloud Cookbook Migration

A Python tool to convert Evernote recipe notes (ENEX format) to Nextcloud Cookbook format (schema.org Recipe JSON).

## Features

- Parses multiple ENEX export files organized by category
- Extracts recipe ingredients and instructions using 3-tier fallback:
  1. **recipe-scrapers library** - For web-clipped recipes with schema.org data
  2. **Heuristic parsing** - Pattern matching for ingredients/instructions
  3. **Fallback** - Preserves raw content for manual review
- Extracts embedded images
- Assigns categories from ENEX filename
- Converts Evernote tags to keywords
- Handles duplicate recipe names
- Dry-run mode for previewing changes
- Validation command to verify output

## Requirements

- Python 3.12+
- pipenv

## Installation

```bash
# Clone or download this repository
cd evernote-export

# Install dependencies
pipenv install

# Verify installation
pipenv run python -m src.migrate --help
```

## Exporting from Evernote

1. Open Evernote desktop app (macOS or Windows)
2. Organize recipes into notebooks by category (e.g., "Appetizers", "Desserts")
3. Right-click each notebook → **Export Notebook...**
4. Select format: **ENEX** (.enex file)
5. Enable: Tags, Created date, Author
6. Save to `Imported Notes/` folder

## Usage

### Basic Migration

```bash
# Process all ENEX files in a directory (recommended)
pipenv run python -m src.migrate --input-dir "Imported Notes" ./output

# Process specific files
pipenv run python -m src.migrate "Appetizers.enex" "Desserts.enex" ./output

# Process single file
pipenv run python -m src.migrate "recipes.enex" ./output
```

### Options

```
usage: migrate.py [-h] [--input-dir DIR] [--dry-run] [--validate]
                  [--log-file PATH] [-v] [paths ...]

Migrate Evernote recipes to Nextcloud Cookbook format.

positional arguments:
  paths              ENEX files to process, followed by output directory

options:
  -h, --help         show this help message and exit
  --input-dir DIR    Directory containing .enex files
  --dry-run          Show what would be created without writing files
  --validate         Run validation tests after migration
  --log-file PATH    Write logs to file (default: migration.log)
  -v, --verbose      Increase logging verbosity (DEBUG level)
```

### Examples

```bash
# Preview changes without writing files
pipenv run python -m src.migrate --input-dir "Imported Notes" ./output --dry-run -v

# Run migration with validation
pipenv run python -m src.migrate --input-dir "Imported Notes" ./output --validate

# Validate existing output
pipenv run python -m src.migrate --validate ./output

# Verbose logging to custom file
pipenv run python -m src.migrate --input-dir "Imported Notes" ./output -v --log-file debug.log
```

## Output Format

### Folder Structure

```
output/
├── Chicken Parmesan/
│   ├── recipe.json
│   └── full.jpg
├── Chocolate Cake/
│   ├── recipe.json
│   └── full.png
├── Unclear Recipe/
│   └── recipe.json          # Category: "Needs Review"
├── migration.log
└── migration_summary.json
```

### recipe.json Schema

```json
{
  "@type": "Recipe",
  "name": "Chicken Parmesan",
  "description": "A classic Italian-American dish...",
  "recipeIngredient": [
    "4 boneless skinless chicken breasts",
    "1 cup Italian breadcrumbs",
    "2 eggs, beaten"
  ],
  "recipeInstructions": [
    "Preheat oven to 400°F (200°C).",
    "Pound chicken breasts to even thickness.",
    "Dip in eggs, then coat with breadcrumbs."
  ],
  "prepTime": "PT20M",
  "cookTime": "PT25M",
  "totalTime": "PT45M",
  "recipeYield": "4 servings",
  "recipeCategory": "Main Dishes",
  "keywords": "dinner, italian, chicken",
  "image": "full.jpg",
  "datePublished": "2024-01-01",
  "dateCreated": "2024-01-01T12:00:00Z"
}
```

## Category Handling

| ENEX Filename | recipeCategory |
|---------------|----------------|
| `Appetizers.enex` | Appetizers |
| `Main Dishes.enex` | Main Dishes |
| `Desserts.enex` | Desserts |
| `Recipes inside Interesting Articles*.enex` | Review - Possible Duplicate |
| (Failed extraction) | Needs Review |

## Migration Summary

After migration, check `migration_summary.json`:

```json
{
  "run_date": "2024-01-15T10:30:00Z",
  "mode": "production",
  "duration_seconds": 45.2,
  "summary": {
    "total_notes": 450,
    "successful": 380,
    "needs_review": 68,
    "failed": 2,
    "images_extracted": 412
  },
  "by_category": {
    "Appetizers": 45,
    "Main Dishes": 120,
    "Needs Review": 68
  },
  "issues": []
}
```

## Copying to Nextcloud

After verifying the output:

```bash
# Copy to Nextcloud Cookbook folder
cp -r ./output/* "/path/to/Nextcloud/Recipes/"
```

### Triggering Nextcloud Rescan

1. Open Nextcloud in browser
2. Go to Cookbook app
3. Open Settings (gear icon)
4. Change "Recipe folder" to a different folder
5. Save, then change back to "Recipes"
6. Save again to trigger rescan

## Troubleshooting

### High "Needs Review" Count

If many recipes end up in "Needs Review":
- Web-clipped recipes may have complex HTML that heuristics can't parse
- Manually entered notes without clear structure
- Review these in Nextcloud and edit as needed

### Missing Images

- Only the first image per note is extracted
- Image must be embedded (not linked)
- Check `migration.log` for extraction errors

### Duplicate Folder Names

Handled automatically by appending numbers:
- `Chicken Soup/`
- `Chicken Soup (2)/`
- `Chicken Soup (3)/`

### Memory Usage

The parser uses streaming (iterparse) for memory efficiency. Even large ENEX files (100MB+) should process without issues.

## Development

### Running Tests

```bash
# Run all tests
pipenv run pytest tests/ -v

# Run with coverage
pipenv run pytest tests/ -v --cov=src
```

### Project Structure

```
src/
├── migrate.py          # CLI entry point
├── enex_parser.py      # ENEX XML parsing
├── recipe_extractor.py # 3-tier extraction
├── heuristics.py       # Pattern matching
├── nextcloud_writer.py # JSON + image output
└── utils.py            # Logging, helpers
```

## License

MIT License
