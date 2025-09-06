import pytest
import os
import sys
from unittest.mock import patch, MagicMock

# Adjust the path to import MemoryManager from the parent directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from memory_manager import MemoryManager

# Define a dummy project path for testing
DUMMY_PROJECT_PATH = "/tmp/dummy_project_for_memory_test"

@pytest.fixture(autouse=True)
def setup_teardown():
    """Ensure the dummy project path exists and is clean for each test."""
    os.makedirs(DUMMY_PROJECT_PATH, exist_ok=True)
    yield
    # Clean up dummy directory if needed, but PersistentClient is mocked, so no files are created.

@patch('memory_manager.embedding_functions.SentenceTransformerEmbeddingFunction')
@patch('memory_manager.chromadb.PersistentClient')
def test_memory_manager_initialization(mock_persistent_client, mock_embedding_function):
    """
    Tests that MemoryManager initializes correctly, creating a client and a collection
    with the correct embedding function.
    """
    # Arrange
    mock_collection = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_instance.get_or_create_collection.return_value = mock_collection
    mock_persistent_client.return_value = mock_client_instance
    mock_ef_instance = MagicMock()
    mock_embedding_function.return_value = mock_ef_instance

    # Act
    manager = MemoryManager(project_path=DUMMY_PROJECT_PATH)

    # Assert
    mock_persistent_client.assert_called_once_with(path=os.path.join(DUMMY_PROJECT_PATH, ".cortex_memory"))
    mock_embedding_function.assert_called_once_with(model_name="all-MiniLM-L6-v2")
    mock_client_instance.get_or_create_collection.assert_called_once_with(
        name="project_memories",
        embedding_function=mock_ef_instance
    )
    assert manager.collection is mock_collection

@patch('memory_manager.embedding_functions.SentenceTransformerEmbeddingFunction')
@patch('memory_manager.chromadb.PersistentClient')
def test_add_memory(mock_persistent_client, mock_embedding_function):
    """
    Tests that adding a memory calls the collection's add method correctly.
    """
    # Arrange
    mock_collection = MagicMock()
    mock_collection.get.return_value = {'ids': []} # Simulate memory not existing
    mock_client_instance = MagicMock()
    mock_client_instance.get_or_create_collection.return_value = mock_collection
    mock_persistent_client.return_value = mock_client_instance

    manager = MemoryManager(project_path=DUMMY_PROJECT_PATH)

    memory_text = "This is a new memory."

    # Act
    manager.add_memory(memory_text)

    # Assert
    mock_collection.add.assert_called_once()
    # Check that the call to 'add' had the correct arguments
    args, kwargs = mock_collection.add.call_args
    assert 'documents' in kwargs and memory_text in kwargs['documents']
    assert 'ids' in kwargs and len(kwargs['ids']) == 1


@patch('memory_manager.embedding_functions.SentenceTransformerEmbeddingFunction')
@patch('memory_manager.chromadb.PersistentClient')
def test_add_duplicate_memory(mock_persistent_client, mock_embedding_function):
    """
    Tests that adding a duplicate memory does not result in a new call to `add`.
    """
    # Arrange
    memory_text = "This is a duplicate memory."
    import hashlib
    doc_id = hashlib.sha256(memory_text.encode()).hexdigest()

    mock_collection = MagicMock()
    mock_collection.get.return_value = {'ids': [doc_id]} # Simulate memory already existing
    mock_client_instance = MagicMock()
    mock_client_instance.get_or_create_collection.return_value = mock_collection
    mock_persistent_client.return_value = mock_client_instance

    manager = MemoryManager(project_path=DUMMY_PROJECT_PATH)

    # Act
    manager.add_memory(memory_text)

    # Assert
    mock_collection.get.assert_called_once_with(ids=[doc_id])
    mock_collection.add.assert_not_called()


@patch('memory_manager.embedding_functions.SentenceTransformerEmbeddingFunction')
@patch('memory_manager.chromadb.PersistentClient')
def test_search_memories(mock_persistent_client, mock_embedding_function):
    """
    Tests that searching for memories calls the collection's query method.
    """
    # Arrange
    query_text = "What was the memory?"
    search_results = {'documents': [['This is a relevant memory.']]}

    mock_collection = MagicMock()
    mock_collection.query.return_value = search_results
    mock_client_instance = MagicMock()
    mock_client_instance.get_or_create_collection.return_value = mock_collection
    mock_persistent_client.return_value = mock_client_instance

    manager = MemoryManager(project_path=DUMMY_PROJECT_PATH)

    # Act
    results = manager.search_memories(query_text, n_results=1)

    # Assert
    mock_collection.query.assert_called_once_with(query_texts=[query_text], n_results=1)
    assert results == search_results['documents'][0]
