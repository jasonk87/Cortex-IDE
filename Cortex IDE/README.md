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
*   **Code Linting**: Automatic linting for Python files using Flake8 to help identify errors and style issues.
*   **Code Formatting**: Format Python code using Black with a dedicated "Format" button.

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

## Code Linting

Cortex IDE provides automatic code linting for Python files using Flake8. This helps you identify potential errors, style issues, and anti-patterns in your code as you type.

*   **How it Works**: When you are editing a Python file, linting suggestions will automatically appear in the editor. Issues are typically indicated by markers in the gutter and underlining of the relevant code. Hovering over these markers or underlined code may provide more details about the issue.
*   **Underlying Tool**: Linting is performed by Flake8. The IDE calls a backend service that runs Flake8 on your code.
*   **Benefits**: Helps improve code quality, catch errors early, and maintain consistent style.

## Code Formatting

You can automatically format your Python code using Black, a popular opinionated code formatter.

1.  **Open a Python File**: Ensure the Python file you want to format is open in the editor.
2.  **Click the "Format" Button**: Locate the "Format" button in the file viewer panel (typically next to the "Save" and "Run" buttons).
3.  **Automatic Formatting**: Clicking this button will send your code to a backend service that uses Black to reformat it. The code in your editor will then be updated with the Black-formatted version.
4.  **Save Changes**: Remember to save the file if you are happy with the formatted code.
*   **Note**: If you click "Format" for a non-Python file, a warning will appear in the logs, and no formatting action will be taken.

## Agent Interaction

*   Use the chat interface to send messages or instructions to the AI agent.
*   The agent can help with generating code, explaining concepts, or performing tasks within the project.
*   Agent logs, plans, and execution results are displayed in the "Agent Logs" panel.

---

Happy Coding!
