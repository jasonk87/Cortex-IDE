import pytest
import os
import json
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import requests
from werkzeug.utils import secure_filename

# Adjust path to import tools from the parent directory
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools import lint_file_tool, format_file_tool, get_safe_path, FLASK_APP_URL, save_file, read_file

# Define a dummy project path for testing
# In a real test setup, this might be a temporary directory created by pytest fixture
DUMMY_PROJECT_PATH = "/tmp/dummy_project_for_tools_test"
# Ensure FLASK_APP_URL is defined or correctly imported for the tests
# from tools import FLASK_APP_URL (if it's not already available)

@pytest.fixture(autouse=True)
def ensure_dummy_project_path():
    if not os.path.exists(DUMMY_PROJECT_PATH):
        os.makedirs(DUMMY_PROJECT_PATH, exist_ok=True)
    yield
    # Teardown: remove files created in DUMMY_PROJECT_PATH if necessary,
    # but be careful if other tests might use it.
    # For simplicity here, we are not cleaning up aggressively after each test,
    # but a real test suite might.

@patch('requests.post')
def test_lint_file_tool_success_with_issues(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "success": True,
        "issues": [
            {"line": 1, "col": 1, "code": "F401", "message": "'os' imported but unused"}
        ]
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    test_filename = "test_lint_dummy.py"
    test_filepath = os.path.join(DUMMY_PROJECT_PATH, test_filename)
    with open(test_filepath, "w") as f:
        f.write("import os\nprint('hello')")

    result = lint_file_tool(DUMMY_PROJECT_PATH, test_filename)

    mock_post.assert_called_once_with(
        f"{FLASK_APP_URL}/api/lint_code",
        json={'code': "import os\nprint('hello')"}
    )
    assert "Found 1 linting issues" in result
    assert "Line 1, Col 1: [F401] 'os' imported but unused" in result
    os.remove(test_filepath)

@patch('requests.post')
def test_lint_file_tool_no_issues(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True, "issues": []}
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    test_filename = "test_lint_clean_dummy.py"
    test_filepath = os.path.join(DUMMY_PROJECT_PATH, test_filename)
    with open(test_filepath, "w") as f:
        f.write("print('hello')")

    result = lint_file_tool(DUMMY_PROJECT_PATH, test_filename)
    assert "No linting issues found" in result
    os.remove(test_filepath)

def test_lint_file_tool_non_python_file():
    result = lint_file_tool(DUMMY_PROJECT_PATH, "test.txt")
    assert "Error: Linting is only supported for Python files (.py)" in result

def test_lint_file_tool_non_existent_file():
    result = lint_file_tool(DUMMY_PROJECT_PATH, "non_existent.py")
    assert "Error: File 'non_existent.py' not found for linting" in result

@patch('requests.post')
@patch('tools.Path.write_text') # Mock Path.write_text used by format_file_tool
@patch('tools.Path.read_text') # Mock Path.read_text used by format_file_tool
def test_format_file_tool_success_changes_made(mock_read_text, mock_write_text, mock_post):
    original_code = "def  foo(): print( 'hello' )"
    formatted_code = "def foo():\n    print(\"hello\")\n"

    mock_read_text.return_value = original_code

    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True, "formatted_code": formatted_code}
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    test_filename = "test_format_dummy.py"
    # Create a dummy file for get_safe_path to find, though its content read is mocked
    dummy_filepath = os.path.join(DUMMY_PROJECT_PATH, secure_filename(test_filename))
    Path(dummy_filepath).touch()


    result = format_file_tool(DUMMY_PROJECT_PATH, test_filename)

    mock_post.assert_called_once_with(
        f"{FLASK_APP_URL}/api/format_code",
        json={'code': original_code}
    )
    mock_read_text.assert_called_once()
    mock_write_text.assert_called_once_with(formatted_code, encoding='utf-8')
    assert f"File '{test_filename}' formatted successfully" in result

    if os.path.exists(dummy_filepath): # Clean up dummy file
        os.remove(dummy_filepath)


@patch('requests.post')
@patch('tools.Path.write_text')
@patch('tools.Path.read_text')
def test_format_file_tool_success_no_changes(mock_read_text, mock_write_text, mock_post):
    original_code = "def foo():\n    print(\"hello\")\n" # Already formatted

    mock_read_text.return_value = original_code

    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True, "formatted_code": original_code}
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    test_filename = "test_format_clean_dummy.py"
    dummy_filepath = os.path.join(DUMMY_PROJECT_PATH, secure_filename(test_filename))
    Path(dummy_filepath).touch()

    result = format_file_tool(DUMMY_PROJECT_PATH, test_filename)

    assert f"File '{test_filename}' is already correctly formatted" in result
    mock_write_text.assert_not_called() # Should not write if no changes

    if os.path.exists(dummy_filepath):
        os.remove(dummy_filepath)

@patch('requests.post')
def test_lint_file_tool_api_error(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": False, "error": "Syntax error in code"}
    mock_response.raise_for_status = MagicMock() # Simulate no HTTP error for this test
    mock_post.return_value = mock_response

    test_filename = "test_lint_api_error.py"
    test_filepath = os.path.join(DUMMY_PROJECT_PATH, test_filename)
    with open(test_filepath, "w") as f:
        f.write("def foo():::") # Invalid syntax

    result = lint_file_tool(DUMMY_PROJECT_PATH, test_filename)
    assert "Error linting file" in result
    assert "Syntax error in code" in result
    os.remove(test_filepath)

@patch('requests.post')
def test_lint_file_tool_request_exception(mock_post):
    mock_post.side_effect = requests.exceptions.ConnectionError("Failed to connect")

    test_filename = "test_lint_req_ex.py"
    test_filepath = os.path.join(DUMMY_PROJECT_PATH, test_filename)
    with open(test_filepath, "w") as f:
        f.write("print('hello')")

    result = lint_file_tool(DUMMY_PROJECT_PATH, test_filename)
    assert "Error calling linting API" in result
    assert "Failed to connect" in result
    os.remove(test_filepath)

# Add similar tests for format_file_tool API errors and request exceptions if desired.
# Note on secure_filename:
# The get_safe_path function uses werkzeug.utils.secure_filename.
# For tests involving filenames that might be altered by secure_filename (e.g., " ../../foo.py"),
# ensure the mocked file operations and assertions use the secured name if that's what
# get_safe_path would resolve to for internal operations.
# The dummy filenames used here are simple and unlikely to be changed by secure_filename.
from werkzeug.utils import secure_filename # Ensure it's imported for tests if needed directly
