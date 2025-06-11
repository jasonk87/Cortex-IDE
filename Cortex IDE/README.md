# Cortex IDE

Cortex IDE is a web-based development environment for Python projects. It allows users to manage files, edit code, and run Python applications directly in the browser. It also features an interactive agent to assist with development tasks.

## Features

*   **Project Management**: Create and manage projects within isolated workspaces.
*   **File Explorer**: View, create, edit, and delete files and folders within your project.
*   **Code Editor**: A web-based code editor with syntax highlighting (powered by CodeMirror).
*   **Python Code Execution**: Run Python scripts and see their output.
*   **Agent Interaction**: Chat with an AI agent to help with coding tasks.
*   **Download Project**: Download the entire project as a .zip file.
*   **Dependency Management**: Manage Python package dependencies for your projects.

## Getting Started

1.  **Start a New Project**:
    *   Open the Cortex IDE in your web browser.
    *   Enter a name for your new project in the input field and click "Start New Project".

2.  **File Management**:
    *   Use the "Project Files" panel on the left to manage your project's files and folders.
    *   You can create new files (e.g., `main.py`, `utils.py`) or new folders.
    *   Click on a file to open it in the editor.
    *   Save changes using the "Save" button above the editor.

3.  **Running Code**:
    *   Open a Python file (e.g., `main.py`).
    *   Click the "Run" button above the editor to execute the current script.
    *   Output and errors will be displayed in the terminal panel below the editor or in the Agent Logs.

## Dependency Management

Cortex IDE supports managing Python package dependencies using a `requirements.txt` file.

1.  **Create `requirements.txt`**:
    *   In the "Project Files" panel, create a new file named `requirements.txt` in the root directory of your project.
    *   Add your project's dependencies to this file, one package per line, optionally specifying versions (e.g., `requests==2.25.1`, `flask>=2.0`).

2.  **Install Dependencies**:
    *   Once your `requirements.txt` file is saved, click the "Install Dependencies" button located in the "Project Files" panel (below the "Create Folder" button).
    *   The IDE will run `pip install -r requirements.txt` for your project.
    *   Progress and results of the installation will be displayed in the "Agent Logs" panel.
    *   Any necessary packages will be installed into the environment used by the code runner for your project.

3.  **Using Installed Packages**:
    *   After successful installation, you can import and use the installed packages in your Python scripts within the project.

## Agent Interaction

*   Use the chat interface to send messages or instructions to the AI agent.
*   The agent can help with generating code, explaining concepts, or performing tasks within the project.
*   Agent logs, plans, and execution results are displayed in the "Agent Logs" panel.

---

Happy Coding!
