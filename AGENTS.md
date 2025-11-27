# CLAUDE.md - Evernote to Nextcloud Cookbook Migration

## Project Overview

Migration script to convert Evernote recipe notes (ENEX format) to Nextcloud Cookbook (schema.org Recipe JSON format).

## Tech Stack

- **Python**: 3.12.7
- **Dependency Management**: pipenv
- **Key Libraries**:
  - `lxml` - ENEX XML parsing
  - `beautifulsoup4` - HTML content extraction
  - `recipe-scrapers` - Extract structured recipe data from clipped web content
  - `html2text` - Fallback HTML to text conversion

## Project Structure

```
[project root folder]/
├── Pipfile
├── Pipfile.lock
├── README.md
├── AGENTS.md
├── CLAUDE.md
├── GEMINI.md
├── STRUCTURED_PLANS.md
├── Imported Notes/         # ENEX exports organized by category
│   ├── Appetizers.enex
│   ├── Breakfast.enex
│   ├── Desserts.enex
│   ├── Full Meals.enex
│   ├── Main Dishes.enex
│   ├── Recipes inside Interesting Articles (May be duplicate).enex
│   ├── Sauces and Soups.enex
│   └── Side Dishes.enex
├── src/
│   ├── __init__.py
│   ├── migrate.py          # Main CLI entry point
│   ├── enex_parser.py      # ENEX XML parsing
│   ├── recipe_extractor.py # HTML → structured recipe conversion
│   ├── nextcloud_writer.py # Write recipe.json + images
│   ├── heuristics.py       # Pattern matching for unstructured recipes
│   └── utils.py            # Logging, sanitization, helpers
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # pytest fixtures, --quick/--full flags
│   ├── test_enex_parser.py
│   ├── test_recipe_extractor.py
│   ├── test_heuristics.py
│   ├── test_nextcloud_writer.py
│   ├── test_validation.py       # Real ENEX validation (--quick/--full)
│   ├── test_schema_validation.py
│   ├── test_data_integrity.py
│   ├── test_category_assignment.py
│   ├── test_content_quality.py
│   └── fixtures/
│       └── sample.enex          # Small test ENEX file
└── output/                      # Default output directory (gitignored)
```

## Key Requirements

### Input
- Multiple ENEX files exported from Evernote desktop app (one per category)
- Located in `Imported Notes/` folder:
  - Appetizers.enex, Breakfast.enex, Desserts.enex, Full Meals.enex
  - Main Dishes.enex, Sauces and Soups.enex, Side Dishes.enex
  - Recipes inside Interesting Articles (May be duplicate).enex
- Contains: note title, HTML content (in CDATA), tags, timestamps, embedded images (base64)

### Output
- Flat folder structure: `<RecipeName>/recipe.json` + optional `full.jpg`
- JSON follows schema.org Recipe format
- `recipeCategory` derived from ENEX filename (e.g., "Appetizers", "Main Dishes")
- "Recipes inside Interesting Articles" → "Review - Possible Duplicate" category
- Recipes that fail parsing get `"recipeCategory": "Needs Review"`

### CLI Interface
```bash
# Directory mode (recommended - process all .enex files)
python -m src.migrate --input-dir "Imported Notes" <output_dir> [options]

# Multiple files
python -m src.migrate <file1.enex> <file2.enex> ... <output_dir> [options]

# Single file
python -m src.migrate <enex_file> <output_dir> [options]

Options:
  --input-dir PATH    Directory containing .enex files
  --dry-run           Show what would be created without writing files
  --validate          Run validation tests after migration (or standalone)
  --log-file PATH     Write logs to file (default: migration.log)
  --verbose, -v       Increase logging verbosity
```

### Category Handling
- `recipeCategory` derived from ENEX filename (without .enex extension)
- Special case: Files containing "Interesting Articles" → "Review - Possible Duplicate"
- Failed parses → "Needs Review" (overrides source category)

### Tag Handling
- All Evernote tags → `keywords` field in recipe.json (comma-separated)
- Tags are separate from category

### Error Handling Strategy
- Recipes that cannot be parsed → create entry with `"recipeCategory": "Needs Review"`
- Raw HTML content preserved in `description` field for manual review
- Never skip/lose data

## Critical Implementation Notes

### ENEX Parsing
- Content is XHTML wrapped in CDATA
- Images referenced via `<en-media hash="...">` tags
- Hash = MD5 of decoded base64 image data
- Handle HTML entities (nbsp, special chars) - see `html.entities.entitydefs`

