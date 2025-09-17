import chromadb
from chromadb.utils import embedding_functions
import os

class MemoryManager:
    def __init__(self, project_path):
        self.db_path = os.path.join(project_path, ".cortex_memory")
        self.client = chromadb.PersistentClient(path=self.db_path)

        # Using the SentenceTransformer a a more reliable embedding function
        # This avoids the onnxruntime dependency that causes issues on Windows.
        # The model name is the same as the default, so behavior is consistent.
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        self.collection = self.client.get_or_create_collection(
            name="project_memories",
            embedding_function=self.embedding_function
        )

    def add_memory(self, text: str):
        """Adds a new memory to the collection."""
        # Use a hash of the text as a simple, deterministic ID
        import hashlib
        doc_id = hashlib.sha256(text.encode()).hexdigest()

        # Check if a document with this ID already exists
        if self.collection.get(ids=[doc_id])['ids']:
            # If it exists, you might want to update it or just skip adding.
            # For simplicity, we'll skip.
            return

        self.collection.add(
            documents=[text],
            ids=[doc_id]
        )

    def search_memories(self, query: str, n_results: int = 5):
        """Searches for memories similar to the query."""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        return results['documents'][0] if results and results['documents'] else []
