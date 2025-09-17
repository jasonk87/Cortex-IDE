import os
import shutil
import zipfile
import pytest
from pathlib import Path
import sys

# Add the parent directory to the sys.path to allow imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import create_backup

@pytest.fixture
def temp_project():
    """Create a temporary project directory with some files and a nested folder."""
    project_dir = Path("test_project_for_backup")
    project_dir.mkdir()
    (project_dir / "file1.txt").write_text("hello")
    (project_dir / "folder1").mkdir()
    (project_dir / "folder1" / "file2.txt").write_text("world")

    yield str(project_dir)

    # Teardown
    shutil.rmtree(project_dir)

def test_create_backup_creates_backup_dir_and_zip(temp_project):
    """
    Tests that create_backup successfully creates the .backups directory
    and a zip file inside it.
    """
    result = create_backup(temp_project)

    assert "Successfully created backup" in result

    backup_dir = Path(temp_project) / ".backups"
    assert backup_dir.is_dir()

    # Check that a zip file was created
    backup_files = list(backup_dir.glob("*.zip"))
    assert len(backup_files) == 1

def test_create_backup_excludes_backups_dir_from_archive(temp_project):
    """
    Tests that the created backup archive does not contain the .backups
    directory itself.
    """
    # Create a dummy file in the backup dir to ensure it's not included
    backup_dir = Path(temp_project) / ".backups"
    backup_dir.mkdir()
    (backup_dir / "dummy_file.txt").write_text("should not be in backup")

    create_backup(temp_project)

    backup_files = list(backup_dir.glob("*.zip"))
    backup_zip_path = backup_files[0]

    with zipfile.ZipFile(backup_zip_path, 'r') as zipf:
        zip_contents = zipf.namelist()

        # Check that the .backups directory and its contents are not in the archive
        assert not any(item.startswith('.backups') for item in zip_contents)
        # Check that the other files are present
        assert "file1.txt" in zip_contents
        assert os.path.join("folder1", "file2.txt") in zip_contents
