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
        f.write("requests==2.25.1
")

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
