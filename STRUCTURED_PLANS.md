# Evernote to Nextcloud Cookbook Migration - Structured Plans

## Implementation Status

> **Last Updated**: 2025-11-27

### Current State: ✅ COMPLETE

| Component | Status | Notes |
|-----------|--------|-------|
| `src/enex_parser.py` | ✅ Complete | 376 lines, 18 unit tests passing |
| `src/heuristics.py` | ✅ Complete | 596 lines, 27 unit tests passing, improved markdown support |
| `src/recipe_extractor.py` | ✅ Complete | 420+ lines, 3-tier extraction working |
| `src/nextcloud_writer.py` | ✅ Complete | 300+ lines, schema.org JSON output |
| `src/utils.py` | ✅ Complete | 180 lines, logging and helpers |
| `src/migrate.py` | ✅ Complete | 330 lines, full CLI with validation |
| Unit Tests | ✅ Complete | 85 tests passing |
| Integration Testing | ✅ Complete | Tested against all 8 ENEX files |

### Migration Results (Production Run)

```
Total notes processed: 208
  Successful:          187  (90%)
  Needs Review:        21   (10%)
  Failed:              0
  Images extracted:    181

By Category:
  Appetizers:                 23
  Breakfast:                  11
  Desserts:                   23
  Full Meals:                 22
  Main Dishes:                64
  Needs Review:               21
  Review - Possible Duplicate: 3
  Sauces and Soups:           16
  Side Dishes:                25

Duration: ~2 seconds
```

### Key Improvements Made

1. **Markdown Header Detection** - Added `normalize_header()` and `is_header_match()` functions to recognize:
   - `# Ingredients`, `## Ingredients`, `### Ingredients`
   - `Ingredients:`, `Ingredients`
   - Mixed formats: `## Ingredients:`

2. **Extended Instruction Headers** - Added "technique", "techniques", "proceso", "preparación"

3. **Improved Line Extraction** - Better handling of markdown bullet lists (`* item`, `- item`) while preserving numbered instructions

4. **Performance** - ~10ms per recipe with warm filesystem cache

---

## Executive Summary

**Goal**: Migrate hundreds of recipes from Evernote to Nextcloud Cookbook

**Approach**: Python script that parses ENEX export files and converts them to Nextcloud Cookbook's schema.org Recipe JSON format

**Key Decisions**:
- Run from MacBook with output to temp folder
- **Multiple ENEX files**: Each file represents a category (Appetizers.enex, Breakfast.enex, etc.)
- **Category assignment**: `recipeCategory` derived from ENEX filename (not tags)
- All Evernote tags become keywords (separate from category)
- Failed parses get "Needs Review" category
- "Recipes inside Interesting Articles" file → "Review - Possible Duplicate" category
- Flat output structure (category in JSON only, no subfolders)
- Logging to console and file
- Dry-run mode supported

---

## Phase 1: Evernote Export

### Prerequisites
- Evernote desktop app (macOS or Windows)
- Free tier account (supports full ENEX export)

### Export Steps
1. Open Evernote desktop app
2. Navigate to your recipes notebook
3. Right-click notebook → **Export Notebook...**
4. Select format: **ENEX** (.enex file)
5. Check export options:
   - ☑ Tags
   - ☑ Created date
   - ☑ Author
6. Click **Export**
7. Save to project directory as `recipes.enex`

### ENEX Format Reference

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE en-export SYSTEM "http://xml.evernote.com/pub/evernote-export.dtd">
<en-export export-date="20240101T120000Z" application="Evernote" version="10.0">
  <note>
    <title>Chicken Parmesan</title>
    <content><![CDATA[
      <?xml version="1.0" encoding="UTF-8"?>
      <!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml.dtd">
      <en-note>
        <div>Ingredients:</div>
        <div>- 4 chicken breasts</div>
        <div>- 1 cup breadcrumbs</div>
        <en-media hash="abc123..." type="image/jpeg"/>
      </en-note>
    ]]></content>
    <created>20240101T120000Z</created>
    <updated>20240115T180000Z</updated>
    <tag>dinner</tag>
    <tag>italian</tag>
    <note-attributes>
      <source-url>https://example.com/recipe</source-url>
    </note-attributes>
    <resource>
      <data encoding="base64">
        /9j/4AAQSkZJRgABAQAAAQABAAD...
      </data>
      <mime>image/jpeg</mime>
      <resource-attributes>
        <file-name>photo.jpg</file-name>
      </resource-attributes>
    </resource>
  </note>
