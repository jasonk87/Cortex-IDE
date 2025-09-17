import os
import pytest
from pathlib import Path
import sys

# Add the parent directory to the sys.path to allow imports from the main app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import search_and_replace, insert_at_line, apply_diff
import diff_match_patch as dmp_module

@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project directory for testing."""
    project_path = tmp_path / "test_project"
    project_path.mkdir()
    return str(project_path)

def test_search_and_replace_success(temp_project):
    """Tests successful search and replace operation."""
    filename = "test_file.txt"
    file_path = os.path.join(temp_project, filename)

    # Create a file with initial content
    initial_content = "Hello world, this is a test. The world is great."
    with open(file_path, "w") as f:
        f.write(initial_content)

    # Perform the search and replace
    result = search_and_replace(temp_project, filename, "world", "universe")
    assert "Successfully replaced" in result

    # Verify the file content
    with open(file_path, "r") as f:
        content = f.read()
    assert content == "Hello universe, this is a test. The universe is great."

def test_search_and_replace_not_found(temp_project):
    """Tests search and replace when the search query is not found."""
    filename = "test_file.txt"
    file_path = os.path.join(temp_project, filename)

    initial_content = "Hello world."
    with open(file_path, "w") as f:
        f.write(initial_content)

    result = search_and_replace(temp_project, filename, "universe", "galaxy")
    assert "Error: Search query 'universe' not found" in result

    # Ensure the file content remains unchanged
    with open(file_path, "r") as f:
        content = f.read()
    assert content == initial_content


def test_apply_diff_success(temp_project):
    """Tests successful application of a diff."""
    filename = "test_file.txt"
    file_path = os.path.join(temp_project, filename)

    initial_content = "Hello world."
    with open(file_path, "w") as f:
        f.write(initial_content)

    dmp = dmp_module.diff_match_patch()
    diff = dmp.diff_main(initial_content, "Hello universe.")
    patch = dmp.patch_make(diff)
    diff_text = dmp.patch_toText(patch)

    result = apply_diff(temp_project, filename, diff_text)
    assert "Successfully applied diff" in result

    with open(file_path, "r") as f:
        content = f.read()
    assert content == "Hello universe."

def test_insert_at_line_middle(temp_project):
    """Tests inserting content in the middle of a file."""
    filename = "test_file.txt"
    file_path = os.path.join(temp_project, filename)

    initial_content = "Line 1\nLine 3\n"
    with open(file_path, "w") as f:
        f.write(initial_content)

    content_to_insert = "Line 2"
    result = insert_at_line(temp_project, filename, 2, content_to_insert)
    assert "Successfully inserted" in result

    with open(file_path, "r") as f:
        content = f.read()
    assert content == "Line 1\nLine 2\nLine 3\n"

def test_insert_at_line_start(temp_project):
    """Tests inserting content at the beginning of a file."""
    filename = "test_file.txt"
    file_path = os.path.join(temp_project, filename)

    initial_content = "Line 2\nLine 3\n"
    with open(file_path, "w") as f:
        f.write(initial_content)

    content_to_insert = "Line 1"
    result = insert_at_line(temp_project, filename, 1, content_to_insert)
    assert "Successfully inserted" in result

    with open(file_path, "r") as f:
        content = f.read()
    assert content == "Line 1\nLine 2\nLine 3\n"

def test_insert_at_line_end(temp_project):
    """Tests inserting content at the end of a file."""
    filename = "test_file.txt"
    file_path = os.path.join(temp_project, filename)

    initial_content = "Line 1\nLine 2\n"
    with open(file_path, "w") as f:
        f.write(initial_content)

    content_to_insert = "Line 3"
    # To insert at the end, the line number should be len(lines) + 1
    result = insert_at_line(temp_project, filename, 3, content_to_insert)
    assert "Successfully inserted" in result

    with open(file_path, "r") as f:
        content = f.read()
    assert content == "Line 1\nLine 2\nLine 3\n"

def test_insert_at_line_out_of_bounds(temp_project):
    """Tests inserting content at a line number that is out of bounds."""
    filename = "test_file.txt"
    file_path = os.path.join(temp_project, filename)

    initial_content = "Line 1\n"
    with open(file_path, "w") as f:
        f.write(initial_content)

    content_to_insert = "Line X"
    result = insert_at_line(temp_project, filename, 5, content_to_insert)
    assert "Error: Line number 5 is out of bounds" in result

    # Ensure the file content remains unchanged
    with open(file_path, "r") as f:
        content = f.read()
    assert content == initial_content
