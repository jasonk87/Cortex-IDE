# tools.py
import os
import re
import ast
from pathlib import Path
from typing import Dict, List, Any
import subprocess
from pathlib import Path
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent  # root of the workspace

def get_safe_path(project_path, filename):
    """Ensures file paths are safe, sanitized, and within the project directory."""
    if not project_path:
        raise Exception("No active project selected")
    
    # Sanitize the filename to prevent directory traversal and other attacks
    safe_filename = secure_filename(filename)
    if not safe_filename:
        raise Exception("Invalid filename provided")

    file_path = os.path.join(project_path, safe_filename)
    normalized_path = os.path.normpath(file_path)

    # Final check to ensure the path is within the project directory
    if not normalized_path.startswith(os.path.normpath(project_path)):
        raise PermissionError("Access denied: File path is outside of the project directory.")
    
    return normalized_path

def _compress_blank_lines(text: str, max_run: int = 2) -> str:
    """
    Collapse any run of > `max_run` consecutive new-lines to exactly `max_run`.
    Also strips trailing blank lines.
    """
    text = re.sub(r'\n{'+str(max_run+1)+r',}', '\n'*max_run, text)
    return text.rstrip() + '\n'   # keep exactly one final newline

# Define the parser class that walks the Abstract Syntax Tree
class PythonCodeParser(ast.NodeVisitor):
    """
    A NodeVisitor to traverse the AST of a Python file and extract key components.
    It identifies imports, top-level functions, and classes with their methods.
    """
    def __init__(self):
        self.imports = set()
        self.functions = []
        self.classes = {}

    def visit_Import(self, node: ast.Import):
        """Extracts standard imports like 'import os'."""
        for alias in node.names:
            self.imports.add(alias.name.split('.')[0]) # Get the top-level package
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Extracts 'from' imports like 'from pathlib import Path'."""
        if node.module:
            self.imports.add(node.module.split('.')[0]) # Get the top-level package
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Extracts top-level functions, ignoring methods within classes."""
        # This check ensures we only capture top-level functions.
        # The `ast.walk` in the main function starts at the module level.
        # We can refine this by checking the parent node if needed, but for
        # a direct `visit` call on a module tree, this works.
        args = [a.arg for a in node.args.args]
        self.functions.append(f"{node.name}({', '.join(args)})")
        # Do not traverse further into functions to avoid capturing nested functions.

    def visit_ClassDef(self, node: ast.ClassDef):
        """Extracts classes and their methods."""
        class_name = node.name
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method_args = [a.arg for a in item.args.args]
                methods.append(f"{item.name}({', '.join(method_args)})")
        self.classes[class_name] = methods
        # Do not traverse further into classes.

def generate_code_map(project_path: str, *args, **kwargs) -> str:
    """
    Scans the project directory, parses all Python files, and generates a
    comprehensive markdown-formatted map of the entire project structure,
    including file tree, dependencies, classes, and functions.

    This function uses Python's Abstract Syntax Tree (AST) module to ensure
    accurate and safe parsing of code components.
    """
    project_path_obj = Path(project_path).resolve()
    if not project_path_obj.is_dir():
        return "Error: The provided path is not a valid directory."

    code_map = {}
    file_tree_lines = []
    
    # Common directories to exclude from the scan
    exclude_dirs = {'__pycache__', '.git', '.idea', 'venv', '.venv', 'env', 'node_modules'}

    for root, dirs, files in os.walk(project_path_obj, topdown=True):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        current_path = Path(root)
        relative_path = current_path.relative_to(project_path_obj)
        level = len(relative_path.parts)
        
        indent = '    ' * level
        dir_name = current_path.name if str(relative_path) != '.' else project_path_obj.name
        file_tree_lines.append(f"{indent}📁 {dir_name}/")

        file_indent = '    ' * (level + 1)
        for name in sorted(files):
            file_tree_lines.append(f"{file_indent}📄 {name}")
            
            if name.endswith('.py'):
                file_path = current_path / name
                relative_file_path = str(file_path.relative_to(project_path_obj))
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        source_code = f.read()
                    
                    tree = ast.parse(source_code, filename=name)
                    parser = PythonCodeParser()
                    # We only visit the top-level nodes of the module
                    for node in ast.iter_child_nodes(tree):
                         parser.visit(node)
                    
                    code_map[relative_file_path] = {
                        "imports": sorted(list(parser.imports)),
                        "functions": sorted(parser.functions),
                        "classes": {k: sorted(v) for k, v in sorted(parser.classes.items())}
                    }
                except Exception as e:
                    code_map[relative_file_path] = {"error": f"Could not parse file: {e}"}

    # --- Format the final markdown output ---
    output_md = "# Project Code Map\n\n"

    output_md += "## File Tree\n```\n"
    output_md += "\n".join(file_tree_lines)
    output_md += "\n```\n\n"
    
    output_md += "## Code Structure Analysis\n"
    if not code_map:
        output_md += "No Python files were found or parsed in the project.\n"
    else:
        for file_path, data in sorted(code_map.items()):
            output_md += f"### `{file_path}`\n"
            if "error" in data:
                output_md += f"- **Error:** {data['error']}\n"
                continue

            if not data["imports"] and not data["classes"] and not data["functions"]:
                 output_md += "- *No classes, functions, or imports found.*\n"
                 continue

            if data["imports"]:
                output_md += "- **Imports:** `" + "`, `".join(data["imports"]) + "`\n"
            if data["classes"]:
                output_md += "- **Classes:**\n"
                for class_name, methods in data["classes"].items():
                    output_md += f"  - **`{class_name}`**:\n"
                    if methods:
                        for method in methods:
                            output_md += f"    - `{method}`\n"
                    else:
                        output_md += f"    - *(No methods defined)*\n"
            if data["functions"]:
                output_md += "- **Functions:**\n"
                for func in data["functions"]:
                    output_md += f"  - `{func}`\n"
            output_md += "\n"
            
    return output_md.strip()