</en-export>
```

### Key ENEX Elements

| Element | Description |
|---------|-------------|
| `<title>` | Recipe name |
| `<content>` | CDATA-wrapped XHTML content |
| `<created>` | ISO timestamp |
| `<tag>` | Multiple allowed, become keywords |
| `<source-url>` | Original URL if clipped from web |
| `<resource>` | Embedded files (images) |
| `<data encoding="base64">` | Base64-encoded binary |
| `<en-media hash="...">` | Reference to resource by MD5 hash |

---

## Phase 2: Output Format (Nextcloud Cookbook)

### Folder Structure

```
output/
├── Chicken Parmesan/
│   ├── recipe.json
│   └── full.jpg
├── Beef Tacos/
│   ├── recipe.json
│   └── full.jpg
├── Unclear Recipe/
│   └── recipe.json          # Category: "Needs Review"
├── migration.log
└── summary.txt
```

### recipe.json Schema

```json
{
  "@type": "Recipe",
  "name": "Chicken Parmesan",
  "description": "A classic Italian-American dish with crispy breaded chicken topped with marinara and melted cheese.",
  "recipeIngredient": [
    "4 boneless skinless chicken breasts",
    "1 cup Italian breadcrumbs",
    "2 eggs, beaten",
    "2 cups marinara sauce",
    "1 cup shredded mozzarella cheese",
    "1/4 cup grated Parmesan cheese",
    "2 tablespoons olive oil",
    "Salt and pepper to taste"
  ],
  "recipeInstructions": [
    "Preheat oven to 400°F (200°C).",
    "Pound chicken breasts to even thickness.",
    "Season chicken with salt and pepper.",
    "Dip chicken in beaten eggs, then coat with breadcrumbs.",
    "Heat olive oil in oven-safe skillet over medium-high heat.",
    "Brown chicken 3 minutes per side.",
    "Top with marinara sauce and cheeses.",
    "Bake 15-20 minutes until chicken reaches 165°F internal temperature."
  ],
  "prepTime": "PT20M",
  "cookTime": "PT25M",
  "totalTime": "PT45M",
  "recipeYield": "4 servings",
  "recipeCategory": "",
  "keywords": "dinner, italian, chicken",
  "image": "full.jpg",
  "datePublished": "2024-01-01",
  "dateCreated": "2024-01-01T12:00:00Z"
}
```

### Schema Field Mapping

| Nextcloud Field | Source | Notes |
|-----------------|--------|-------|
| `name` | `<title>` | Direct mapping |
| `description` | Extracted or raw content | Fallback: full HTML as text |
| `recipeIngredient` | Parsed from content | Array of strings |
| `recipeInstructions` | Parsed from content | Array of strings |
| `recipeCategory` | ENEX filename | e.g., "Appetizers", "Main Dishes"; "Needs Review" on parse failure |
| `keywords` | `<tag>` elements | Comma-separated |
| `image` | First `<resource>` image | Saved as `full.jpg` |
| `datePublished` | `<created>` | Reformatted to YYYY-MM-DD |
| `dateCreated` | `<created>` | ISO format preserved |

### Time Format (ISO 8601 Duration)
- `PT20M` = 20 minutes
- `PT1H30M` = 1 hour 30 minutes
- `PT2H` = 2 hours

---

## Phase 3: Script Architecture

### Module Breakdown

```
src/
├── __init__.py
├── migrate.py          # CLI entry point, orchestration
├── enex_parser.py      # ENEX XML parsing
├── recipe_extractor.py # HTML → structured recipe
├── nextcloud_writer.py # Output file generation
├── heuristics.py       # Pattern matching logic
└── utils.py            # Shared utilities
```

### Module: enex_parser.py

**Purpose**: Parse ENEX XML, yield note objects

**Key Functions**:
```python
def parse_enex(enex_path: str) -> Iterator[Note]:
    """
    Stream-parse ENEX file, yield Note objects.
    Uses XMLPullParser for memory efficiency with large files.
    """

def extract_resources(note_element) -> dict[str, Resource]:
    """
    Extract embedded resources (images).
    Returns dict mapping MD5 hash to Resource object.
    """

