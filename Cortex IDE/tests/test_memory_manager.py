import pytest
from unittest.mock import patch, MagicMock
import sys
import os
import hashlib

# Add the parent directory (Cortex IDE) to sys.path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from memory_manager import MemoryManager

@pytest.fixture
def patched_memory_manager():
    """
    A fixture that patches ChromaDB and the embedding function,
    initializes MemoryManager, and yields the instance and its mock collection.
    """
    with patch('chromadb.PersistentClient') as mock_client_constructor, \
         patch('chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction') as mock_embedding_constructor:

        # Setup mock instances
        mock_client_instance = MagicMock()
        mock_collection = MagicMock()
        mock_embedding_instance = MagicMock()

        # Configure mock constructors to return our instances
        mock_client_constructor.return_value = mock_client_instance
        mock_embedding_constructor.return_value = mock_embedding_instance

        # Configure the mock client to return our mock collection
        mock_client_instance.get_or_create_collection.return_value = mock_collection

        # The object under test is created here, while patches are active
        project_path = "/tmp/test_project"
        memory_manager = MemoryManager(project_path)

        # Yield the necessary objects for the tests
        yield memory_manager, mock_collection, mock_client_constructor, mock_embedding_constructor, project_path

def test_memory_manager_initialization(patched_memory_manager):
    """Test that MemoryManager initializes its dependencies correctly."""
    _, _, mock_client_constructor, mock_embedding_constructor, project_path = patched_memory_manager

    # Check that PersistentClient was called with the correct path
    mock_client_constructor.assert_called_once_with(path=os.path.join(project_path, ".cortex_memory"))

    # Check that SentenceTransformerEmbeddingFunction was initialized
    mock_embedding_constructor.assert_called_once_with(model_name="all-MiniLM-L6-v2")

    # Check that get_or_create_collection was called correctly
    mock_client = mock_client_constructor.return_value
    mock_embedding_fn = mock_embedding_constructor.return_value
    mock_client.get_or_create_collection.assert_called_once_with(
        name="project_memories",
        embedding_function=mock_embedding_fn
    )

def test_add_new_memory(patched_memory_manager):
    """Test adding a new, unique memory."""
    memory_manager, mock_collection, _, _, _ = patched_memory_manager

    # Simulate that the memory does not exist
    mock_collection.get.return_value = {'ids': []}

    text_to_add = "This is a new memory."
    memory_manager.add_memory(text_to_add)

    # Verify it was added
    doc_id = hashlib.sha256(text_to_add.encode()).hexdigest()
    mock_collection.add.assert_called_once_with(
        documents=[text_to_add],
        ids=[doc_id]
    )

def test_add_existing_memory(patched_memory_manager):
    """Test that an existing memory is not added again."""
    memory_manager, mock_collection, _, _, _ = patched_memory_manager

    text_to_add = "This is an existing memory."
    doc_id = hashlib.sha256(text_to_add.encode()).hexdigest()

    # Simulate that the memory already exists
    mock_collection.get.return_value = {'ids': [doc_id]}

    memory_manager.add_memory(text_to_add)

    # Verify that 'add' was not called
    mock_collection.add.assert_not_called()

def test_search_memories(patched_memory_manager):
    """Test searching for memories."""
    memory_manager, mock_collection, _, _, _ = patched_memory_manager

    query_text = "What is the memory about?"
    expected_results = ["doc1", "doc2"]

    # Configure the mock query result
    mock_collection.query.return_value = {
        'documents': [expected_results]
    }

    results = memory_manager.search_memories(query_text, n_results=2)

    # Verify the query was made correctly
    mock_collection.query.assert_called_once_with(
        query_texts=[query_text],
        n_results=2
    )

    # Verify the results are correct
    assert results == expected_results

def test_search_memories_no_results(patched_memory_manager):
    """Test searching when no results are found."""
    memory_manager, mock_collection, _, _, _ = patched_memory_manager

    query_text = "A query that finds nothing."

    # Configure the mock query result for no documents
    mock_collection.query.return_value = {'documents': []}

    results = memory_manager.search_memories(query_text)

    assert results == []