def save_file(project_path: str, filename: str, content: str) -> str:
    """Saves content to a file in the project directory."""
    try:
        file_path = get_safe_path(project_path, filename)

        # ---- NEW: anti-wall safeguard ------------------------------------
        if len(content) > 10_000 or content.count('\n')/max(len(content),1) > 0.3:
            content = _compress_blank_lines(content)
        # ------------------------------------------------------------------

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully saved file: {os.path.basename(file_path)}"
    except Exception as e:
        return f"Error saving file '{filename}': {e}"


def delete_file(project_path: str, filename: str) -> str:
    """Deletes a file from the project directory."""
    try:
        file_path = get_safe_path(project_path, filename)
        if not os.path.exists(file_path):
            return f"Error: File '{os.path.basename(file_path)}' not found."
        os.remove(file_path)
        return f"Successfully deleted file: {os.path.basename(file_path)}"
    except Exception as e:
        return f"Error deleting file '{filename}': {e}"

# -----------------------------------------------------------------
# Re-plan signal
# -----------------------------------------------------------------
def replan(project_path: str, reason: str) -> str:
    """
    Called by the agent when its current plan fails or needs revision.
    Returns a simple text token the caller can interpret.
    """
    return f"REPLAN_REQUESTED: {reason}"


# -----------------------------------------------------------------
# Sub-task creator
# -----------------------------------------------------------------
import time
def create_subtask(project_path: str, description: str) -> str:
    """
    Spawn a follow-up task for the agent to tackle later.
    In a real system you’d enqueue this; here we just return an ID.
    """
    subtask_id = f"task_{int(time.time())}"
    # TODO: push (subtask_id, description) onto your queue/store.
    return f"SUBTASK_CREATED: {subtask_id} — {description}"

def execute_python_file(project_path: str, filename: str, timeout: int = 10) -> str:
    """Executes a python file in the project directory with a timeout."""
    try:
        safe_filename = secure_filename(filename)
        if not os.path.exists(os.path.join(project_path, safe_filename)):
            return f"Error: File '{safe_filename}' not found."
        
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1' # Ensures output is not buffered
        
        # Use Popen for more control if needed, but run with timeout is simpler
        result = subprocess.run(
            ['python', safe_filename],
            capture_output=True, text=True, timeout=timeout,
            cwd=project_path, encoding='utf-8', env=env
        )
        return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return f"Error: Execution timed out after {timeout} seconds."
    except Exception as e:
        return f"Error executing file '{filename}': {e}"

def list_files(project_path: str) -> str:
    """Lists all files in the project directory."""
    try:
        files = [f for f in os.listdir(project_path) if os.path.isfile(os.path.join(project_path, f))]
        if not files: return "No files in the project directory."
        return "\n".join(files)
    except Exception as e:
        return f"Error listing files: {e}"

