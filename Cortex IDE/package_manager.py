import os
import subprocess
from flask import Blueprint, jsonify, request, session, current_app
from code_utils import (
    _internal_lint_code,
    _internal_format_code,
)  # Import new functions

package_manager_bp = Blueprint("package_manager", __name__)


@package_manager_bp.route("/api/install_packages", methods=["POST"])
def install_packages():
    project_path = session.get("project_path")
    if not project_path:
        return jsonify({"error": "No active project session"}), 400

    requirements_path = os.path.join(project_path, "requirements.txt")
    if not os.path.exists(requirements_path):
        return jsonify({"error": "requirements.txt not found in the project root"}), 404

    socketio = current_app.extensions.get("socketio")

    try:
        try:
            pip_check_result = subprocess.run(
                ["pip", "--version"],
                capture_output=True,
                check=True,
                text=True,
                encoding="utf-8",
            )
            print(f"Pip version check: {pip_check_result.stdout}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            error_detail = e.stderr if hasattr(e, "stderr") and e.stderr else str(e)
            error_msg = (
                f"pip command not found or not executable. Details: {error_detail}"
            )
            if socketio:
                socketio.emit(
                    "installation_failed", {"message": error_msg}, room=project_path
                )
            return jsonify({"error": error_msg}), 500

        pip_upgrade_result = subprocess.run(
            ["python", "-m", "pip", "install", "--upgrade", "pip"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
        )

        if pip_upgrade_result.returncode != 0:
            if socketio:
                socketio.emit(
                    "debug_message",
                    {
                        "message": "Pip upgrade process finished with non-zero exit code.",
                        "stdout": pip_upgrade_result.stdout,
                        "stderr": pip_upgrade_result.stderr,
                    },
                    room=project_path,
                )
        else:
            if socketio:
                socketio.emit(
                    "debug_message",
                    {
                        "message": "Pip upgrade process successful.",
                        "stdout": pip_upgrade_result.stdout,
                        "stderr": pip_upgrade_result.stderr,
                    },
                    room=project_path,
                )

        install_result = subprocess.run(
            ["python", "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
        )

        if install_result.returncode == 0:
            if socketio:
                socketio.emit(
                    "packages_installed",
                    {
                        "message": "Packages installed successfully.",
                        "stdout": install_result.stdout,
                        "stderr": install_result.stderr,
                    },
                    room=project_path,
                )
            return jsonify(
                {
                    "success": True,
                    "message": "Packages installed successfully.",
                    "stdout": install_result.stdout,
                    "stderr": install_result.stderr,
                }
            )
        else:
            if socketio:
                socketio.emit(
                    "installation_failed",
                    {
                        "message": "Failed to install packages.",
                        "stdout": install_result.stdout,
                        "stderr": install_result.stderr,
                        "exit_code": install_result.returncode,
                    },
                    room=project_path,
                )
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Failed to install packages.",
                        "stdout": install_result.stdout,
                        "stderr": install_result.stderr,
                        "exit_code": install_result.returncode,
                    }
                ),
                500,
            )
    except subprocess.TimeoutExpired:
        if socketio:
            socketio.emit(
                "installation_failed",
                {"message": "Package installation timed out."},
                room=project_path,
            )
        return jsonify({"error": "Package installation timed out."}), 408
    except Exception as e:
        if socketio:
            socketio.emit(
                "installation_failed",
                {"message": f"An unexpected error occurred: {str(e)}"},
                room=project_path,
            )
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


@package_manager_bp.route("/api/lint_code", methods=["POST"])
def lint_code():
    data = request.get_json()
    if not data or "code" not in data:
        return (
            jsonify({"success": False, "error": "No code provided for linting."}),
            400,
        )

    code = data.get("code", "")
    result = _internal_lint_code(code)
    return jsonify(result)


@package_manager_bp.route("/api/format_code", methods=["POST"])
def format_code():
    data = request.get_json()
    if not data or "code" not in data:
        return (
            jsonify({"success": False, "error": "No code provided for formatting."}),
            400,
        )

    code = data.get("code", "")
    result = _internal_format_code(code)
    return jsonify(result)
