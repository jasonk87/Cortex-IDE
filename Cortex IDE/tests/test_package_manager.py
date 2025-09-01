import os
import shutil
import tempfile
import pytest
import json
from unittest.mock import patch, MagicMock

# Adjust the path to import app and other necessary modules from Cortex IDE
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    temp_workspaces_dir = tempfile.mkdtemp()
    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "PROJECTS_BASE_DIR": temp_workspaces_dir,
    })
    yield flask_app
    shutil.rmtree(temp_workspaces_dir)

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def project(app, client):
    """Creates a temporary project for testing and puts it in the session."""
    project_name = "test_project"
    base_dir = app.config["PROJECTS_BASE_DIR"]
    project_path = os.path.join(base_dir, project_name)
    os.makedirs(project_path, exist_ok=True)

    with open(os.path.join(project_path, "requirements.txt"), "w") as f:
        f.write("requests==2.25.1\n")

    # Set project_path in session for the test client
    with client.session_transaction() as sess:
        sess['project_path'] = project_path

    return project_path

def test_install_packages_no_project_in_session(client):
    """Test /api/install_packages when no project is in session."""
    # Ensure no project_path in session
    with client.session_transaction() as sess:
        sess.pop('project_path', None)
    response = client.post('/api/install_packages')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert "No active project session" in data["error"]

def test_install_packages_requirements_txt_not_found(client, project):
    """Test /api/install_packages when requirements.txt is not found."""
    os.remove(os.path.join(project, "requirements.txt"))
    response = client.post('/api/install_packages')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert "requirements.txt not found" in data["error"]

@patch('subprocess.run')
def test_install_packages_success(mock_subprocess_run, client, project):
    """Test successful package installation."""
    mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")
    response = client.post('/api/install_packages')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert "Success" in data["stdout"]

@patch('subprocess.run')
def test_install_packages_pip_install_fails(mock_subprocess_run, client, project):
    """Test package installation failure."""
    mock_subprocess_run.side_effect = [
        MagicMock(returncode=0), # pip version check
        MagicMock(returncode=0), # pip upgrade
        MagicMock(returncode=1, stdout="Failure", stderr="Error") # pip install
    ]
    response = client.post('/api/install_packages')
    assert response.status_code == 500
    data = json.loads(response.data)
    assert data["success"] is False
    assert "Failed to install packages" in data["message"]

@patch('package_manager._internal_lint_code')
def test_lint_code_success(mock_internal_lint, client):
    """Test successful linting."""
    mock_internal_lint.return_value = {"success": True, "issues": []}
    python_code = "def my_func():\n    pass\n"
    response = client.post('/api/lint_code', json={'code': python_code})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert len(data["issues"]) == 0
    mock_internal_lint.assert_called_once_with(python_code)

@patch('package_manager._internal_lint_code')
def test_lint_code_with_issues(mock_internal_lint, client):
    """Test linting with issues found."""
    issues = [{"line": 1, "message": "test issue"}]
    mock_internal_lint.return_value = {"success": True, "issues": issues}
    response = client.post('/api/lint_code', json={'code': 'import os'})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert data["issues"] == issues

def test_lint_code_no_code_provided(client):
    """Test lint_code with no code provided."""
    response = client.post('/api/lint_code', json={})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data["success"] is False
    assert "No code provided" in data["error"]

@patch('package_manager._internal_format_code')
def test_format_code_success(mock_internal_format, client):
    """Test successful code formatting."""
    unformatted_code = "def  foo():\n  print('hello')"
    formatted_code = "def foo():\n    print(\"hello\")\n"
    mock_internal_format.return_value = {"success": True, "formatted_code": formatted_code}

    response = client.post('/api/format_code', json={'code': unformatted_code})

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert data["formatted_code"] == formatted_code
    mock_internal_format.assert_called_once_with(unformatted_code)

@patch('package_manager._internal_format_code')
def test_format_code_failure(mock_internal_format, client):
    """Test code formatting failure."""
    error_details = "Black could not parse input"
    mock_internal_format.return_value = {"success": False, "error": error_details}

    invalid_code = "def foo(:\n    print('hello')"
    response = client.post('/api/format_code', json={'code': invalid_code})

    assert response.status_code == 200 # The endpoint itself succeeds
    data = json.loads(response.data)
    assert data["success"] is False
    assert data["error"] == error_details
    mock_internal_format.assert_called_once_with(invalid_code)

def test_format_code_no_code_provided(client):
    """Test format_code with no code provided."""
    response = client.post('/api/format_code', json={})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data["success"] is False
    assert "No code provided" in data["error"]
