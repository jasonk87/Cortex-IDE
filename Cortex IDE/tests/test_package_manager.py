import os
import shutil
import tempfile
import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Adjust the path to import app and other necessary modules from Cortex IDE
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app # Import the Flask app instance
from package_manager import package_manager_bp # If your blueprint is separate

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    # Create a temporary directory for workspaces for testing
    temp_workspaces_dir = tempfile.mkdtemp()

    # Configure the app for testing
    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "PROJECTS_BASE_DIR": temp_workspaces_dir, # Use temp dir for workspaces
         # If session depends on project_path, ensure it's handled or mocked
    })

    # If the blueprint isn't registered in your main app.py when imported,
    # you might need to register it here, or ensure your app factory does.
    # Example: if not any(bp.name == package_manager_bp.name for bp in flask_app.blueprints.values()):
    #    flask_app.register_blueprint(package_manager_bp)

    yield flask_app

    # Clean up the temporary workspaces directory
    shutil.rmtree(temp_workspaces_dir)


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def project(app):
    """Creates a temporary project for testing."""
    project_name = "test_project"
    # Use the app's configured PROJECTS_BASE_DIR
    base_dir = Path(app.config["PROJECTS_BASE_DIR"])
    project_path = base_dir / project_name
    project_path.mkdir(parents=True, exist_ok=True)

    # Create a dummy requirements.txt for some tests
    with open(project_path / "requirements.txt", "w") as f:
        f.write("requests==2.25.1\n") # Ensure newline character

    return str(project_path) # Return path as string, as session might store it

def test_install_packages_no_project_in_session(client):
    """Test /api/install_packages when no project is in session."""
    response = client.post('/api/install_packages')
    assert response.status_code == 400 # Expecting Bad Request
    data = json.loads(response.data)
    assert "error" in data
    assert "No active project session" in data["error"]

def test_install_packages_requirements_txt_not_found(client, project):
    """Test /api/install_packages when requirements.txt is not found."""
    # Remove the default requirements.txt created by the project fixture
    os.remove(os.path.join(project, "requirements.txt"))

    with client.session_transaction() as sess:
        sess['project_path'] = project

    response = client.post('/api/install_packages')
    assert response.status_code == 404 # Not Found
    data = json.loads(response.data)
    assert "error" in data
    assert "requirements.txt not found" in data["error"]

@patch('subprocess.run')
def test_install_packages_success(mock_subprocess_run, client, project):
    """Test successful package installation."""
    # Mock pip upgrade and install to return success
    mock_pip_upgrade_result = MagicMock()
    mock_pip_upgrade_result.returncode = 0
    mock_pip_upgrade_result.stdout = "pip upgraded successfully"
    mock_pip_upgrade_result.stderr = ""

    mock_install_result = MagicMock()
    mock_install_result.returncode = 0
    mock_install_result.stdout = "Successfully installed requests"
    mock_install_result.stderr = ""

    # First call to subprocess.run is 'pip --version' (or similar check)
    # Second call is pip upgrade, third is pip install -r
    mock_subprocess_run.side_effect = [
        MagicMock(returncode=0, stdout="pip 20.0", stderr=""), # pip version check
        mock_pip_upgrade_result,  # pip upgrade
        mock_install_result       # pip install -r requirements.txt
    ]

    with client.session_transaction() as sess:
        sess['project_path'] = project

    response = client.post('/api/install_packages')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert "Successfully installed requests" in data["stdout"]

    # Check that subprocess.run was called for version, upgrade, and install
    assert mock_subprocess_run.call_count == 3
    # Check the pip install command
    install_call_args = mock_subprocess_run.call_args_list[2][0][0]
    assert "pip" in install_call_args[1] # python -m pip
    assert "install" in install_call_args
    assert "-r" in install_call_args
    assert "requirements.txt" in install_call_args

@patch('subprocess.run')
def test_install_packages_pip_install_fails(mock_subprocess_run, client, project):
    """Test package installation when pip install -r fails."""
    mock_pip_upgrade_result = MagicMock()
    mock_pip_upgrade_result.returncode = 0 # pip upgrade succeeds
    mock_pip_upgrade_result.stdout = "pip upgraded successfully"
    mock_pip_upgrade_result.stderr = ""

    mock_install_fail_result = MagicMock()
    mock_install_fail_result.returncode = 1
    mock_install_fail_result.stdout = "Some output"
    mock_install_fail_result.stderr = "Error: Could not find a version that satisfies the requirement non_existent_package"

    mock_subprocess_run.side_effect = [
        MagicMock(returncode=0, stdout="pip 20.0", stderr=""), # pip version check
        mock_pip_upgrade_result,
        mock_install_fail_result
    ]

    with client.session_transaction() as sess:
        sess['project_path'] = project

    response = client.post('/api/install_packages')

    assert response.status_code == 500 # Internal Server Error (as per blueprint)
    data = json.loads(response.data)
    assert data["success"] is False
    assert "Failed to install packages" in data["message"]
    assert "Error: Could not find a version that satisfies the requirement" in data["stderr"]
    assert data["exit_code"] == 1

    assert mock_subprocess_run.call_count == 3

