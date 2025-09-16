import pytest
import sys
import os
import json
import shutil
import zipfile
import io

# Add the parent directory to the sys.path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app as flask_app


@pytest.fixture(autouse=True)
def change_test_dir(monkeypatch):
    """Change the CWD to the app's root directory for the test session."""
    monkeypatch.chdir("Cortex IDE")


@pytest.fixture
def app():
    flask_app.config.update(
        {
            "TESTING": True,
        }
    )
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def test_project(client):
    """Fixture to create a test project and clean it up."""
    project_name = "test_api_project"
    project_path = os.path.join("workspaces", project_name)

    # Clean up before test
    if os.path.exists(project_path):
        shutil.rmtree(project_path)

    # Start the project via the API
    client.post("/api/start_project", json={"name": project_name})

    yield project_name, project_path

    # Cleanup after test
    if os.path.exists(project_path):
        shutil.rmtree(project_path)


def test_index(client):
    """Test the index route."""
    res = client.get("/")
    assert res.status_code == 200
    assert b"Cortex IDE" in res.data


def test_start_project(client):
    """Test starting a new project."""
    project_name = "test_project_start"
    project_path = os.path.join("workspaces", project_name)

    if os.path.exists(project_path):
        shutil.rmtree(project_path)

    res = client.post("/api/start_project", json={"name": project_name})
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["message"] == f"Project “{project_name}” created."
    assert data["project_path"] == project_path.replace("\\", "/")
    assert os.path.isdir(project_path)

    res_no_name = client.post("/api/start_project", json={"name": ""})
    assert res_no_name.status_code == 400
    data_no_name = json.loads(res_no_name.data)
    assert "error" in data_no_name
    assert data_no_name["error"] == "Project name required"

    if os.path.exists(project_path):
        shutil.rmtree(project_path)


def test_get_files_empty(client, test_project):
    """Test the /api/files endpoint with an empty project."""
    project_name, _ = test_project
    res = client.get("/api/files")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["name"] == project_name
    assert data["children"] == []


def test_create_and_get_files(client, test_project):
    """Test creating a file and then listing it."""
    _, project_path = test_project
    filename = "new_test_file.txt"

    res_create = client.post("/api/create_file", json={"filename": filename})
    assert res_create.status_code == 200
    assert os.path.exists(os.path.join(project_path, filename))

    res_get = client.get("/api/files")
    assert res_get.status_code == 200
    data = json.loads(res_get.data)
    assert len(data["children"]) == 1
    assert data["children"][0]["name"] == filename

    res_existing = client.post("/api/create_file", json={"filename": filename})
    assert res_existing.status_code == 409


def test_get_file_content(client, test_project):
    """Test getting file content."""
    _, project_path = test_project
    filename = "file_to_read.txt"
    content = "Hello, this is the content."

    with open(os.path.join(project_path, filename), "w") as f:
        f.write(content)

    res = client.post("/api/get_file_content", json={"filename": filename})
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["content"] == content
    assert data["filename"] == filename

    res_not_found = client.post(
        "/api/get_file_content", json={"filename": "nonexistent.txt"}
    )
    assert res_not_found.status_code == 404


def test_save_file_content(client, test_project):
    """Test saving content to a file."""
    _, project_path = test_project
    filename = "file_to_save.txt"
    initial_content = "Initial content."
    updated_content = "Updated content."

    file_path = os.path.join(project_path, filename)
    with open(file_path, "w") as f:
        f.write(initial_content)

    res = client.post(
        "/api/save_file_content",
        json={"filename": filename, "content": updated_content},
    )
    assert res.status_code == 200

    with open(file_path, "r") as f:
        content = f.read()
    assert content == updated_content


def test_delete_file(client, test_project):
    """Test deleting a file."""
    _, project_path = test_project
    filename = "file_to_delete.txt"
    file_path = os.path.join(project_path, filename)

    with open(file_path, "w") as f:
        f.write("delete me")
    assert os.path.exists(file_path)

    res = client.post("/api/delete_file", json={"filename": filename})
    assert res.status_code == 200
    assert not os.path.exists(file_path)

    res_not_found = client.post("/api/delete_file", json={"filename": filename})
    assert res_not_found.status_code == 404


def test_create_and_delete_folder(client, test_project):
    """Test creating and deleting a folder."""
    _, project_path = test_project
    folder_name = "new_test_folder"
    folder_path = os.path.join(project_path, folder_name)

    res_create = client.post("/api/create_folder", json={"path": folder_name})
    assert res_create.status_code == 200
    assert os.path.isdir(folder_path)

    res_existing = client.post("/api/create_folder", json={"path": folder_name})
    assert res_existing.status_code == 409

    res_delete = client.post("/api/delete_folder", json={"path": folder_name})
    assert res_delete.status_code == 200
    assert not os.path.exists(folder_path)


def test_execute_code(client, test_project):
    """Test the /api/execute_code endpoint."""
    project_name, project_path = test_project

    # Test successful execution
    code = "import sys; print('hello'); print('world', file=sys.stderr)"
    res_success = client.post("/api/execute_code", json={"code": code})
    assert res_success.status_code == 200
    data_success = json.loads(res_success.data)
    assert data_success["stdout"].strip() == "hello"
    assert data_success["stderr"].strip() == "world"
    assert data_success["exit_code"] == 0

    # Test execution with an error
    error_code = "import non_existent_module"
    res_error = client.post("/api/execute_code", json={"code": error_code})
    assert res_error.status_code == 200
    data_error = json.loads(res_error.data)
    assert "ModuleNotFoundError" in data_error["stderr"]
    assert data_error["exit_code"] != 0


def test_download_project(client, test_project):
    """Test downloading the project as a zip file."""
    project_name, project_path = test_project

    # Add a file to the project to check for in the zip
    test_filename = "download_test_file.txt"
    with open(os.path.join(project_path, test_filename), "w") as f:
        f.write("test content")

    res = client.get("/api/download_project")
    assert res.status_code == 200
    assert res.headers["Content-Type"] == "application/zip"
    assert "attachment; filename=" in res.headers["Content-Disposition"]
    assert f"{project_name}.zip" in res.headers["Content-Disposition"]

    # Check the contents of the zip file
    zip_file = zipfile.ZipFile(io.BytesIO(res.data))
    assert f"{test_filename}" in zip_file.namelist()
    with zip_file.open(test_filename) as f:
        content = f.read()
        assert content == b"test content"
