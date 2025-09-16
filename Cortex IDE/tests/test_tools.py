import pytest
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

# Adjust path to import tools from the parent directory
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lint_file_tool, format_file_tool, get_safe_path, save_file, read_file
from code_utils import _internal_lint_code, _internal_format_code

DUMMY_PROJECT_PATH = "/tmp/dummy_project_for_tools_test"


@pytest.fixture(autouse=True)
def setup_dummy_project():
    os.makedirs(DUMMY_PROJECT_PATH, exist_ok=True)
    yield
    # Basic cleanup
    for item in os.listdir(DUMMY_PROJECT_PATH):
        item_path = os.path.join(DUMMY_PROJECT_PATH, item)
        if os.path.isfile(item_path):
            os.remove(item_path)


@patch("tools._internal_lint_code")
def test_lint_file_tool_success_with_issues(mock_internal_lint):
    mock_internal_lint.return_value = {
        "success": True,
        "issues": [
            {"line": 1, "col": 1, "code": "F401", "message": "'os' imported but unused"}
        ],
    }
    test_filename = "test_lint_dummy.py"
    test_filepath = os.path.join(DUMMY_PROJECT_PATH, test_filename)
    with open(test_filepath, "w") as f:
        f.write("import os\nprint('hello')")

    result = lint_file_tool(DUMMY_PROJECT_PATH, test_filename)

    mock_internal_lint.assert_called_once_with("import os\nprint('hello')")
    assert "Found 1 linting issues" in result
    assert "Line 1, Col 1: [F401] 'os' imported but unused" in result


@patch("tools._internal_lint_code")
def test_lint_file_tool_no_issues(mock_internal_lint):
    mock_internal_lint.return_value = {"success": True, "issues": []}

    test_filename = "test_lint_clean_dummy.py"
    test_filepath = os.path.join(DUMMY_PROJECT_PATH, test_filename)
    with open(test_filepath, "w") as f:
        f.write("print('hello')")

    result = lint_file_tool(DUMMY_PROJECT_PATH, test_filename)
    assert "No linting issues found" in result


def test_lint_file_tool_non_python_file():
    result = lint_file_tool(DUMMY_PROJECT_PATH, "test.txt")
    assert "Error: Linting is only supported for Python files (.py)" in result


def test_lint_file_tool_non_existent_file():
    result = lint_file_tool(DUMMY_PROJECT_PATH, "non_existent.py")
    assert "Error: File 'non_existent.py' not found for linting" in result


@patch("tools._internal_format_code")
def test_format_file_tool_success_changes_made(mock_internal_format):
    original_code = "def  foo(): print( 'hello' )"
    formatted_code = 'def foo():\n    print("hello")\n'
    mock_internal_format.return_value = {
        "success": True,
        "formatted_code": formatted_code,
    }

    test_filename = "test_format_dummy.py"
    test_filepath = os.path.join(DUMMY_PROJECT_PATH, test_filename)
    with open(test_filepath, "w") as f:
        f.write(original_code)

    result = format_file_tool(DUMMY_PROJECT_PATH, test_filename)

    with open(test_filepath, "r") as f:
        final_content = f.read()

    assert final_content == formatted_code
    assert f"File '{test_filename}' formatted successfully" in result


@patch("tools._internal_format_code")
def test_format_file_tool_success_no_changes(mock_internal_format):
    original_code = 'def foo():\n    print("hello")\n'
    mock_internal_format.return_value = {
        "success": True,
        "formatted_code": original_code,
    }

    test_filename = "test_format_clean_dummy.py"
    test_filepath = os.path.join(DUMMY_PROJECT_PATH, test_filename)
    with open(test_filepath, "w") as f:
        f.write(original_code)

    result = format_file_tool(DUMMY_PROJECT_PATH, test_filename)

    with open(test_filepath, "r") as f:
        final_content = f.read()

    assert final_content == original_code  # Should not change
    assert f"File '{test_filename}' is already correctly formatted" in result


@patch("tools._internal_lint_code")
def test_lint_file_tool_api_error(mock_internal_lint):
    mock_internal_lint.return_value = {
        "success": False,
        "error": "Syntax error in code",
    }

    test_filename = "test_lint_api_error.py"
    test_filepath = os.path.join(DUMMY_PROJECT_PATH, test_filename)
    with open(test_filepath, "w") as f:
        f.write("def foo():::")

    result = lint_file_tool(DUMMY_PROJECT_PATH, test_filename)
    assert "Error linting file" in result
    assert "Syntax error in code" in result