@patch('subprocess.run')
def test_install_packages_pip_command_not_found(mock_subprocess_run, client, project):
    """Test package installation when pip command is not found."""
    # Simulate FileNotFoundError for pip --version check
    mock_subprocess_run.side_effect = FileNotFoundError("pip command not found")

    with client.session_transaction() as sess:
        sess['project_path'] = project

    response = client.post('/api/install_packages')

    assert response.status_code == 500 # As per blueprint's error handling
    data = json.loads(response.data)
    assert "error" in data # The blueprint returns {"error": ...}
    assert "pip command not found" in data["error"]

    # subprocess.run was called once for the version check
    assert mock_subprocess_run.call_count == 1

# To run these tests, you would typically use `pytest` in your terminal
# in the root directory of the "Cortex IDE" project.
# Ensure pytest and Flask are installed in your environment.

# (Existing imports and fixtures are assumed to be above this point)
# ...

@patch('subprocess.run')
def test_lint_code_success_with_issues(mock_subprocess_run, client, project):
    """Test successful linting with issues found."""
    python_code = "import os\ndef my_func():\n  print(os)\n" # Example with unused import + spacing for flake8

    # Mock pip install flake8
    mock_pip_flake8 = MagicMock()
    mock_pip_flake8.returncode = 0
    mock_pip_flake8.stdout = "flake8 installed"
    mock_pip_flake8.stderr = ""

    # Mock flake8 execution
    mock_flake8_result = MagicMock()
    mock_flake8_result.returncode = 1 # Flake8 exits 1 if issues found
    # Example output: "row,col,code,text"
    mock_flake8_result.stdout = "1,1,F401,'os' imported but unused\n2,1,E302,expected 2 blank lines, found 0"
    mock_flake8_result.stderr = ""

    # Side effect for subprocess.run:
    # 1. flake8 --version (successful, tool exists)
    # 2. flake8 command (finds issues)
    mock_subprocess_run.side_effect = [
        MagicMock(returncode=0, stdout="Flake8 version 3.9.2", stderr=""), # Flake8 version check
        mock_flake8_result # Actual flake8 linting call
    ]

    with client.session_transaction() as sess:
        sess['project_path'] = project # Linting might use project_path for temp file creation

    response = client.post('/api/lint_code', json={'code': python_code})

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert len(data["issues"]) == 2
    assert data["issues"][0]["line"] == 1
    assert data["issues"][0]["col"] == 1
    assert data["issues"][0]["code"] == "F401"
    assert "'os' imported but unused" in data["issues"][0]["message"]
    assert data["issues"][1]["line"] == 2
    assert data["issues"][1]["code"] == "E302"

    # Check subprocess calls
    assert mock_subprocess_run.call_count == 2 # version check + lint command
    version_call_args = mock_subprocess_run.call_args_list[0][0][0]
    assert "flake8" in version_call_args[1] and "--version" in version_call_args # python -m flake8 --version
    flake8_call_args = mock_subprocess_run.call_args_list[1][0][0]
    assert "flake8" in flake8_call_args[1] # python -m flake8 ...

@patch('subprocess.run')
def test_lint_code_success_no_issues_tool_exists(mock_subprocess_run, client, project):
    """Test successful linting with no issues found, tool already exists."""
    python_code = "def my_func():\n    pass\n"

    mock_flake8_version_check = MagicMock(returncode=0, stdout="Flake8 3.9.2", stderr="")
    mock_flake8_lint_result = MagicMock(returncode=0, stdout="", stderr="") # Flake8 exits 0 if no issues

    mock_subprocess_run.side_effect = [mock_flake8_version_check, mock_flake8_lint_result]

    with client.session_transaction() as sess:
        sess['project_path'] = project

    response = client.post('/api/lint_code', json={'code': python_code})

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert len(data["issues"]) == 0
    assert mock_subprocess_run.call_count == 2 # version check + lint command

@patch('subprocess.run')
def test_lint_code_installs_if_not_exists(mock_subprocess_run, client, project):
    """Test that lint_code attempts to install flake8 if not found, then lints."""
    python_code = "def my_func():\n    pass\n"

    mock_flake8_version_fail = FileNotFoundError("flake8 not found") # Simulate tool not found
    mock_pip_install_flake8 = MagicMock(returncode=0, stdout="Successfully installed flake8", stderr="")
    mock_flake8_lint_result = MagicMock(returncode=0, stdout="", stderr="") # No lint issues

    mock_subprocess_run.side_effect = [
        mock_flake8_version_fail,
        mock_pip_install_flake8,
        mock_flake8_lint_result
    ]

    with client.session_transaction() as sess:
        sess['project_path'] = project

    response = client.post('/api/lint_code', json={'code': python_code})

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert len(data["issues"]) == 0
    assert mock_subprocess_run.call_count == 3 # version check (fail) + pip install + lint command

    # Check pip install call
    pip_install_call_args = mock_subprocess_run.call_args_list[1][0][0]
    assert "pip" in pip_install_call_args[1] and "install" in pip_install_call_args and "flake8" in pip_install_call_args


