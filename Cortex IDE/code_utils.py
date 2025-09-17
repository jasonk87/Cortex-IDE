import subprocess
import tempfile
import os
from pathlib import Path

def _internal_lint_code(code: str) -> dict:
    """
    Internal function to lint a string of Python code using flake8.
    This function is pure and does not depend on a Flask request context.
    Returns a dictionary with success status and a list of issues.
    """
    if not code.strip():
        return {"success": True, "issues": []}

    # Ensure flake8 is installed
    try:
        subprocess.run(['python', '-m', 'flake8', '--version'], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            subprocess.run(['python', '-m', 'pip', 'install', 'flake8'], capture_output=True, text=True, check=True)
        except Exception as e:
            return {"success": False, "error": "Failed to install flake8.", "details": str(e)}

    # Use a temporary file to run flake8
    temp_file_name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.py') as temp_file:
            temp_file.write(code)
            temp_file_name = temp_file.name

        flake8_process = subprocess.run(
            ['python', '-m', 'flake8', '--format=%(row)d,%(col)d,%(code)s,%(text)s', temp_file_name],
            capture_output=True, text=True, check=False
        )

        issues = []
        if flake8_process.stdout:
            lines = flake8_process.stdout.strip().split('\n')
            for line in lines:
                if not line.strip(): continue
                parts = line.split(',', 3)
                if len(parts) == 4:
                    try:
                        issues.append({
                            "line": int(parts[0]), "col": int(parts[1]),
                            "code": parts[2], "message": parts[3]
                        })
                    except ValueError:
                        pass # Ignore lines that can't be parsed

        if flake8_process.returncode != 0 and not issues and flake8_process.stderr:
            return {"success": False, "error": "Flake8 execution error", "details": flake8_process.stderr}

        return {"success": True, "issues": issues}

    finally:
        if temp_file_name and os.path.exists(temp_file_name):
            os.remove(temp_file_name)


def _internal_format_code(code: str) -> dict:
    """
    Internal function to format a string of Python code using Black.
    This function is pure and does not depend on a Flask request context.
    Returns a dictionary with success status and the formatted code.
    """
    if not code.strip():
        return {"success": True, "formatted_code": code}

    # Ensure black is installed
    try:
        subprocess.run(['python', '-m', 'black', '--version'], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            subprocess.run(['python', '-m', 'pip', 'install', 'black'], capture_output=True, text=True, check=True)
        except Exception as e:
            return {"success": False, "error": "Failed to install black.", "details": str(e)}

    # Use a temporary file to run black
    temp_file_name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.py') as temp_file:
            temp_file.write(code)
            temp_file_name = temp_file.name

        black_process = subprocess.run(
            ['python', '-m', 'black', temp_file_name],
            capture_output=True, text=True, check=False
        )

        if black_process.returncode > 1:
            return {"success": False, "error": "Black formatting failed.", "details": black_process.stderr}

        formatted_code = Path(temp_file_name).read_text()
        return {"success": True, "formatted_code": formatted_code}

    finally:
        if temp_file_name and os.path.exists(temp_file_name):
            os.remove(temp_file_name)
