import chromadb
import uuid
import re

class MemoryManager:
    def __init__(self, project_path):
        """
        Initializes the MemoryManager for a specific project.
        """
        self.client = chromadb.PersistentClient(path="./cortex_memory")

        # Sanitize the project_path to create a valid collection name
        # ChromaDB requires names to be 3-63 chars, start/end with alphanum, and only contain alphanum, _, -
        sanitized_path = re.sub(r'[^a-zA-Z0-9._-]', '_', project_path)
        # Ensure the name is not too long and doesn't start/end with invalid chars
        if len(sanitized_path) > 50:
            sanitized_path = sanitized_path[:50]
        if sanitized_path.startswith(('_', '.', '-')):
            sanitized_path = 'p' + sanitized_path[1:]
        if sanitized_path.endswith(('_', '.', '-')):
            sanitized_path = sanitized_path[:-1] + 'p'

        self.collection_name = f"project_{sanitized_path}"
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def add_memory(self, text_content: str, metadata: dict = None):
        """
        Adds a new memory (e.g., a summary of a successful task) to the collection.
        """
        if not text_content:
            return

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

        return results['documents'][0] if results and results['documents'] else []

# Example Usage (for testing purposes)
if __name__ == '__main__':
    project_memory = MemoryManager(project_path="workspaces/sample_project")
    project_memory_win = MemoryManager(project_path="workspaces\\sample_project_win")

    print(f"Unix-style path collection name: {project_memory.collection_name}")
    print(f"Windows-style path collection name: {project_memory_win.collection_name}")

    project_memory.add_memory("Test memory for unix path.")
    project_memory_win.add_memory("Test memory for windows path.")

    print("\nSearching for 'unix':")
    print(project_memory.search_memories("unix"))

    print("\nSearching for 'windows':")
    print(project_memory_win.search_memories("windows"))
