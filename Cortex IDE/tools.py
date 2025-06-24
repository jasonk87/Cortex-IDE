# tools.py
import os
import re
import ast
from pathlib import Path
from typing import Dict, List, Any
import subprocess
#from pathlib import Path # Duplicate import removed
from werkzeug.utils import secure_filename
import time # For create_subtask, already present
import requests # For new lint/format tools
import json # For new lint/format tools
import tempfile # For new lint/format tools, though not used in final version of them

BASE_DIR = Path(__file__).resolve().parent  # root of the workspace

FLASK_APP_URL = "http://localhost:5001" # Used by new tools

def get_safe_path(project_path, filename):
    """Ensures file paths are safe, sanitized, and within the project directory."""
    if not project_path:
        raise Exception("No active project selected")

    safe_filename = secure_filename(filename)
    if not safe_filename: # handle cases where secure_filename might return an empty string
        # Attempt to use original filename if it's simple and relative
        # This is a basic check; more robust validation might be needed depending on expected inputs
        if Path(filename).is_absolute() or ".." in Path(filename).parts:
             raise Exception("Invalid or potentially unsafe filename provided")
        # If filename seems okay (e.g. "main.py", "src/test.py"), use it cautiously
        # This part assumes 'filename' itself has been somewhat vetted if secure_filename fails
        # For maximum safety, one might choose to reject if secure_filename doesn't like it.
        # However, secure_filename can be too aggressive for valid relative paths with subdirs.
        # We rely on the os.path.join and subsequent startswith check for main security.
        safe_filename = filename

    file_path = os.path.join(project_path, safe_filename)
    normalized_path = os.path.normpath(file_path)

    if not normalized_path.startswith(os.path.normpath(project_path)):
        raise PermissionError("Access denied: File path is outside of the project directory.")

    return normalized_path

def _compress_blank_lines(text: str, max_run: int = 2) -> str:
    """
    Collapse any run of > `max_run` consecutive new-lines to exactly `max_run`.
    Also strips trailing blank lines.
    """
    text = re.sub(r'\n{'+str(max_run+1)+r',}', '\n'*max_run, text)
    return text.rstrip() + '\n'

