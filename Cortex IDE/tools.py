# tools.py
import os
import re
import ast
from pathlib import Path
import subprocess
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime
import zipfile
from code_utils import _internal_lint_code, _internal_format_code
import requests
from bs4 import BeautifulSoup
from googlesearch import search
import diff_match_patch as dmp_module


def create_backup(project_path: str, *args, **kwargs) -> str:
    """
    Creates a zip backup of the project.
    The backup is stored in a .backups directory within the project,
    and the .backups directory itself is excluded from the archive.
    """
    try:
        backup_dir = os.path.join(project_path, ".backups")
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.zip"
        backup_filepath = os.path.join(backup_dir, backup_filename)

        with zipfile.ZipFile(backup_filepath, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(project_path):
                # Exclude the .backups directory itself from being walked
                if ".backups" in dirs:
                    dirs.remove(".backups")

                for file in files:
                    file_path = os.path.join(root, file)
                    # The arcname is the path inside the zip file
                    arcname = os.path.relpath(file_path, project_path)
                    zipf.write(file_path, arcname)

        return f"Successfully created backup: {backup_filename}"
    except Exception as e:
        return f"Error creating backup: {e}"


def get_safe_path(project_path, filename):
    """Ensures file paths are safe, sanitized, and within the project directory."""
    if not project_path:
        raise Exception("No active project selected")

    safe_filename = secure_filename(filename)
    if not safe_filename:
        if Path(filename).is_absolute() or ".." in Path(filename).parts:
            raise Exception("Invalid or potentially unsafe filename provided")
        safe_filename = filename

    file_path = os.path.join(project_path, safe_filename)
    normalized_path = os.path.normpath(file_path)

    if not normalized_path.startswith(os.path.normpath(project_path)):
        raise PermissionError(
            "Access denied: File path is outside of the project directory."
        )

    return normalized_path


def google_search(project_path: str, query: str, num_results: int = 8) -> str:
    """
    Performs a Google search for the given query and returns the top results.
    """
    try:
        results = []
        for j in search(query, num_results=num_results):
            results.append(j)

        if not results:
            return "No results found."

        return "\n".join(results)
    except Exception as e:
        return f"Error performing Google search: {e}"


def view_text_website(project_path: str, url: str) -> str:
    """
    Fetches the content of a website and returns it as plain text.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()

        text = soup.get_text()

        # Clean up text
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)

        return text
    except requests.exceptions.RequestException as e:
        return f"Error fetching website: {e}"


def _compress_blank_lines(text: str, max_run: int = 2) -> str:
    """
    Collapse any run of > `max_run` consecutive new-lines to exactly `max_run`.
    Also strips trailing blank lines.
    """
    text = re.sub(r"\n{" + str(max_run + 1) + r",}", "\n" * max_run, text)
    return text.rstrip() + "\n"


class PythonCodeParser(ast.NodeVisitor):
    def __init__(self):
        self.imports = set()
        self.functions = []
        self.classes = {}

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.add(alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            self.imports.add(node.module.split(".")[0])
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
    exclude_dirs = {
        "__pycache__",
        ".git",
        ".idea",
        "venv",
        ".venv",
        "env",
        "node_modules",
    }

    for root, dirs, files in os.walk(project_path_obj, topdown=True):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        current_path = Path(root)
        relative_path = current_path.relative_to(project_path_obj)
        level = len(relative_path.parts)
        indent = "    " * level
        dir_name = (
            current_path.name if str(relative_path) != "." else project_path_obj.name
        )
        file_tree_lines.append(f"{indent}📁 {dir_name}/")
        file_indent = "    " * (level + 1)
        for name in sorted(files):
            file_tree_lines.append(f"{file_indent}📄 {name}")
            if name.endswith(".py"):
                file_path = current_path / name
                relative_file_path_str = str(file_path.relative_to(project_path_obj))
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        source_code = f.read()
                    tree = ast.parse(source_code, filename=name)
                    parser = PythonCodeParser()
                    for node in ast.iter_child_nodes(tree):
                        parser.visit(node)
                    code_map[relative_file_path_str] = {
                        "imports": sorted(list(parser.imports)),
                        "functions": sorted(parser.functions),
                        "classes": {
                            k: sorted(v) for k, v in sorted(parser.classes.items())
                        },
                    }
                except Exception as e:
                    code_map[relative_file_path_str] = {
                        "error": f"Could not parse file: {e}"
                    }

    output_md = (
        "# Project Code Map\n\n## File Tree\n```\n"
        + "\n".join(file_tree_lines)
        + "\n```\n\n## Code Structure Analysis\n"
    )
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
    try:
        file_path = get_safe_path(project_path, filename)
        if len(content) > 10_000 or content.count("\n") / max(len(content), 1) > 0.3:
            content = _compress_blank_lines(content)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully saved file: {os.path.basename(filename)}"
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
    subtask_id = f"task_{uuid.uuid4()}"
    return f"SUBTASK_CREATED: {subtask_id} — {description}"


def execute_python_file(project_path: str, filename: str, timeout: int = 10) -> str:
    try:
        full_safe_path = get_safe_path(project_path, filename)
        relative_filename = os.path.relpath(full_safe_path, project_path)
        if not os.path.exists(full_safe_path):
            return f"Error: File '{filename}' not found."
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        result = subprocess.run(
            ["python", relative_filename],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_path,
            encoding="utf-8",
            env=env,
        )
        return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return (
            f"Error: Execution timed out after {timeout} seconds for file '{filename}'."
        )
    except Exception as e:
        return f"Error executing file '{filename}': {e}"


def list_files(project_path: str) -> str:
    try:
        if not os.path.isdir(project_path):
            return "Error: Project path is not a valid directory."
        files = [
            f
            for f in os.listdir(project_path)
            if os.path.isfile(os.path.join(project_path, f))
        ]
        if not files:
            return "No files in the project directory."
        return "\n".join(files)
    except Exception as e:
        return f"Error listing files: {e}"


def read_file(project_path: str, filename: str) -> str:
    try:
        file_path = get_safe_path(project_path, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file '{filename}': {e}"


def finish(project_path: str, reason: str) -> None:
    return None


def find_line_numbers(project_path: str, filename: str, keyword: str) -> str:
    try:
        file_path = get_safe_path(project_path, filename)
        if not os.path.exists(file_path):
            return f"Error: File '{os.path.basename(filename)}' not found."
        found_lines = []
        with open(file_path, "r", encoding="utf-8") as f:
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
                with fpath.open("r", encoding="utf-8", errors="ignore") as f:
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
    return message


def read_code_chunk(
    project_path: str, filename: str, start_line: int, line_count: int = 50
) -> str:
    try:
        file_path = get_safe_path(project_path, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        start_index = start_line - 1
        end_index = start_index + line_count
        if start_index < 0 or start_index >= len(lines):
            return (
                f"Error: start_line {start_line} is out of bounds for file {filename}."
            )
        chunk = "".join(lines[start_index:end_index])
        return f"--- Code from {filename} (lines {start_line}-{end_index}) ---\n{chunk}"
    except Exception as e:
        return f"Error reading file chunk: {e}"




def run_tests(project_path: str, timeout: int = 60) -> str:
    """
    Runs the pytest test suite within the project's directory.
    Captures and returns the output, including test results and errors.
    """
    try:
        if not os.path.isdir(project_path):
            return "Error: Project path is not a valid directory."

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        result = subprocess.run(
            ["python", "-m", "pytest"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_path,
            encoding="utf-8",
            env=env,
        )
        output = f"Exit Code: {result.returncode}\n"
        if result.stdout:
            output += f"--- Test Output (stdout) ---\n{result.stdout}\n"
        if result.stderr:
            output += f"--- Test Errors (stderr) ---\n{result.stderr}\n"
        if result.returncode == 0:
            return f"All tests passed.\n\n{output}"
        elif result.returncode == 1:
            return f"Tests failed.\n\n{output}"
        else:
            return f"Pytest exited with an unusual code. See output for details.\n\n{output}"
    except FileNotFoundError:
        return "Error: `pytest` command not found. Please ensure pytest is installed in the environment."
    except subprocess.TimeoutExpired:
        return f"Error: Test execution timed out after {timeout} seconds."
    except Exception as e:
        return f"An unexpected error occurred while running tests: {e}"


def search_and_replace(
    project_path: str, filename: str, search_query: str, replacement_text: str
) -> str:
    """
    Performs a search and replace operation on a file.
    Replaces all occurrences of search_query with replacement_text.
    """
    try:
        file_path = get_safe_path(project_path, filename)
        if not os.path.exists(file_path):
            return f"Error: File '{os.path.basename(filename)}' not found."
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if search_query not in content:
            return f"Error: Search query '{search_query}' not found in {os.path.basename(filename)}."
        new_content = content.replace(search_query, replacement_text)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"Successfully replaced '{search_query}' with '{replacement_text}' in {os.path.basename(filename)}."
    except Exception as e:
        return f"Error during search and replace in '{filename}': {e}"


def insert_at_line(
    project_path: str, filename: str, line_number: int, content_to_insert: str
) -> str:
    """
    Inserts a block of text into a file at a specific line number.
    """
    try:
        file_path = get_safe_path(project_path, filename)
        if not os.path.exists(file_path):
            return f"Error: File '{os.path.basename(filename)}' not found."
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if not (1 <= line_number <= len(lines) + 1):
            return f"Error: Line number {line_number} is out of bounds for file {os.path.basename(filename)} which has {len(lines)} lines."
        if not content_to_insert.endswith("\n"):
            content_to_insert += "\n"
        lines.insert(line_number - 1, content_to_insert)
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return f"Successfully inserted content into {os.path.basename(filename)} at line {line_number}."
    except Exception as e:
        return f"Error during insert operation in '{filename}': {e}"


def lint_file_tool(project_path: str, filename: str) -> str:
    """
    Lints a specified Python file.
    Returns a summary of linting issues or a success message.
    """
    try:
        target_file_path = get_safe_path(project_path, filename)
        if not Path(target_file_path).name.endswith(".py"):
            return "Error: Linting is only supported for Python files (.py)."
        if not os.path.exists(target_file_path):
            return f"Error: File '{filename}' not found for linting."
        with open(target_file_path, "r", encoding="utf-8") as f:
            code_content = f.read()
        if not code_content.strip():
            return f"File '{filename}' is empty. No linting needed."

        result = _internal_lint_code(code_content)

        if result.get("success"):
            issues = result.get("issues", [])
            if not issues:
                return f"No linting issues found in '{filename}'."
            else:
                summary = [f"Found {len(issues)} linting issues in '{filename}':"]
                for issue in issues:
                    summary.append(
                        f"  - Line {issue['line']}, Col {issue['col']}: [{issue['code']}] {issue['message']}"
                    )
                return "\n".join(summary)
        else:
            return f"Error linting file '{filename}': {result.get('error', 'Unknown linting error')}. Details: {result.get('details', '')}"
    except Exception as e:
        return f"Error during lint_file_tool for '{filename}': {str(e)}"


def format_file_tool(project_path: str, filename: str) -> str:
    """
    Formats a specified Python file using Black and overwrites it.
    Returns a success or error message.
    """
    try:
        target_file_path = get_safe_path(project_path, filename)
        if not Path(target_file_path).name.endswith(".py"):
            return "Error: Formatting is only supported for Python files (.py)."
        if not os.path.exists(target_file_path):
            return f"Error: File '{filename}' not found for formatting."

        with open(target_file_path, "r", encoding="utf-8") as f:
            original_content = f.read()
        if not original_content.strip():
            return f"File '{filename}' is empty. No formatting needed."

        result = _internal_format_code(original_content)

        if result.get("success"):
            formatted_content = result.get("formatted_code")
            if formatted_content != original_content:
                with open(target_file_path, "w", encoding="utf-8") as f:
                    f.write(formatted_content)
                return f"File '{filename}' formatted successfully."
            else:
                return f"File '{filename}' is already correctly formatted."
        else:
            return f"Error formatting file '{filename}': {result.get('error', 'Unknown formatting error')}. Details: {result.get('details', '')}"
    except Exception as e:
        return f"Error during format_file_tool for '{filename}': {str(e)}"


class ToolRegistry:
    """A registry to hold and manage the agent's tools."""

    def __init__(self, project_path: str):
        self._tools = {
            "create_backup": create_backup,
            "echo": echo,
            "save_file": save_file,
            "execute_python_file": execute_python_file,
            "list_files": list_files,
            "read_file": read_file,
            "delete_file": delete_file,
            "find_line_numbers": find_line_numbers,
            "search_file_content": search_file_content,
            "read_code_chunk": read_code_chunk,
            "finish": finish,
            "generate_code_map": generate_code_map,
            "replan": replan,
            "create_subtask": create_subtask,
            "lint_file": lint_file_tool,
            "format_file": format_file_tool,
            "run_tests": run_tests,
            "search_and_replace": search_and_replace,
            "insert_at_line": insert_at_line,
            "google_search": google_search,
            "view_text_website": view_text_website,
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
            "- execute_python_file(filename: str, timeout: int = 10): Run a Python script with a timeout (default 10s).\n"
            "- run_tests(): Runs the pytest test suite for the project and returns the results.\n"
            "- delete_file(filename: str): Delete a file.\n"
            "- find_line_numbers(filename: str, keyword: str): Find all line numbers where a keyword appears in one file.\n"
            "- search_file_content(keyword: str): Search every file for a keyword (case-insensitive).\n"
            "- search_and_replace(filename: str, search_query: str, replacement_text: str): Search for a string in a file and replace all occurrences.\n"
            "- insert_at_line(filename: str, line_number: int, content_to_insert: str): Insert a block of text into a file at a specific line number.\n"
            "- read_code_chunk(filename: str, start_line: int, line_count: int = 50): Return a chunk of code from a file.\n"
            "- lint_file(filename: str): Lints the specified Python file and reports issues.\n"
            "- format_file(filename: str): Formats the specified Python file using Black and overwrites it.\n"
            "- google_search(query: str, num_results: int = 8): Performs a Google search and returns the top results.\n"
            "- view_text_website(url: str): Fetches the content of a website as plain text.\n"
            "- finish(reason: str): Call when the entire objective is complete.\n"
            "- replan(reason: str): Tell the orchestrator the current plan failed and request a new one.\n"
            "- create_subtask(description: str): Spawn a follow-up task for work that should be done later.\n"
            "- generate_code_map(): Scans the project to create a detailed map of all files, classes, and functions.\n"
        )
