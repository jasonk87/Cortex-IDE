import os
import subprocess
import tempfile
import re
from flask import Blueprint, jsonify, request, session, current_app
from tools import get_safe_path # Assuming tools.py is in the same directory
from pathlib import Path

package_manager_bp = Blueprint('package_manager', __name__)

@package_manager_bp.route('/api/install_packages', methods=['POST'])
def install_packages():
    project_path = session.get('project_path')
    if not project_path:
        return jsonify({"error": "No active project session"}), 400

    requirements_path = os.path.join(project_path, 'requirements.txt')
    if not os.path.exists(requirements_path):
        return jsonify({"error": "requirements.txt not found in the project root"}), 404

    # Get socketio instance from app context
    socketio = current_app.extensions.get('socketio')

    try:
        # Ensure pip is available
        try:
            # Run pip --version to check availability and capture output
            pip_check_result = subprocess.run(['pip', '--version'], capture_output=True, check=True, text=True, encoding='utf-8')
            print(f"Pip version check: {pip_check_result.stdout}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            # Detailed error message if pip is not found
            error_detail = e.stderr if hasattr(e, 'stderr') and e.stderr else str(e)
            error_msg = f"pip command not found or not executable. Details: {error_detail}"
            if socketio:
                socketio.emit('installation_failed', {'message': error_msg}, room=project_path)
            return jsonify({"error": error_msg}), 500

        # Upgrade pip
        pip_upgrade_result = subprocess.run(
            ['python', '-m', 'pip', 'install', '--upgrade', 'pip'],
            cwd=project_path, capture_output=True, text=True, timeout=180, encoding='utf-8'
        )

        if pip_upgrade_result.returncode != 0:
            print(f"Pip upgrade warning/error stdout: {pip_upgrade_result.stdout}")
            print(f"Pip upgrade warning/error stderr: {pip_upgrade_result.stderr}")
            if socketio:
                socketio.emit('debug_message', {
                    'message': 'Pip upgrade process finished with non-zero exit code.',
                    'stdout': pip_upgrade_result.stdout,
                    'stderr': pip_upgrade_result.stderr
                }, room=project_path)
        else:
            if socketio:
                socketio.emit('debug_message', {
                    'message': 'Pip upgrade process successful.',
                    'stdout': pip_upgrade_result.stdout,
                    'stderr': pip_upgrade_result.stderr
                }, room=project_path)


        # Install packages from requirements.txt
        install_result = subprocess.run(
            ['python', '-m', 'pip', 'install', '-r', 'requirements.txt'],
            cwd=project_path, capture_output=True, text=True, timeout=300, encoding='utf-8'
        )

        if install_result.returncode == 0:
            if socketio:
                socketio.emit('packages_installed', {
                    'message': 'Packages installed successfully.',
                    'stdout': install_result.stdout,
                    'stderr': install_result.stderr
                }, room=project_path)
            return jsonify({
                "success": True,
                "message": "Packages installed successfully.",
                "stdout": install_result.stdout,
                "stderr": install_result.stderr
            })
        else:
            if socketio:
                socketio.emit('installation_failed', {
                    'message': 'Failed to install packages.',
                    'stdout': install_result.stdout,
                    'stderr': install_result.stderr,
                    'exit_code': install_result.returncode
                }, room=project_path)
            return jsonify({
                "success": False,
                "message": "Failed to install packages.",
                "stdout": install_result.stdout,
                "stderr": install_result.stderr,
                "exit_code": install_result.returncode
            }), 500
    except subprocess.TimeoutExpired:
        if socketio:
            socketio.emit('installation_failed', {
                'message': 'Package installation timed out.'
            }, room=project_path)
        return jsonify({"error": "Package installation timed out."}), 408
    except Exception as e:
        if socketio:
            socketio.emit('installation_failed', {
                'message': f'An unexpected error occurred: {str(e)}'
            }, room=project_path)
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@package_manager_bp.route('/api/lint_code', methods=['POST'])
def lint_code():
    data = request.get_json()
    if not data or 'code' not in data:
        return jsonify({"success": False, "error": "No code provided for linting."}), 400

    code = data.get('code', '')
    if not code.strip():
        return jsonify({"success": True, "issues": []}) # No code to lint, no issues

    project_path = session.get('project_path')
    # Although project_path is fetched, it's not strictly used for flake8 on a string,
    # but could be used for project-specific flake8 configs in the future.
    # For now, we ensure it doesn't break if not present for some reason,
    # or default to a generic temp dir if needed for flake8.

    socketio = current_app.extensions.get('socketio')

    try:
        # Check if Flake8 is installed, install if not
        try:
            subprocess.run(['python', '-m', 'flake8', '--version'], capture_output=True, text=True, check=True)
            if socketio and project_path:
                 socketio.emit('debug_message', {'message': 'Flake8 is already installed.'}, room=project_path)
        except (subprocess.CalledProcessError, FileNotFoundError):
            if socketio and project_path:
                socketio.emit('debug_message', {'message': 'Flake8 not found, attempting to install.'}, room=project_path)
            pip_install_flake8 = subprocess.run(
                ['python', '-m', 'pip', 'install', 'flake8'],
                capture_output=True, text=True, check=False
            )
            if pip_install_flake8.returncode != 0:
                error_message = f"Failed to install flake8. STDERR: {pip_install_flake8.stderr}"
                if socketio:
                    socketio.emit('linting_error', {'message': error_message}, room=project_path if project_path else None)
                return jsonify({"success": False, "error": error_message, "details": pip_install_flake8.stderr}), 500
            if socketio and project_path:
                socketio.emit('debug_message', {'message': 'Flake8 installed successfully.'}, room=project_path)

        temp_file_name = None
        temp_file = None
        try:
            # Use project_path for temp file directory if available, otherwise OS default
            temp_dir = project_path if project_path and os.path.isdir(project_path) else None
            temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.py', dir=temp_dir)
            temp_file.write(code)
            temp_file.flush()
            temp_file_name = temp_file.name
            temp_file.close()

            # Run Flake8
            # Example format: E302 expected 2 blank lines, found 1
            # Our format: row,col,code,text
            flake8_process = subprocess.run(
                ['python', '-m', 'flake8', '--format=%(row)d,%(col)d,%(code)s,%(text)s', temp_file_name],
                capture_output=True, text=True, check=False # Flake8 exits 1 if issues found
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
                                "line": int(parts[0]),
                                "col": int(parts[1]),
                                "code": parts[2],
                                "message": parts[3]
                            })
                        except ValueError:
                            print(f"Warning: Could not parse flake8 output line: {line}")
                            # Optionally, report this parsing issue if critical
                    else:
                        print(f"Warning: Unexpected flake8 output line format: {line}")


            if flake8_process.returncode != 0 and not issues and flake8_process.stderr:
                # Flake8 failed for reasons other than finding lint issues (e.g., config error)
                # and didn't produce formatted output.
                if socketio:
                     socketio.emit('linting_error', {'message': f"Flake8 error: {flake8_process.stderr}"}, room=project_path if project_path else None)
                return jsonify({"success": False, "error": f"Flake8 execution error: {flake8_process.stderr}"}), 500

            return jsonify({"success": True, "issues": issues})

        finally:
            if temp_file_name and os.path.exists(temp_file_name):
                os.remove(temp_file_name)
            elif temp_file and hasattr(temp_file, 'close') and not temp_file.closed:
                 temp_file.close() # Ensure closed if error before explicit close and not deleted

    except subprocess.CalledProcessError as e:
        error_message = f"Subprocess error during linting: {e.stderr or e.stdout or str(e)}"
        if socketio:
            socketio.emit('linting_error', {'message': error_message}, room=project_path if project_path else None)
        return jsonify({"success": False, "error": error_message}), 500