class PythonCodeParser(ast.NodeVisitor):
    def __init__(self):
        self.imports = set()
        self.functions = []
        self.classes = {}

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.add(alias.name.split('.')[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            self.imports.add(node.module.split('.')[0])
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        args = [a.arg for a in node.args.args]
        self.functions.append(f"{node.name}({', '.join(args)})")

    def visit_ClassDef(self, node: ast.ClassDef):
        class_name = node.name
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method_args = [a.arg for a in item.args.args]
                methods.append(f"{item.name}({', '.join(method_args)})")
        self.classes[class_name] = methods

def generate_code_map(project_path: str, *args, **kwargs) -> str:
    project_path_obj = Path(project_path).resolve()
    if not project_path_obj.is_dir():
        return "Error: The provided path is not a valid directory."

    code_map = {}
    file_tree_lines = []
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
                relative_file_path_str = str(file_path.relative_to(project_path_obj))
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        source_code = f.read()
                    tree = ast.parse(source_code, filename=name)
                    parser = PythonCodeParser()
                    for node in ast.iter_child_nodes(tree):
                         parser.visit(node)
                    code_map[relative_file_path_str] = {
                        "imports": sorted(list(parser.imports)),
                        "functions": sorted(parser.functions),
                        "classes": {k: sorted(v) for k, v in sorted(parser.classes.items())}
                    }
                except Exception as e:
                    code_map[relative_file_path_str] = {"error": f"Could not parse file: {e}"}

    output_md = "# Project Code Map\n\n## File Tree\n```\n" + "\n".join(file_tree_lines) + "\n```\n\n## Code Structure Analysis\n"
    if not code_map:
        output_md += "No Python files were found or parsed in the project.\n"
    else:
        for file_path_str, data in sorted(code_map.items()):
            output_md += f"### `{file_path_str}`\n"
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
                        for method in methods: output_md += f"    - `{method}`\n"
                    else: output_md += f"    - *(No methods defined)*\n"
            if data["functions"]:
                output_md += "- **Functions:**\n"
                for func in data["functions"]: output_md += f"  - `{func}`\n"
            output_md += "\n"
    return output_md.strip()

def save_file(project_path: str, filename: str, content: str) -> str:
    try:
        file_path = get_safe_path(project_path, filename) # get_safe_path returns str
        if len(content) > 10_000 or content.count('\n')/max(len(content),1) > 0.3:
            content = _compress_blank_lines(content)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully saved file: {os.path.basename(filename)}" # Use original filename for user message
    except Exception as e:
        return f"Error saving file '{filename}': {e}"

def delete_file(project_path: str, filename: str) -> str:
    try:
        file_path = get_safe_path(project_path, filename)
        if not os.path.exists(file_path):
            return f"Error: File '{os.path.basename(filename)}' not found."
        os.remove(file_path)
        return f"Successfully deleted file: {os.path.basename(filename)}"
    except Exception as e:
        return f"Error deleting file '{filename}': {e}"

def replan(project_path: str, reason: str) -> str:
    return f"REPLAN_REQUESTED: {reason}"

def create_subtask(project_path: str, description: str) -> str:
    subtask_id = f"task_{int(time.time())}"
    return f"SUBTASK_CREATED: {subtask_id} — {description}"

def execute_python_file(project_path: str, filename: str, timeout: int = 10) -> str:
    try:
        # Use get_safe_path to resolve the full path first
        full_safe_path = get_safe_path(project_path, filename)
        # For subprocess, it's often better to use the relative path from project_path if cwd is project_path
        relative_filename = os.path.relpath(full_safe_path, project_path)

        if not os.path.exists(full_safe_path): # Check existence using full path
            return f"Error: File '{filename}' not found."

        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'

        result = subprocess.run(
            ['python', relative_filename], # Execute using relative_filename
            capture_output=True, text=True, timeout=timeout,
            cwd=project_path, encoding='utf-8', env=env
        )
        return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return f"Error: Execution timed out after {timeout} seconds for file '{filename}'."
    except Exception as e:
        return f"Error executing file '{filename}': {e}"

def list_files(project_path: str) -> str:
    try:
        # Ensure project_path is a directory
        if not os.path.isdir(project_path):
            return "Error: Project path is not a valid directory."
        files = [f for f in os.listdir(project_path) if os.path.isfile(os.path.join(project_path, f))]
        if not files: return "No files in the project directory."
        return "\n".join(files)
    except Exception as e:
        return f"Error listing files: {e}"

def read_file(project_path: str, filename: str) -> str:
    try:
        file_path = get_safe_path(project_path, filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file '{filename}': {e}"

def finish(project_path: str, reason: str) -> None:
    return None # Explicitly return None, though Python does this by default

def find_line_numbers(project_path: str, filename: str, keyword: str) -> str:
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

def search_file_content(project_path: str, keyword: str) -> str:
    base_dir = Path(project_path).resolve()
    patt = re.compile(re.escape(keyword), re.IGNORECASE)
    matches = []
    for root, _, files in os.walk(base_dir):
        for fname in files:
            fpath = Path(root) / fname
            try:
                with fpath.open('r', encoding='utf-8', errors='ignore') as f:
                    for ln_no, line in enumerate(f, 1):
                        if patt.search(line):
                            rel = fpath.relative_to(base_dir)
                            matches.append(f"{rel}, line {ln_no}: {line.strip()}")
            except (UnicodeDecodeError, PermissionError): continue
    if not matches: return f"Keyword '{keyword}' not found in any file content in the project."
    return "Search results:\n" + "\n".join(matches[:50])

def echo(project_path: str, message: str) -> str:
    return message

def read_code_chunk(project_path: str, filename: str, start_line: int, line_count: int = 50) -> str:
    try:
        file_path = get_safe_path(project_path, filename)
        with open(file_path, 'r', encoding='utf-8') as f: lines = f.readlines()
        start_index = start_line - 1
        end_index = start_index + line_count
        if start_index < 0 or start_index >= len(lines):
            return f"Error: start_line {start_line} is out of bounds for file {filename}."
        chunk = "".join(lines[start_index:end_index])
        return f"--- Code from {filename} (lines {start_line}-{end_index}) ---\n{chunk}"
    except Exception as e:
        return f"Error reading file chunk: {e}"

def apply_diff(project_path: str, filename: str, diff_content: str) -> str:
    try:
        file_path = get_safe_path(project_path, filename)
        return "Note: `apply_diff` is a placeholder. Please use `read_file`, modify the content in your thought process, and use `save_file` for now."
    except Exception as e:
        return f"Error applying diff: {e}"

# --- New Lint and Format Tools ---
def lint_file_tool(project_path: str, filename: str) -> str:
    """
    Lints a specified Python file using the backend /api/lint_code endpoint.
    Returns a summary of linting issues or a success message.
    Requires the main Flask app to be running.
    """
    try:
        target_file_path_str = get_safe_path(project_path, filename) # get_safe_path returns str
        target_file_path = Path(target_file_path_str)

        if not target_file_path.name.endswith(".py"):
            return "Error: Linting is only supported for Python files (.py)."
        if not target_file_path.exists():
            return f"Error: File '{filename}' not found for linting."

        code_content = target_file_path.read_text(encoding='utf-8')

        if not code_content.strip():
            return f"File '{filename}' is empty. No linting needed."

        # This tool makes an HTTP request to its own Flask application.
        # Ensure the session context is correctly handled if the endpoint relies on it.
        # For this specific endpoint, project_path is implicitly available via session in package_manager.py
        # However, this tool doesn't run in a request context with that session.
        # This is a known limitation. The agent would need to ensure session is set if calling this.
        # A better long-term solution would be to refactor lint_code to be callable internally.

        # For now, we assume the agent has set a session or the endpoint can work without it for this tool.
        # This is a simplification. The `project_path` parameter here is mostly for path safety.

        # Construct payload for the API
        payload = {'code': code_content}
        # The API endpoint in package_manager.py doesn't explicitly use project_path from payload,
        # it uses it from session for temp file creation. We rely on current_app context there.

        response = requests.post(f"{FLASK_APP_URL}/api/lint_code", json=payload)
        response.raise_for_status()

        result = response.json()

        if result.get("success"):
            issues = result.get("issues", [])
            if not issues:
                return f"No linting issues found in '{filename}'."
            else:
                summary = [f"Found {len(issues)} linting issues in '{filename}':"]
                for issue in issues:
                    summary.append(f"  - Line {issue['line']}, Col {issue['col']}: [{issue['code']}] {issue['message']}")
                return "\n".join(summary)
        else:
            return f"Error linting file '{filename}': {result.get('error', 'Unknown linting error')}. Details: {result.get('details', '')}"

    except requests.exceptions.RequestException as req_e:
        return f"Error calling linting API for '{filename}': {req_e}. Ensure the Cortex IDE server is running at {FLASK_APP_URL}."
    except Exception as e:
        return f"Error during lint_file_tool for '{filename}': {str(e)}"

def format_file_tool(project_path: str, filename: str) -> str:
    """
    Formats a specified Python file using the backend /api/format_code endpoint.
    The file is overwritten with the formatted code.
    Returns a success or error message. Requires the main Flask app to be running.
    """
    try:
        target_file_path_str = get_safe_path(project_path, filename)
        target_file_path = Path(target_file_path_str)

        if not target_file_path.name.endswith(".py"):
            return "Error: Formatting is only supported for Python files (.py)."
        if not target_file_path.exists():
            return f"Error: File '{filename}' not found for formatting."

        original_content = target_file_path.read_text(encoding='utf-8')

        if not original_content.strip():
            return f"File '{filename}' is empty. No formatting needed."

        payload = {'code': original_content}
        response = requests.post(f"{FLASK_APP_URL}/api/format_code", json=payload)
        response.raise_for_status()

        result = response.json()

        if result.get("success"):
            formatted_content = result.get("formatted_code")
            if formatted_content != original_content:
                # Save the formatted content back to the file
                target_file_path.write_text(formatted_content, encoding='utf-8')
                return f"File '{filename}' formatted successfully."
            else:
                return f"File '{filename}' is already correctly formatted."
        else:
            return f"Error formatting file '{filename}': {result.get('error', 'Unknown formatting error')}. Details: {result.get('details', '')}"

    except requests.exceptions.RequestException as req_e:
        return f"Error calling formatting API for '{filename}': {req_e}. Ensure the Cortex IDE server is running at {FLASK_APP_URL}."
    except Exception as e:
        return f"Error during format_file_tool for '{filename}': {str(e)}"

class ToolRegistry:
    """A registry to hold and manage the agent's tools."""
    def __init__(self, project_path: str):
        self._tools = {
            "echo": echo,
            "save_file": save_file,
            "execute_python_file": execute_python_file,
            "list_files": list_files,
            "read_file": read_file,
            "delete_file": delete_file,
            "find_line_numbers": find_line_numbers,
            "search_file_content": search_file_content,
            "read_code_chunk": read_code_chunk,
            "apply_diff": apply_diff,
            "finish": finish,
            "generate_code_map": generate_code_map,
            "replan": replan,
            "create_subtask": create_subtask,
            "lint_file": lint_file_tool, # New
            "format_file": format_file_tool, # New
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
            "- apply_diff(filename: str, diff_content: str): Apply a unified-diff patch to a file. (Currently a placeholder, use read/save_file)\n" # Updated apply_diff description
            "- lint_file(filename: str): Lints the specified Python file and reports issues.\n" # New
            "- format_file(filename: str): Formats the specified Python file using Black and overwrites it.\n" # New
            "- finish(reason: str): Call when the entire objective is complete.\n"
            "- replan(reason: str): Tell the orchestrator the current plan failed and request a new one.\n"
            "- create_subtask(description: str): Spawn a follow-up task for work that should be done later.\n"
            "- generate_code_map(): Scans the project to create a detailed map of all files, classes, and functions.\n"
        )
