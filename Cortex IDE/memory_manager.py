import chromadb
import uuid

class MemoryManager:
    def __init__(self, project_path):
        """
        Initializes the MemoryManager for a specific project.
        """
        # Each project will have its own ChromaDB collection.
        # The database itself is stored in a persistent directory.
        self.client = chromadb.PersistentClient(path="./cortex_memory")
        self.collection_name = f"project_{project_path.replace('/', '_').replace(' ', '_')}"
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def add_memory(self, text_content: str, metadata: dict = None):
        """
        Adds a new memory (e.g., a summary of a successful task) to the collection.
        """
        if not text_content:
            return

        # ChromaDB requires a unique ID for each entry.
        doc_id = str(uuid.uuid4())

        self.collection.add(
            documents=[text_content],
            metadatas=[metadata] if metadata else None,
            ids=[doc_id]
        )
        print(f"Added memory to collection '{self.collection_name}'.")

    def search_memories(self, query_text: str, n_results: int = 3) -> list:
        """
        Searches for memories relevant to a given query text.
        """
        if not query_text:
            return []

        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results
        )

        # The query returns a list of lists, one for each query text.
        # Since we only have one query, we take the first element.
        return results['documents'][0] if results and results['documents'] else []

# Example Usage (for testing purposes)
if __name__ == '__main__':
    # This would be run in the context of a project
    project_memory = MemoryManager(project_path="workspaces/sample_project")

    # Example of adding memories
    project_memory.add_memory("The agent successfully refactored the database connection string in `config.py`.", metadata={"source": "task_123"})
    project_memory.add_memory("A common error when installing `numpy` on this system is a missing BLAS library.", metadata={"source": "task_456"})
    project_memory.add_memory("The user prefers functions to be documented using Google-style docstrings.", metadata={"source": "conversation_789"})

    # Example of searching memories
    search_query = "How should I document a new function?"
    relevant_memories = project_memory.search_memories(search_query)

    print(f"Query: '{search_query}'")
    print("Found relevant memories:")
    for memory in relevant_memories:
        print(f"- {memory}")