@package_manager_bp.route('/api/format_code', methods=['POST'])
def format_code():
    data = request.get_json()
    if not data or 'code' not in data:
        return jsonify({"success": False, "error": "No code provided for formatting."}), 400

    code = data.get('code', '')
    if not code.strip():
        # No code to format, return original code or empty string based on preference
        return jsonify({"success": True, "formatted_code": code})

    project_path = session.get('project_path')
    socketio = current_app.extensions.get('socketio')

    try:
        # Check if Black is installed, install if not
        try:
            subprocess.run(['python', '-m', 'black', '--version'], capture_output=True, text=True, check=True)
            if socketio and project_path:
                socketio.emit('debug_message', {'message': 'Black is already installed.'}, room=project_path)
        except (subprocess.CalledProcessError, FileNotFoundError):
            if socketio and project_path:
                socketio.emit('debug_message', {'message': 'Black not found, attempting to install.'}, room=project_path)
            pip_install_black = subprocess.run(
                ['python', '-m', 'pip', 'install', 'black'],
                capture_output=True, text=True, check=False
            )
            if pip_install_black.returncode != 0:
                error_message = f"Failed to install black. STDERR: {pip_install_black.stderr}"
                if socketio and project_path: # Check project_path for room
                    socketio.emit('formatting_error', {'message': error_message}, room=project_path)
                return jsonify({"success": False, "error": error_message, "details": pip_install_black.stderr}), 500
            if socketio and project_path:
                socketio.emit('debug_message', {'message': 'Black installed successfully.'}, room=project_path)

        temp_file_descriptor, temp_file_name = tempfile.mkstemp(suffix='.py', dir=project_path if project_path and os.path.isdir(project_path) else None)

        try:
            with os.fdopen(temp_file_descriptor, 'w') as temp_file:
                temp_file.write(code)

            # Run Black on the temporary file
            black_process = subprocess.run(
                ['python', '-m', 'black', temp_file_name],
                capture_output=True, text=True, check=False
                # Black exits 0 if successful, 1 if it had to reformat,
                # >1 for other errors. We only care about >1 for actual errors.
            )

            if black_process.returncode != 0:
                # Check if stderr indicates a fatal error (e.g., code cannot be parsed)
                # Black might write to stderr for non-fatal issues too, but usually exits 0 or 1.
                # If Black couldn't parse the file, it often exits with specific codes like 123.
                # For simplicity, any non-zero exit code here is treated as a potential formatting failure
                # if the formatted code can't be read or is empty.
                # However, Black modifies the file in-place. So, we read it regardless of exit code 0 or 1.
                # A more robust check would be to see if Black explicitly states "error:" in stderr.
                pass # We will try to read the file content anyway. Black modifies in-place.

            formatted_code = Path(temp_file_name).read_text()

            if black_process.returncode > 1 : # Indicates a more serious error with Black itself
                 error_detail = black_process.stderr or "Black failed with a non-zero exit code but no stderr."
                 if socketio and project_path:
                    socketio.emit('formatting_error', {'message': f"Black formatting error: {error_detail}"}, room=project_path)
                 return jsonify({"success": False, "error": "Black formatting failed.", "details": error_detail}), 500

            return jsonify({"success": True, "formatted_code": formatted_code})

        finally:
            if os.path.exists(temp_file_name):
                os.remove(temp_file_name)

    except subprocess.CalledProcessError as e:
        error_message = f"Subprocess error during formatting: {e.stderr or e.stdout or str(e)}"
        if socketio and project_path:
            socketio.emit('formatting_error', {'message': error_message}, room=project_path)
        return jsonify({"success": False, "error": error_message, "details": str(e)}), 500
    except FileNotFoundError:
        error_message = "Error: Black or Python command not found. Ensure they are installed and in PATH."
        if socketio and project_path:
            socketio.emit('formatting_error', {'message': error_message}, room=project_path)
        return jsonify({"success": False, "error": error_message}), 500
    except Exception as e:
        error_message = f"An unexpected error occurred during formatting: {str(e)}"
        if socketio and project_path:
            socketio.emit('formatting_error', {'message': error_message}, room=project_path)
        return jsonify({"success": False, "error": error_message, "details": str(e)}), 500
    except FileNotFoundError:
        error_message = "Error: Flake8 or Python command not found. Ensure they are installed and in PATH."
        if socketio:
            socketio.emit('linting_error', {'message': error_message}, room=project_path if project_path else None)
        return jsonify({"success": False, "error": error_message}), 500
    except Exception as e:
        error_message = f"An unexpected error occurred during linting: {str(e)}"
        if socketio:
            socketio.emit('linting_error', {'message': error_message}, room=project_path if project_path else None)
        return jsonify({"success": False, "error": error_message}), 500
