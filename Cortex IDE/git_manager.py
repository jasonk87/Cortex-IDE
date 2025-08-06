import os
import subprocess
from flask import Blueprint, request, jsonify, session
from tools import get_safe_path

git_manager_bp = Blueprint('git_manager', __name__)

def run_git_command(project_path, command):
    """A helper function to run a Git command in the project's directory."""
    try:
        # Ensure the project_path is a safe, existing directory
        safe_project_path = get_safe_path(os.path.abspath("workspaces"), os.path.basename(project_path))

        if not os.path.isdir(safe_project_path):
            return {"error": "Project directory not found."}, 404

        # Execute the git command
        result = subprocess.run(
            command,
            cwd=safe_project_path,
            capture_output=True,
            text=True,
            check=False  # Do not raise exception on non-zero exit codes
        )

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }

    except Exception as e:
        return {"error": str(e)}, 500

@git_manager_bp.route('/api/git/init', methods=['POST'])
def git_init():
    project_path = session.get('project_path')
    if not project_path:
        return jsonify({"error": "No active project session"}), 400

    # Check if .git directory already exists
    if os.path.isdir(os.path.join(project_path, '.git')):
        return jsonify({"message": "Git repository already initialized."}), 200

    result = run_git_command(project_path, ['git', 'init'])
    return jsonify(result)

@git_manager_bp.route('/api/git/status', methods=['GET'])
def git_status():
    project_path = session.get('project_path')
    if not project_path:
        return jsonify({"error": "No active project session"}), 400

    result = run_git_command(project_path, ['git', 'status', '--porcelain'])
    return jsonify(result)

@git_manager_bp.route('/api/git/add_all', methods=['POST'])
def git_add_all():
    project_path = session.get('project_path')
    if not project_path:
        return jsonify({"error": "No active project session"}), 400

    result = run_git_command(project_path, ['git', 'add', '.'])
    return jsonify(result)

@git_manager_bp.route('/api/git/commit', methods=['POST'])
def git_commit():
    project_path = session.get('project_path')
    if not project_path:
        return jsonify({"error": "No active project session"}), 400

    data = request.get_json()
    message = data.get('message')
    if not message:
        return jsonify({"error": "Commit message is required"}), 400

    result = run_git_command(project_path, ['git', 'commit', '-m', message])
    return jsonify(result)