def test_lint_code_no_code_provided(client, project):
    """Test lint_code when no code is provided in the request."""
    with client.session_transaction() as sess:
        sess['project_path'] = project
    response = client.post('/api/lint_code', json={})
    assert response.status_code == 400 # Bad Request
    data = json.loads(response.data)
    assert data["success"] is False
    assert "No code provided" in data["error"]

@patch('subprocess.run')
@patch('Cortex_IDE.package_manager.Path.read_text') # Patching where Path(...).read_text() is used
def test_format_code_success(mock_path_read_text, mock_subprocess_run, client, project):
    """Test successful code formatting with Black."""
    unformatted_code = "def foo():\n  print('hello world')"
    formatted_code_by_black = "def foo():\n    print(\"hello world\")\n"

    mock_black_version_check = MagicMock(returncode=0, stdout="black, version 22.3.0", stderr="")
    mock_black_format_result = MagicMock(returncode=0, stdout="", stderr="") # Black modifies file in place

    mock_subprocess_run.side_effect = [mock_black_version_check, mock_black_format_result]

    # When the endpoint tries to read the (theoretically) formatted temp file,
    # make our mock_path_read_text return the desired formatted code.
    mock_path_read_text.return_value = formatted_code_by_black

    with client.session_transaction() as sess:
        sess['project_path'] = project

    response = client.post('/api/format_code', json={'code': unformatted_code})

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert data["formatted_code"] == formatted_code_by_black

    assert mock_subprocess_run.call_count == 2 # version check + format command
    version_call_args = mock_subprocess_run.call_args_list[0][0][0]
    assert "black" in version_call_args[1] and "--version" in version_call_args
    format_call_args = mock_subprocess_run.call_args_list[1][0][0]
    assert "black" in format_call_args[1]
    mock_path_read_text.assert_called_once() # Verify the file was attempted to be read

@patch('subprocess.run')
@patch('Cortex_IDE.package_manager.Path.read_text') # Keep patching read_text for this error case too
def test_format_code_black_fails_to_parse_tool_exists(mock_path_read_text, mock_subprocess_run, client, project):
    """Test code formatting when Black fails (e.g., parsing error), tool already exists."""
    invalid_python_code = "def foo():\n print('hello world" # Syntax error

    mock_black_version_check = MagicMock(returncode=0, stdout="black, version 22.3.0", stderr="")
    mock_black_error_result = MagicMock(returncode=123, stdout="", stderr="Error: Cannot parse source file.") # Black fails

    mock_subprocess_run.side_effect = [mock_black_version_check, mock_black_error_result]

    # If black fails to parse, it might not write to the file, or write an error.
    # For this test, assume it doesn't modify or read_text returns original/empty.
    mock_path_read_text.return_value = invalid_python_code


    with client.session_transaction() as sess:
        sess['project_path'] = project

    response = client.post('/api/format_code', json={'code': invalid_python_code})

    assert response.status_code == 500
    data = json.loads(response.data)
    assert data["success"] is False
    assert "Black formatting failed" in data["error"]
    assert "Error: Cannot parse source file." in data.get("details", "")
    assert mock_subprocess_run.call_count == 2 # version check + format command (which fails)
    mock_path_read_text.assert_called_once()


@patch('subprocess.run')
@patch('Cortex_IDE.package_manager.Path.read_text')
def test_format_code_installs_if_not_exists(mock_path_read_text, mock_subprocess_run, client, project):
    """Test that format_code attempts to install black if not found, then formats."""
    unformatted_code = "def foo():\n  print('hello world')"
    formatted_code_by_black = "def foo():\n    print(\"hello world\")\n"

    mock_black_version_fail = FileNotFoundError("black not found")
    mock_pip_install_black = MagicMock(returncode=0, stdout="Successfully installed black", stderr="")
    mock_black_format_result = MagicMock(returncode=0, stdout="", stderr="") # Black formats successfully

    mock_subprocess_run.side_effect = [
        mock_black_version_fail,
        mock_pip_install_black,
        mock_black_format_result
    ]
    mock_path_read_text.return_value = formatted_code_by_black

    with client.session_transaction() as sess:
        sess['project_path'] = project

    response = client.post('/api/format_code', json={'code': unformatted_code})

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert data["formatted_code"] == formatted_code_by_black
    assert mock_subprocess_run.call_count == 3 # version check (fail) + pip install + format command

    pip_install_call_args = mock_subprocess_run.call_args_list[1][0][0]
    assert "pip" in pip_install_call_args[1] and "install" in pip_install_call_args and "black" in pip_install_call_args
    mock_path_read_text.assert_called_once()


def test_format_code_no_code_provided(client, project):
    """Test format_code when no code is provided."""
    with client.session_transaction() as sess:
        sess['project_path'] = project
    response = client.post('/api/format_code', json={})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data["success"] is False
    assert "No code provided" in data["error"]

# (Ensure these tests are appended to the existing test_package_manager.py file)