def decode_content(cdata_content: str) -> str:
    """
    Extract XHTML from CDATA, handle entity encoding.
    """
```

**Data Classes**:
```python
@dataclass
class Note:
    title: str
    content_html: str
    created: datetime
    updated: datetime | None
    tags: list[str]
    source_url: str | None
    resources: dict[str, Resource]

@dataclass
class Resource:
    data: bytes
    mime_type: str
    filename: str | None
    md5_hash: str
```

### Module: recipe_extractor.py

**Purpose**: Convert HTML content to structured recipe data

**Extraction Strategy (3-tier fallback)**:

```
┌─────────────────────────────────────────────────────────┐
│ Input: HTML content + optional source URL               │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ Tier 1: recipe-scrapers library                         │
│ - Try if source_url is available                        │
│ - Works well for clipped web recipes with schema.org    │
│ - Returns structured data if successful                 │
└─────────────────────────────────────────────────────────┘
                          │
                    (if failed)
                          ▼
┌─────────────────────────────────────────────────────────┐
│ Tier 2: Heuristic parsing                               │
│ - Pattern match for ingredients/instructions            │
│ - Look for headers, lists, numbered steps               │
│ - Confidence scoring                                    │
└─────────────────────────────────────────────────────────┘
                          │
                    (if failed)
                          ▼
┌─────────────────────────────────────────────────────────┐
│ Tier 3: Fallback                                        │
│ - Convert HTML to plain text                            │
│ - Store in description field                            │
│ - Set recipeCategory = "Needs Review"                   │
└─────────────────────────────────────────────────────────┘
```

**Key Functions**:
```python
def extract_recipe(html_content: str, source_url: str | None = None) -> Recipe:
    """
    Main extraction function. Tries all tiers.
    """

def try_recipe_scrapers(html: str, url: str) -> Recipe | None:
    """
    Attempt extraction using recipe-scrapers library.
    """

def try_heuristic_parse(html: str) -> Recipe | None:
    """
    Attempt extraction using pattern matching.
    """

def create_fallback_recipe(html: str) -> Recipe:
    """
    Create minimal recipe with raw content for manual review.
    """
```

**Data Class**:
```python
@dataclass
class Recipe:
    name: str
    description: str
    ingredients: list[str]
    instructions: list[str]
    prep_time: str | None
    cook_time: str | None
    total_time: str | None
    yields: str | None
    category: str
    keywords: str
    image_filename: str | None
    date_published: str
    date_created: str
    needs_review: bool = False
```

### Module: heuristics.py

**Purpose**: Pattern matching for unstructured recipe content

**Ingredient Detection Patterns**:
```python
INGREDIENT_PATTERNS = [
    r'^\d+[\s/\d]*\s*(cup|tbsp|tsp|oz|lb|g|kg|ml|l)',  # Starts with quantity + unit
    r'^\d+[\s/\d]*\s+\w+',  # Starts with number
    r'^[\u00BC-\u00BE\u2150-\u215E]',  # Starts with fraction character
    r'^[-•*]\s+\d',  # Bullet + number
]

INGREDIENT_KEYWORDS = [
    'cup', 'cups', 'tablespoon', 'tablespoons', 'tbsp',
    'teaspoon', 'teaspoons', 'tsp', 'ounce', 'ounces', 'oz',
    'pound', 'pounds', 'lb', 'lbs', 'gram', 'grams', 'g',
    'kilogram', 'kg', 'milliliter', 'ml', 'liter', 'l',
    'pinch', 'dash', 'clove', 'cloves', 'bunch', 'handful',
]
```

**Instruction Detection Patterns**:
```python
INSTRUCTION_PATTERNS = [
    r'^\d+[\.\)]\s+',  # Numbered step: "1. " or "1) "
    r'^step\s+\d+',  # "Step 1"
]

INSTRUCTION_VERBS = [
    'preheat', 'heat', 'boil', 'simmer', 'fry', 'sauté', 'saute',
    'bake', 'roast', 'grill', 'broil', 'steam', 'poach',
    'mix', 'stir', 'whisk', 'blend', 'fold', 'combine',
    'chop', 'dice', 'mince', 'slice', 'cut', 'trim',
    'add', 'pour', 'place', 'put', 'set', 'arrange',
    'season', 'sprinkle', 'drizzle', 'coat', 'marinate',
    'let', 'allow', 'rest', 'cool', 'chill', 'refrigerate',
    'serve', 'garnish', 'top', 'finish',
]
```

**Section Header Detection**:
```python
INGREDIENT_HEADERS = [
    'ingredients', 'ingredient', 'you will need', 'you\'ll need',
    'what you need', 'shopping list', 'grocery list',
]

