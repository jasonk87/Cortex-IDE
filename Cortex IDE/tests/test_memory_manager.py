import os
import pytest
from pathlib import Path
import sys
import re
from unittest.mock import patch, MagicMock

# Add the parent directory to the sys.path to allow imports from the main app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory_manager import MemoryManager

@patch('memory_manager.chromadb.PersistentClient')
def test_windows_path_sanitization(mock_persistent_client):
    """
    Tests that a Windows-style path with backslashes is correctly sanitized.
    """
    # Arrange: Configure the mock to behave like the real object
    mock_collection = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_instance.get_or_create_collection.return_value = mock_collection
    mock_persistent_client.return_value = mock_client_instance

    # Act: Create an instance of MemoryManager, which will use the mock
    windows_path = "workspaces\\my_test_project"
    manager = MemoryManager(project_path=windows_path)

    # Assert: Check that the collection name was sanitized correctly
    expected_name = "project_workspaces_my_test_project"
    mock_client_instance.get_or_create_collection.assert_called_once_with(name=expected_name)
    assert manager.collection_name == expected_name

@patch('memory_manager.chromadb.PersistentClient')
def test_path_sanitization_with_various_chars(mock_persistent_client):
    """
    Tests sanitization with a mix of invalid characters.
    """
    # Arrange
    mock_collection = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_instance.get_or_create_collection.return_value = mock_collection
    mock_persistent_client.return_value = mock_client_instance

    # Act
    messy_path = "project / path \\ with@#$invalid chars"
    manager = MemoryManager(project_path=messy_path)

    # Assert
    expected_sanitized_part = re.sub(r'[^a-zA-Z0-9._-]', '_', messy_path)
    expected_sanitized_part = expected_sanitized_part[:50] # Match the truncation logic
    expected_name = f"project_{expected_sanitized_part}"

    mock_client_instance.get_or_create_collection.assert_called_once_with(name=expected_name)
    assert manager.collection_name == expected_name
