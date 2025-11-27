"""
Main CLI entry point for Evernote to Nextcloud Cookbook migration.

Usage:
    # Directory mode (recommended - process all .enex files)
    python -m src.migrate --input-dir "Imported Notes" ./output [options]

    # Multiple files
    python -m src.migrate file1.enex file2.enex ./output [options]

    # Single file
    python -m src.migrate recipes.enex ./output [options]

Options:
    --input-dir PATH    Directory containing .enex files
    --dry-run           Show what would be created without writing files
    --validate          Run validation tests after migration
    --log-file PATH     Write logs to file (default: migration.log)
    --verbose, -v       Increase logging verbosity
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.enex_parser import Note, parse_enex, count_notes, get_first_image_resource
from src.recipe_extractor import Recipe, extract_recipe
from src.nextcloud_writer import write_recipe
from src.utils import setup_logging, format_file_size


logger = logging.getLogger(__name__)


@dataclass
class MigrationStats:
    """Statistics tracking for migration run."""
    total: int = 0
    success: int = 0
    needs_review: int = 0
    failed: int = 0
    images_extracted: int = 0
    by_category: dict[str, int] = field(default_factory=dict)
    start_time: datetime = field(default_factory=datetime.now)
    errors: list[dict] = field(default_factory=list)

    def record_category(self, category: str) -> None:
        """Increment count for a category."""
        self.by_category[category] = self.by_category.get(category, 0) + 1

    def record_error(self, enex_file: str, note_title: str, error: str) -> None:
        """Record an error for later reporting."""
        self.errors.append({
            'file': enex_file,
            'note': note_title,
            'error': str(error)
        })

    @property
    def duration_seconds(self) -> float:
        """Calculate elapsed time in seconds."""
        return (datetime.now() - self.start_time).total_seconds()


def category_from_filename(enex_path: Path) -> str:
    """
    Extract category from ENEX filename.

    Examples:
        'Appetizers.enex' → 'Appetizers'
        'Main Dishes.enex' → 'Main Dishes'
        'Recipes inside Interesting Articles*.enex' → 'Review - Possible Duplicate'

    Args:
        enex_path: Path to ENEX file

    Returns:
        Category name
    """
    name = enex_path.stem  # Filename without extension

    # Special case for "Interesting Articles" files
    if 'interesting articles' in name.lower():
        return 'Review - Possible Duplicate'

    return name


def extract_name_from_content(description: str, html_content: str) -> str | None:
    """
    Extract recipe name from content when note title is empty/untitled.

    The recipe name is typically at the start of the description or
    in the first heading of the HTML content.

    Args:
        description: Extracted description field
        html_content: Raw HTML content

    Returns:
        Extracted name or None if not found
    """
    import re
    from bs4 import BeautifulSoup

    # Strategy 1: Extract from description (most reliable)
    # Description often starts with "Recipe Name Ingredients..." or "Recipe Name Description..."
    if description:
        # Common patterns that indicate end of recipe name
        stop_words = [
            'ingredients', 'ingredient', 'directions', 'instructions',
            'method', 'recipe', 'prep', 'cook', 'servings', 'serving',
            'calories', 'cal', 'mins', 'min', 'hours', 'hour',
            # Spanish
            'ingredientes', 'preparación', 'instrucciones',
        ]

        # Build regex to find where the name ends
        # Match until we hit a common stop word or excessive length
        desc_lower = description.lower()

        # Find the earliest stop word position
        earliest_pos = len(description)
        for word in stop_words:
            pos = desc_lower.find(word)
            if pos > 0 and pos < earliest_pos:
                earliest_pos = pos

        # Also check for pattern breaks (multiple spaces, common separators)
        for pattern in [' - ', ' | ', ' :: ', '  ', '\n']:
            pos = description.find(pattern)
            if pos > 5 and pos < earliest_pos:  # At least 5 chars for a valid name
                earliest_pos = pos

        # Extract potential name
        if earliest_pos > 5 and earliest_pos < 150:  # Reasonable name length
            potential_name = description[:earliest_pos].strip()
            # Clean up trailing punctuation
            potential_name = re.sub(r'[:\-–—|]+$', '', potential_name).strip()

            # Validate it looks like a name (not just numbers/garbage)
            if len(potential_name) >= 3 and re.search(r'[a-zA-Z]', potential_name):
                logger.debug(f"Extracted name from description: '{potential_name}'")
                return potential_name

    # Strategy 2: Look for first heading in HTML
    if html_content:
        soup = BeautifulSoup(html_content, 'html.parser')

        # Try h1, h2, h3, or first div with substantial text
        for tag in ['h1', 'h2', 'h3']:
            heading = soup.find(tag)
            if heading and heading.get_text(strip=True):
                name = heading.get_text(strip=True)
                if 3 <= len(name) <= 150:
                    logger.debug(f"Extracted name from <{tag}>: '{name}'")
                    return name

        # Try first bold/strong text
        bold = soup.find(['b', 'strong'])
        if bold and bold.get_text(strip=True):
            name = bold.get_text(strip=True)
            if 3 <= len(name) <= 100:
                logger.debug(f"Extracted name from bold text: '{name}'")
                return name

    return None


def is_untitled(title: str) -> bool:
    """Check if a title is effectively untitled."""
    if not title:
        return True
    title_lower = title.lower().strip()
    return title_lower in ('untitled note', 'untitled', '')


def collect_enex_files(file_args: list[str], input_dir: str | None) -> list[Path]:
    """
    Collect ENEX files from command line args or input directory.

    Args:
        file_args: List of file paths from command line
        input_dir: Directory to scan for .enex files (optional)

    Returns:
        List of Path objects to ENEX files

    Raises:
        ValueError: If no ENEX files found
    """
    if input_dir:
        input_path = Path(input_dir)
        if not input_path.exists():
            raise ValueError(f"Input directory not found: {input_dir}")
        if not input_path.is_dir():
            raise ValueError(f"Not a directory: {input_dir}")

        enex_files = sorted(input_path.glob('*.enex'))
        if not enex_files:
            raise ValueError(f"No .enex files found in: {input_dir}")

        logger.info(f"Found {len(enex_files)} ENEX files in {input_dir}")
        return enex_files

    # Use file arguments (all but last which is output_dir)
    enex_files = [Path(f) for f in file_args]

    # Verify files exist
    for f in enex_files:
        if not f.exists():
            raise ValueError(f"ENEX file not found: {f}")
        if not f.suffix.lower() == '.enex':
            raise ValueError(f"Not an ENEX file: {f}")

    return enex_files


def process_note(
    note: Note,
    category: str,
    output_dir: Path,
    dry_run: bool,
    stats: MigrationStats,
    enex_name: str
) -> None:
    """
    Process a single note: extract recipe and write to output.

    Args:
        note: Parsed Note object
        category: Category from ENEX filename
        output_dir: Output directory
        dry_run: If True, only log what would happen
        stats: Stats object to update
        enex_name: Name of source ENEX file for error reporting
    """
    stats.total += 1

    try:
        # Extract recipe from note content
        recipe = extract_recipe(
            html_content=note.content_html,
            source_url=note.source_url,
            title=note.title
        )

        # Set fields from note metadata
        # Try to extract a better name if note is untitled
        if is_untitled(note.title):
            extracted_name = extract_name_from_content(recipe.description, note.content_html)
            if extracted_name:
                recipe.name = extracted_name
                logger.info(f"Extracted name for untitled note: '{extracted_name}'")
            else:
                recipe.name = note.title  # Keep "Untitled Note"
                logger.warning(f"Could not extract name for untitled note, using: '{note.title}'")
        else:
            recipe.name = note.title

        recipe.keywords = ', '.join(note.tags)
        recipe.date_created = note.created.isoformat()
        recipe.date_published = note.created.strftime('%Y-%m-%d')

        # Set category
        if recipe.needs_review:
            recipe.category = "Needs Review"
            stats.needs_review += 1
        else:
            recipe.category = category
            stats.success += 1

        stats.record_category(recipe.category)

        # Check for image
        first_image = get_first_image_resource(note)
        if first_image:
            stats.images_extracted += 1

        # Write recipe
        folder_path = write_recipe(
            recipe=recipe,
            resources=note.resources,
            output_dir=output_dir,
            dry_run=dry_run
        )

        logger.debug(f"Wrote recipe: {note.title} → {folder_path}")

    except Exception as e:
        stats.failed += 1
        stats.record_error(enex_name, note.title, str(e))
        logger.error(f"Failed to process '{note.title}': {e}")


def write_summary(stats: MigrationStats, output_dir: Path, dry_run: bool = False) -> None:
    """
    Write migration summary to output directory.

    Args:
        stats: Migration statistics
        output_dir: Output directory
        dry_run: If True, only log
    """
    summary = {
        'run_date': datetime.now().isoformat(),
        'mode': 'dry-run' if dry_run else 'production',
        'duration_seconds': round(stats.duration_seconds, 2),
        'summary': {
            'total_notes': stats.total,
            'successful': stats.success,
            'needs_review': stats.needs_review,
            'failed': stats.failed,
            'images_extracted': stats.images_extracted
        },
        'by_category': stats.by_category,
        'issues': stats.errors
    }

    if dry_run:
        logger.info(f"[DRY RUN] Would write summary to {output_dir}/migration_summary.json")
        return

    summary_path = output_dir / 'migration_summary.json'
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        f.write('\n')

    logger.info(f"Wrote migration summary to {summary_path}")


def print_summary(stats: MigrationStats) -> None:
    """Print summary to console."""
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Total notes processed: {stats.total}")
    print(f"  Successful:          {stats.success}")
    print(f"  Needs Review:        {stats.needs_review}")
    print(f"  Failed:              {stats.failed}")
    print(f"  Images extracted:    {stats.images_extracted}")
    print(f"Duration:              {stats.duration_seconds:.1f} seconds")
    print()

    if stats.by_category:
        print("By Category:")
        for category, count in sorted(stats.by_category.items()):
            print(f"  {category}: {count}")
        print()

    if stats.errors:
        print(f"Errors ({len(stats.errors)}):")
        for error in stats.errors[:10]:  # Show first 10
            print(f"  [{error['file']}] {error['note']}: {error['error']}")
        if len(stats.errors) > 10:
            print(f"  ... and {len(stats.errors) - 10} more")
        print()


def run_validation(output_dir: Path) -> bool:
    """
    Run validation tests on output directory.

    Args:
        output_dir: Directory to validate

    Returns:
        True if validation passed, False otherwise
    """
    logger.info(f"Running validation on {output_dir}")

    issues = []
    recipe_count = 0
    valid_count = 0

    # Find all recipe.json files
    for recipe_json in output_dir.glob('*/recipe.json'):
        recipe_count += 1
        folder_name = recipe_json.parent.name

        try:
            with open(recipe_json, 'r', encoding='utf-8') as f:
                recipe = json.load(f)

            # Check required fields
            required = ['@type', 'name', 'recipeIngredient', 'recipeInstructions']
            missing = [field for field in required if field not in recipe]

            if missing:
                issues.append({
                    'folder': folder_name,
                    'issue': f"Missing required fields: {missing}"
                })
                continue

            # Check @type
            if recipe.get('@type') != 'Recipe':
                issues.append({
                    'folder': folder_name,
                    'issue': f"Invalid @type: {recipe.get('@type')}"
                })
                continue

            # Check arrays are actually arrays
            if not isinstance(recipe.get('recipeIngredient', []), list):
                issues.append({
                    'folder': folder_name,
                    'issue': "recipeIngredient is not an array"
                })
                continue

            if not isinstance(recipe.get('recipeInstructions', []), list):
                issues.append({
                    'folder': folder_name,
                    'issue': "recipeInstructions is not an array"
                })
                continue

            valid_count += 1

        except json.JSONDecodeError as e:
            issues.append({
                'folder': folder_name,
                'issue': f"Invalid JSON: {e}"
            })
        except Exception as e:
            issues.append({
                'folder': folder_name,
                'issue': f"Error reading: {e}"
            })

    # Print validation results
    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)
    print(f"Total recipes found: {recipe_count}")
    print(f"Valid:               {valid_count}")
    print(f"Invalid:             {len(issues)}")

    if issues:
        print(f"\nIssues ({len(issues)}):")
        for issue in issues[:20]:  # Show first 20
            print(f"  [{issue['folder']}] {issue['issue']}")
        if len(issues) > 20:
            print(f"  ... and {len(issues) - 20} more")

        return False

    print("\nAll recipes validated successfully!")
    return True


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Migrate Evernote recipes to Nextcloud Cookbook format.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all .enex files in a directory
  python -m src.migrate --input-dir "Imported Notes" ./output

  # Dry run to preview changes
  python -m src.migrate --input-dir "Imported Notes" ./output --dry-run -v

  # Process specific files
  python -m src.migrate Appetizers.enex Desserts.enex ./output

  # Validate existing output
  python -m src.migrate --validate ./output
        """
    )

    parser.add_argument(
        'paths',
        nargs='*',
        help='ENEX files to process, followed by output directory'
    )

    parser.add_argument(
        '--input-dir',
        dest='input_dir',
        metavar='DIR',
        help='Directory containing .enex files (alternative to positional arguments)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be created without writing files'
    )

    parser.add_argument(
        '--validate',
        action='store_true',
        help='Run validation tests after migration (or standalone on existing output)'
    )

    parser.add_argument(
        '--log-file',
        metavar='PATH',
        help='Write logs to file (default: migration.log in output_dir)'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Increase logging verbosity (DEBUG level)'
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()

    # Determine output directory
    if args.validate and len(args.paths) == 1:
        # Validate-only mode: single path is output dir
        output_dir = Path(args.paths[0])
        enex_files = []
    elif args.input_dir:
        # Input directory mode
        if not args.paths:
            print("Error: Output directory required", file=sys.stderr)
            return 1
        output_dir = Path(args.paths[0])
        enex_files = None  # Will be collected from input_dir
    else:
        # Positional arguments mode
        if len(args.paths) < 2:
            print("Error: Need at least one ENEX file and an output directory", file=sys.stderr)
            print("Use --help for usage information", file=sys.stderr)
            return 1
        output_dir = Path(args.paths[-1])
        enex_files = args.paths[:-1]

    # Set up logging
    log_file = args.log_file or (output_dir / 'migration.log')
    setup_logging(log_file=log_file, verbose=args.verbose)

    # Validate-only mode
    if args.validate and not enex_files and not args.input_dir:
        if not output_dir.exists():
            print(f"Error: Output directory not found: {output_dir}", file=sys.stderr)
            return 1
        success = run_validation(output_dir)
        return 0 if success else 1

    # Collect ENEX files
    try:
        enex_files = collect_enex_files(enex_files or [], args.input_dir)
    except ValueError as e:
        logger.error(str(e))
        return 1

    # Create output directory
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Log configuration
    logger.info("=" * 60)
    logger.info("Evernote to Nextcloud Cookbook Migration")
    logger.info("=" * 60)
    logger.info(f"Input files: {len(enex_files)} ENEX files")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Verbose: {args.verbose}")

    # Preview files
    total_size = 0
    for enex_path in enex_files:
        size = enex_path.stat().st_size
        total_size += size
        logger.info(f"  {enex_path.name} ({format_file_size(size)})")
    logger.info(f"Total size: {format_file_size(total_size)}")

    # Initialize stats
    stats = MigrationStats()

    # Process each ENEX file
    for enex_path in enex_files:
        category = category_from_filename(enex_path)
        logger.info(f"\nProcessing {enex_path.name} → Category: {category}")

        # Count notes first for progress
        note_count = count_notes(enex_path)
        logger.info(f"Found {note_count} notes")

        # Process notes
        processed = 0
        for note in parse_enex(enex_path):
            processed += 1
            if processed % 50 == 0:
                logger.info(f"Progress: {processed}/{note_count} notes")

            process_note(
                note=note,
                category=category,
                output_dir=output_dir,
                dry_run=args.dry_run,
                stats=stats,
                enex_name=enex_path.name
            )

        logger.info(f"Completed {enex_path.name}: {processed} notes processed")

    # Write summary
    write_summary(stats, output_dir, args.dry_run)

    # Print summary to console
    print_summary(stats)

    # Run validation if requested
    if args.validate:
        if not args.dry_run:
            run_validation(output_dir)

    # Determine exit code
    if stats.failed > 0:
        logger.warning(f"Migration completed with {stats.failed} errors")
        return 1

    logger.info("Migration completed successfully!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