INSTRUCTION_HEADERS = [
    'instructions', 'directions', 'method', 'steps',
    'how to make', 'how to prepare', 'preparation',
    'procedure', 'cooking instructions',
]
```

**Parsing Algorithm**:
```python
def heuristic_parse(html: str) -> tuple[list[str], list[str], bool]:
    """
    Returns (ingredients, instructions, confidence_ok)
    
    Algorithm:
    1. Convert HTML to text, split into lines
    2. Detect section headers to identify regions
    3. If no headers, score each line as ingredient vs instruction
    4. Group consecutive lines of same type
    5. Return highest-scoring groups
    6. confidence_ok = True if clear separation found
    """
```

### Module: nextcloud_writer.py

**Purpose**: Write recipe.json and images to output folder

**Key Functions**:
```python
def write_recipe(recipe: Recipe, resources: dict, output_dir: str, dry_run: bool = False) -> str:
    """
    Write recipe to output directory.
    Returns path to created folder.
    """

def sanitize_folder_name(name: str) -> str:
    """
    Make name filesystem-safe.
    - Remove/replace: / \\ : * ? " < > |
    - Trim whitespace
    - Handle empty/whitespace-only names
    - Truncate if too long
    """

def handle_duplicate_name(base_path: str) -> str:
    """
    If folder exists, append number: "Recipe Name (2)"
    """

def write_image(resource: Resource, recipe_dir: str, dry_run: bool = False) -> str | None:
    """
    Write first image as full.jpg.
    Returns filename or None.
    """

def generate_recipe_json(recipe: Recipe) -> dict:
    """
    Convert Recipe dataclass to Nextcloud Cookbook JSON format.
    """
```

### Module: migrate.py (CLI)

**Purpose**: Main entry point, orchestration, logging

**CLI Interface**:
```
usage: migrate.py [-h] [--input-dir DIR] [--dry-run] [--log-file PATH] [-v]
                  [enex_files ...] output_dir

Migrate Evernote recipes to Nextcloud Cookbook format.

positional arguments:
  enex_files         One or more ENEX files to process
  output_dir         Output directory for recipe folders (flat structure)

options:
  -h, --help         show this help message and exit
  --input-dir DIR    Directory containing .enex files (alternative to positional)
  --dry-run          Show what would be created without writing files
  --validate         Run validation tests after migration (or standalone on existing output)
  --log-file PATH    Write logs to file (default: migration.log in output_dir)
  -v, --verbose      Increase logging verbosity
```

**Category Mapping**:
- Category derived from ENEX filename (without .enex extension)
- Special case: Files containing "Interesting Articles" → "Review - Possible Duplicate"
- Failed parses → "Needs Review" (overrides source category)

**Main Flow**:
```python
def main():
    args = parse_args()
    setup_logging(args.log_file, args.verbose)

    # Collect ENEX files from args or input directory
    enex_files = collect_enex_files(args.enex_files, args.input_dir)

    stats = MigrationStats()

    for enex_path in enex_files:
        # Extract category from filename
        category = category_from_filename(enex_path)
        logger.info(f"Processing {enex_path.name} → Category: {category}")

        for note in parse_enex(enex_path):
            try:
                recipe = extract_recipe(note.content_html, note.source_url)
                recipe.name = note.title
                recipe.keywords = ', '.join(note.tags)
                recipe.date_created = note.created.isoformat()

                if recipe.needs_review:
                    recipe.category = "Needs Review"
                    stats.needs_review += 1
                else:
                    recipe.category = category  # From ENEX filename
                    stats.success += 1

                write_recipe(recipe, note.resources, args.output_dir, args.dry_run)

            except Exception as e:
                logger.error(f"Failed to process '{note.title}': {e}")
                stats.failed += 1

    write_summary(stats, args.output_dir)
    print_summary(stats)