def read_file(project_path: str, filename: str) -> str:
    """Reads the full content of a file in the project directory."""
    try:
        file_path = get_safe_path(project_path, filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        # If the file doesn't exist, this line is triggered.
        return f"Error reading file '{filename}': {e}"

def finish(project_path: str, reason: str) -> None:
    """Signals that the task is complete."""
    return None

def find_line_numbers(project_path: str, filename: str, keyword: str) -> str:
    """Finds all line numbers containing a keyword in a specific file."""
    try:
        file_path = get_safe_path(project_path, filename)
        if not os.path.exists(file_path):
            return f"Error: File '{os.path.basename(filename)}' not found."
        
        found_lines = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                if keyword in line:
                    found_lines.append(str(i))
        
        if not found_lines:
            return f"Keyword '{keyword}' not found in {os.path.basename(filename)}."
        
        return f"Keyword '{keyword}' found on lines: {', '.join(found_lines)} in {os.path.basename(filename)}."
    except Exception as e:
        return f"Error searching in file '{filename}': {e}"


# tools.py
import os, re
from pathlib import Path

def search_file_content(project_path: str, keyword: str) -> str:
    """
    Recursively search every file under the given project_path (string)
    for keyword (case-insensitive). Return up to 50 matches as text.
    """
    base_dir   = Path(project_path).resolve()
    patt       = re.compile(re.escape(keyword), re.IGNORECASE)
    matches    = []

    for root, _, files in os.walk(base_dir):
        for fname in files:
            fpath = Path(root) / fname
            try:
                with fpath.open('r', encoding='utf-8', errors='ignore') as f:
                    for ln_no, line in enumerate(f, 1):
                        if patt.search(line):
                            rel = fpath.relative_to(base_dir)
                            matches.append(f"{rel}, line {ln_no}: {line.strip()}")
            except (UnicodeDecodeError, PermissionError):
                continue

    if not matches:
        return f"Keyword '{keyword}' not found in any file content in the project."
    return "Search results:\n" + "\n".join(matches[:50])

def echo(project_path: str, message: str) -> str:
    """
    A tool for the agent to communicate directly with the user.
    Use this to answer questions, provide analysis, or give updates.
    """
    return message

def read_code_chunk(project_path: str, filename: str, start_line: int, line_count: int = 50) -> str:
    """Reads a chunk of code from a specific file, starting at a given line."""
    try:
        file_path = get_safe_path(project_path, filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        start_index = start_line - 1
        end_index = start_index + line_count

        if start_index < 0 or start_index >= len(lines):
            return f"Error: start_line {start_line} is out of bounds for file {filename}."

        chunk = "".join(lines[start_index:end_index])
        return f"--- Code from {filename} (lines {start_line}-{end_index}) ---\n{chunk}"
    except Exception as e:
        return f"Error reading file chunk: {e}"

def apply_diff(project_path: str, filename: str, diff_content: str) -> str:
    """Applies a provided diff patch to a file. The agent MUST generate a valid diff."""
    try:
        file_path = get_safe_path(project_path, filename)
        # This is a simplified implementation. A real one would use a library like `patch`.
        # For now, we'll simulate by reading, applying, and writing back.
        # This requires the agent to be very precise.

        # Placeholder for a more robust implementation. 
        # We'll guide the agent to use save_file for now via the main prompt.
        return "Note: `apply_diff` is a placeholder. Please use `read_file`, modify the content in your thought process, and use `save_file` for now."
    except Exception as e:
        return f"Error applying diff: {e}"

class ToolRegistry:
    """A registry to hold and manage the agent's tools."""
    def __init__(self, project_path: str):
        self._tools = {
            "echo": echo,
            "save_file": save_file, "execute_python_file": execute_python_file,
            "list_files": list_files, "read_file": read_file,
            "delete_file": delete_file,
            "find_line_numbers": find_line_numbers, # Add this line
            "search_file_content": search_file_content,       # Add this line
            "read_code_chunk": read_code_chunk,  # Add this
            "apply_diff": apply_diff,            # Add this
            "finish": finish,
            "generate_code_map": generate_code_map,
            "replan": replan,
            "create_subtask": create_subtask,
        }

    def get_tool(self, name: str):
        return self._tools.get(name)

    def get_tool_definitions(self) -> str:
        """Return a literal string the LLM sees when it asks for available tools."""
        return (
            "Your available tools are:\n"
            "- echo(message: str): Use to answer a question or provide a direct response to the user in the log.\n"
            "- save_file(filename: str, content: str): Create or overwrite a file.\n"
            "- list_files(): List every file in the current project.\n"
            "- read_file(filename: str): Return the full contents of a file.\n"
            "- execute_python_file(filename: str, timeout: int = 10): Run a Python script with a timeout (default 10s). The script will be terminated if it runs longer.\n"
            "- delete_file(filename: str): Delete a file.\n"
            "- find_line_numbers(filename: str, keyword: str): Find all line numbers where a keyword appears in one file.\n"
            "- search_file_content(keyword: str): Search every file for a keyword (case-insensitive).\n"
            "- read_code_chunk(filename: str, start_line: int, line_count: int = 50): "
            "Return <line_count> lines of code starting at <start_line>.\n"
            "- apply_diff(filename: str, diff_content: str): Apply a unified-diff patch to a file.\n"
            "- finish(reason: str): Call when the entire objective is complete.\n"
            "- replan(reason: str): Tell the orchestrator the current plan failed and request a new one.\n"
            "- create_subtask(description: str): Spawn a follow-up task for work that should be done later.\n"
            "- generate_code_map(): Scans the project to create a detailed map of all files, classes, and functions.\n"
        )
