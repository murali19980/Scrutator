"""Bundle all literature review exports into a zip archive."""

import os
import zipfile
import logging

logger = logging.getLogger(__name__)

def package_review(
    report_path: str,
    latex_path: str,
    bib_path: str,
    ris_path: str,
    csv_path: str,
    obsidian_dir: str,
    zip_path: str
):
    """Zip all generated artifacts including Obsidian files."""
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Add top-level files
            for file_path in [report_path, latex_path, bib_path, ris_path, csv_path]:
                if file_path and os.path.exists(file_path):
                    zip_file.write(file_path, os.path.basename(file_path))
                    
            # 2. Add Obsidian directory contents
            if obsidian_dir and os.path.exists(obsidian_dir):
                for root, dirs, files in os.walk(obsidian_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        # Re-create folders inside zip
                        rel_path = os.path.relpath(full_path, os.path.dirname(obsidian_dir))
                        zip_file.write(full_path, rel_path)
                        
        logger.info(f"Successfully packaged all review files to: {zip_path}")
    except Exception as e:
        logger.error(f"Failed to create review package bundle: {e}")