def category_from_filename(enex_path: Path) -> str:
    """
    Extract category from ENEX filename.

    Examples:
        'Appetizers.enex' → 'Appetizers'
        'Main Dishes.enex' → 'Main Dishes'
        'Recipes inside Interesting Articles*.enex' → 'Review - Possible Duplicate'
    """
    name = enex_path.stem  # Filename without extension
    if 'interesting articles' in name.lower():
        return 'Review - Possible Duplicate'
    return name


def collect_enex_files(file_args: list, input_dir: str | None) -> list[Path]:
    """
    Collect ENEX files from command line args or input directory.
    """
    if input_dir:
        return sorted(Path(input_dir).glob('*.enex'))
    return [Path(f) for f in file_args]
```

**Stats Tracking**:
```python
@dataclass
class MigrationStats:
    total: int = 0
    success: int = 0
    needs_review: int = 0
    failed: int = 0
    images_extracted: int = 0
    by_category: dict[str, int] = field(default_factory=dict)  # Per-category counts
    start_time: datetime = field(default_factory=datetime.now)
```

### Module: utils.py

**Purpose**: Shared utilities

**Functions**:
```python
def setup_logging(log_file: str | None, verbose: bool) -> None:
    """Configure logging to console and file."""

def normalize_whitespace(text: str) -> str:
    """Collapse multiple whitespace to single space."""

def html_to_text(html: str) -> str:
    """Convert HTML to plain text, preserving structure."""

def parse_iso_duration(duration_str: str) -> timedelta | None:
    """Parse ISO 8601 duration (PT1H30M) to timedelta."""

def format_iso_duration(minutes: int) -> str:
    """Format minutes as ISO 8601 duration."""

def safe_get(dict_obj: dict, *keys, default=None):
    """Safely navigate nested dicts."""
```

---

## Phase 4: Development Steps

### Step 1: Project Setup
```bash
mkdir evernote-to-nextcloud-cookbook
cd evernote-to-nextcloud-cookbook

# Initialize pipenv
pipenv --python 3.12
pipenv install lxml beautifulsoup4 recipe-scrapers html2text
pipenv install --dev pytest