### Recipe Extraction (3-tier fallback)
1. **recipe-scrapers**: Try first if source URL available
2. **Heuristic parsing**: Pattern match for ingredients/instructions
3. **Fallback**: Raw content → description, mark "Needs Review"

### Nextcloud Cookbook Format
```json
{
  "@type": "Recipe",
  "name": "Recipe Title",
  "description": "Optional description",
  "recipeIngredient": ["ingredient 1", "ingredient 2"],
  "recipeInstructions": ["Step 1", "Step 2"],
  "recipeCategory": "Category or Needs Review",
  "keywords": "tag1, tag2, tag3",
  "image": "full.jpg",
  "datePublished": "2024-01-01"
}
```

### Image Handling
- First image in note becomes `full.jpg`
- Decode base64 from `<resource><data>` element
- Match to `<en-media>` via MD5 hash

### Folder Naming
- Sanitize recipe titles for filesystem safety
- Remove/replace: `/ \ : * ? " < > |`
- Handle duplicates by appending number

## Development Workflow

1. **Start with enex_parser.py** - Parse sample ENEX, extract notes
2. **Build recipe_extractor.py** - Implement 3-tier extraction
3. **Build nextcloud_writer.py** - Write JSON + images
4. **Wire up migrate.py** - CLI, logging, dry-run mode
5. **Test with real data** - User provides sample ENEX
6. **Iterate on heuristics** - Improve parsing based on failures

## Custom Agents

Three specialized agents are available in `.claude/agents/` to assist with implementation:

### xml-data-parser
**Module**: `src/enex_parser.py`

Specialist for ENEX XML parsing. Use when working on:
- lxml XML parsing and element iteration
- CDATA section extraction
- Base64 image decoding
- MD5 hash calculation for image matching
- HTML entity handling (`&nbsp;`, `&lt;`, etc.)
- Datetime parsing from Evernote format

```
@xml-data-parser help me parse the resource elements
```

### recipe-heuristics-expert
**Modules**: `src/heuristics.py`, `src/recipe_extractor.py`

Specialist for recipe extraction and pattern matching. Use when working on:
- Ingredient detection patterns (quantities, units, items)
- Instruction detection (numbered steps, cooking verbs)
- Section header recognition
- 3-tier extraction fallback strategy
- recipe-scrapers library integration
- BeautifulSoup HTML parsing

```
@recipe-heuristics-expert improve the ingredient detection regex
```

### nextcloud-cookbook-expert
**Module**: `src/nextcloud_writer.py`

Specialist for Nextcloud Cookbook output. Use when working on:
- schema.org Recipe JSON format
- Folder naming sanitization
- Duplicate name handling
- Image output as `full.jpg`
- Category assignment from ENEX filename
- ISO 8601 duration formatting

```
@nextcloud-cookbook-expert validate my recipe.json structure
```

### Agent Scope Boundaries

| Agent | Receives | Produces |
|-------|----------|----------|
| xml-data-parser | ENEX file path | `Note` objects with raw HTML |
| recipe-heuristics-expert | Raw HTML content | `Recipe` objects with structured data |
| nextcloud-cookbook-expert | `Recipe` + `Resource` objects | `recipe.json` + `full.jpg` files |

## Testing Strategy

### Unit Tests
- Unit tests for each module in `tests/`
- Integration test with sample ENEX fixture

### Validation Tests (Real ENEX Files)
Run against actual `Imported Notes/*.enex` files:

```bash
# Quick mode - smallest file only (~2MB)
pytest tests/test_validation.py -v --quick

# Full mode - all 8 ENEX files (~140MB)
pytest tests/test_validation.py -v --full
```

**Validation checks**:
- **Schema validation**: recipe.json matches schema.org Recipe format
- **Data integrity**: Note count matches output count, no data loss
- **Category assignment**: recipeCategory matches ENEX filename
- **Content quality**: Ingredients/instructions populated, no raw HTML

**CLI validation**:
```bash
# Validate existing output
python -m src.migrate --validate ./output

# Migration + validation
python -m src.migrate --input-dir "Imported Notes" ./output --validate
```

### User Acceptance
- Manual review of output before moving to Nextcloud
- Check `validation_report.json` for issues

## Out of Scope (Future/Optional)

- OCR for scanned/photographed recipes
- Direct Nextcloud API integration
- Incremental/sync updates

## User's Environment

- macOS
- Nextcloud mounted via Mountain Duck at:
  `/Users/velazcod/Library/Application Support/Mountain Duck/Volumes.noindex/Nextcloud.localized/Recipes`
- Will use temp output folder, manually move files after verification
- User prefers `vi`/`vim` for editing