# Create structure
mkdir -p src tests/fixtures output
touch src/__init__.py tests/__init__.py
```

### Step 2: Implement enex_parser.py
1. Parse sample ENEX file
2. Extract note metadata (title, tags, dates)
3. Extract and decode content CDATA
4. Extract resources, compute MD5 hashes
5. Handle HTML entities
6. Write unit tests

### Step 3: Implement heuristics.py
1. Implement ingredient pattern matching
2. Implement instruction pattern matching
3. Implement section header detection
4. Implement line scoring algorithm
5. Write unit tests with various recipe formats

### Step 4: Implement recipe_extractor.py
1. Implement recipe-scrapers integration
2. Implement heuristic parsing wrapper
3. Implement fallback handling
4. Chain all three tiers
5. Write unit tests

### Step 5: Implement nextcloud_writer.py
1. Implement folder name sanitization
2. Implement duplicate handling
3. Implement recipe.json generation
4. Implement image extraction
5. Write unit tests

### Step 6: Implement migrate.py
1. Set up argument parsing
2. Set up logging (console + file)
3. Implement main migration loop
4. Implement dry-run mode
5. Implement stats tracking
6. Implement summary generation
7. Integration testing

### Step 7: Testing with Real Data
1. Export small test notebook from Evernote
2. Run migration in dry-run mode
3. Review output
4. Iterate on heuristics based on failures
5. Full migration run
6. Manual review of "Needs Review" recipes

### Step 8: Production Run
1. Export full recipes notebook
2. Run migration
3. Review summary and logs
4. Move output to Nextcloud mount
5. Trigger Cookbook rescan
6. Verify in Nextcloud UI

---

## Phase 5: Testing Strategy

### Unit Tests

| Module | Test Cases |
|--------|------------|
| enex_parser | Valid ENEX, malformed XML, missing fields, special characters, multiple notes |
| heuristics | Clear ingredients list, numbered instructions, mixed content, no clear structure |
| recipe_extractor | Web-clipped recipe, manual recipe, fallback case |
| nextcloud_writer | Normal name, special characters in name, duplicate names, image extraction |
| utils | Whitespace normalization, HTML conversion, duration parsing |

### Integration Tests

1. End-to-end with sample ENEX containing:
   - Web-clipped recipe with schema.org
   - Manually entered recipe with clear structure
   - Recipe with images
   - Recipe with unclear structure (should get "Needs Review")

### Test Fixtures

Create `tests/fixtures/sample.enex` with representative examples from actual Evernote export.

### Validation Tests (Real ENEX Files)

Validation tests run against actual `Imported Notes/*.enex` files to ensure migration correctness before moving to Nextcloud.

#### Test Modes

```bash
# Quick mode - smallest file only (~2MB, fast feedback)
pytest tests/test_validation.py -v --quick

# Full mode - all 8 ENEX files (~140MB, comprehensive)
pytest tests/test_validation.py -v --full
```

#### Validation Test Suite

**1. Schema Validation (`test_schema_validation.py`)**
```python
def test_recipe_json_schema():
    """Validate all output recipe.json files against schema.org Recipe schema."""
    # Required fields present: @type, name, recipeIngredient, recipeInstructions
    # Correct data types: arrays for ingredients/instructions, strings for others
    # Valid ISO 8601 durations for prepTime/cookTime/totalTime

def test_json_encoding():
    """Verify JSON files are valid UTF-8 with proper escaping."""
    # No invalid Unicode
    # Special characters properly escaped
    # File is parseable by json.load()
```

**2. Data Integrity (`test_data_integrity.py`)**
```python
def test_note_count_matches():
    """Verify output recipe count matches input note count per ENEX file."""
    # Parse ENEX, count <note> elements
    # Count output folders
    # Assert counts match (accounting for duplicates)

def test_no_data_loss():
    """Ensure every note produces output (recipe.json or error log)."""
    # Track all note titles from ENEX
    # Verify each has corresponding output folder OR logged error
    # No silent failures

def test_image_extraction():
    """Verify images are correctly extracted and matched."""
    # Count <resource> elements with image MIME types in ENEX
    # Count full.jpg files in output
    # Verify MD5 hash matching worked (spot check)

def test_title_preservation():
    """Verify recipe names match original note titles."""
    # Compare ENEX <title> to recipe.json "name" field
    # Account for sanitization (special chars removed)
```

**3. Category Assignment (`test_category_assignment.py`)**
```python
def test_category_from_filename():
    """Verify recipeCategory matches source ENEX filename."""
    # Appetizers.enex → "Appetizers"
    # Main Dishes.enex → "Main Dishes"
    # Sauces and Soups.enex → "Sauces and Soups"

def test_special_category_handling():
    """Verify special cases are handled correctly."""
    # "Interesting Articles" → "Review - Possible Duplicate"
    # Failed parses → "Needs Review"

def test_category_distribution():
    """Report category distribution for manual review."""
    # Count recipes per category
    # Flag if "Needs Review" exceeds threshold (e.g., >20%)
```

**4. Content Quality (`test_content_quality.py`)**
```python
def test_ingredients_extracted():
    """Verify ingredients array is populated (not empty) for most recipes."""
    # Allow some "Needs Review" recipes to have empty ingredients
    # Flag if >50% have empty ingredients (heuristics need tuning)

def test_instructions_extracted():
    """Verify instructions array is populated for most recipes."""
    # Same threshold logic as ingredients

def test_no_html_in_output():
    """Verify HTML tags are stripped from text fields."""
    # Check description, ingredients, instructions for <tag> patterns
    # Allow &amp; &lt; &gt; entities (expected)

def test_reasonable_field_lengths():
    """Flag suspiciously long or short fields for review."""
    # Ingredients >500 chars might indicate parsing failure
    # Empty description is OK, but empty name is not
```

#### Validation Report

After running validation tests, generate `validation_report.json`:

```json
{
  "run_date": "2024-01-15T10:30:00Z",
  "mode": "full",
  "summary": {
    "total_notes": 450,
    "total_recipes": 448,
    "successful": 380,
    "needs_review": 68,
    "failed": 2,
    "images_extracted": 412
  },
  "by_category": {
    "Appetizers": {"count": 45, "needs_review": 5},
    "Breakfast": {"count": 38, "needs_review": 3},
    "...": "..."
  },
  "issues": [
    {"file": "Main Dishes.enex", "note": "Grandma's Recipe", "error": "Parse timeout"},
    {"file": "Desserts.enex", "note": "Birthday Cake", "error": "No content"}
  ]
}
```

#### CLI Validation Command

```bash
# Run validation only (no migration, just check existing output)
python -m src.migrate --validate ./output

# Run migration + validation
python -m src.migrate --input-dir "Imported Notes" ./output --validate
```

---

## Phase 6: Error Handling

### Expected Errors

| Error | Handling |
|-------|----------|
| ENEX file not found | Exit with clear error message |
| Invalid XML | Log error, skip note, continue |
| Missing title | Use "Untitled Recipe" + timestamp |
| Missing content | Create empty recipe with "Needs Review" |
| Image decode failure | Log warning, continue without image |
| Duplicate folder name | Append number: "Recipe (2)" |
| Filesystem permission error | Exit with clear error message |

### Logging Levels

| Level | Usage |
|-------|-------|
| DEBUG | Detailed parsing info, pattern matches |
| INFO | Note processing progress, success messages |
| WARNING | Non-fatal issues (missing image, unclear structure) |
| ERROR | Processing failures, skipped notes |

---

## Phase 7: Future Enhancements (Out of Scope)

### OCR for Scanned Recipes
- Use Tesseract OCR via `pytesseract`
- Detect images that are likely scanned text
- Extract text, then apply heuristic parsing
- Would require additional dependency and processing time

### Direct Nextcloud API Integration
- Use Nextcloud WebDAV API
- Upload directly instead of local folder
- Would enable progress feedback and validation

### Incremental Sync
- Track processed notes by hash
- Only process new/modified notes
- Would require persistent state storage

---

## Appendix A: Sample Commands

### Development
```bash
# Enter virtual environment
pipenv shell

# Run tests
pytest tests/ -v

# Run single test
pytest tests/test_enex_parser.py -v

# Run migration (dry-run) - single file
python -m src.migrate "Imported Notes/Appetizers.enex" ./output --dry-run -v

# Run migration (dry-run) - directory mode (all .enex files)
python -m src.migrate --input-dir "Imported Notes" ./output --dry-run -v

# Run migration (dry-run) - specific files
python -m src.migrate "Imported Notes/Appetizers.enex" "Imported Notes/Breakfast.enex" ./output --dry-run -v
```

### Production
```bash
# Full migration - all categories (recommended)
pipenv run python -m src.migrate --input-dir "Imported Notes" ./output

# Full migration - specific categories only
pipenv run python -m src.migrate \
    "Imported Notes/Appetizers.enex" \
    "Imported Notes/Main Dishes.enex" \
    "Imported Notes/Desserts.enex" \
    ./output

# Copy to Nextcloud (after verification)
cp -r ./output/* "/Users/velazcod/Library/Application Support/Mountain Duck/Volumes.noindex/Nextcloud.localized/Recipes/"
```

### Your Actual ENEX Files
```bash
# All 8 category files in "Imported Notes/":
#   - Appetizers.enex (17MB)
#   - Breakfast.enex (12MB)
#   - Desserts.enex (42MB)
#   - Full Meals.enex (9MB)
#   - Main Dishes.enex (41MB)
#   - Recipes inside Interesting Articles (May be duplicate).enex (2MB) → "Review - Possible Duplicate"
#   - Sauces and Soups.enex (7MB)
#   - Side Dishes.enex (11MB)
```

---

## Appendix B: Nextcloud Cookbook Rescan

After copying files to Nextcloud:

1. Open Nextcloud in browser
2. Go to Cookbook app
3. Open Settings (gear icon, bottom left)
4. Change "Recipe folder" to a different folder (e.g., root)
5. Click Save
6. Change back to "Recipes" folder
7. Click Save
8. Wait for rescan to complete
9. Verify recipes appear in list

---

## Appendix C: Troubleshooting

### ENEX Export Issues

**Problem**: Export option not available
**Solution**: Must use desktop app, not web version

**Problem**: Only 50 notes exported
**Solution**: Recent Evernote versions limit selection export; use "Export Notebook" instead

### Parsing Issues

**Problem**: Special characters cause XML parse error
**Solution**: Pre-process ENEX to handle HTML entities (implemented in enex_parser)

**Problem**: Images not appearing
**Solution**: Check MD5 hash matching between `<en-media>` and `<resource>`

### Nextcloud Issues

**Problem**: Recipes not appearing after copy
**Solution**: Trigger rescan (see Appendix B)

**Problem**: Invalid recipe.json format
**Solution**: Validate JSON structure; check for null values in required fields
