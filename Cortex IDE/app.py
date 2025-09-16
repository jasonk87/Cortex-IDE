# app.py (Updated for UX/UI)
import os
import uuid
import subprocess
import shutil
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    session,
    send_file,
    after_this_request,
)
from flask_socketio import SocketIO, join_room
from agent import Agent
from tools import get_safe_path
from pathlib import Path
from package_manager import package_manager_bp

app = Flask(__name__)
app.register_blueprint(package_manager_bp)
app.config["SECRET_KEY"] = "a-very-secret-key-for-production!"
socketio = SocketIO(
    app,
    async_mode="threading",  # avoids eventlet blocking
)


PROJECTS_BASE_DIR = "workspaces"
if not os.path.exists(PROJECTS_BASE_DIR):
    os.makedirs(PROJECTS_BASE_DIR)

# --- Agent Management ---
active_agents = {}  # Key: project_path, not SID


def agent_runner(sid, project_path, objective):
    """Wrapper to run agent and ensure cleanup."""

    def broadcast_to_project(event, data=None):
        # We emit directly to the room, not a specific SID
        socketio.emit(event, data, room=project_path)

    agent = Agent(
        project_path=project_path,
        emit_func=broadcast_to_project,
        sleep_func=socketio.sleep,
    )
    # Use project_path as the key for active agents
    active_agents[project_path] = agent
    agent.run(objective)

    if project_path in active_agents:
        del active_agents[project_path]
        print(
            f"Agent task finished for project {project_path}, "
            "removed from active list."
        )


# --- NEW SOCKET.IO EVENT HANDLER ---
@socketio.on("join_project_room")
def handle_join_project_room(data):
    """Handles client request to join a project-specific room."""
    project_path = data.get("project_path")
    if project_path:
        join_room(project_path)
        session["project_path"] = project_path
        print(f"Client {request.sid} joined room {project_path}")


@socketio.on("stop_agent")
def handle_stop_agent():
    # Stop agent based on project path, not SID
    project_path = session.get("project_path")
    if project_path and project_path in active_agents:
        print(f"Stop signal received for agent in project: {project_path}")
        active_agents[project_path].stop()
    else:
        print("Received stop signal, but no active agent found for " +
              f"project: {project_path}")


@socketio.on("disconnect")
def handle_disconnect():
    # This logic may need refinement if a user can switch projects
    # For now, it stops the agent associated with their last session project
    project_path = session.get("project_path")
    print(f"Client disconnected: {request.sid}")
    if project_path and project_path in active_agents:
        active_agents[project_path].stop()
        del active_agents[project_path]
        print(
            "Stopped and removed agent for disconnected client in project: "
            f"{project_path}"
        )


@socketio.on("agent_chat")
def handle_agent_chat(data):
    """Handles a chat message from the user to the agent."""
    project_path = session.get("project_path")
    if not project_path:
        return {"error": "No project in session. Please start a project first."}

    message = data.get("message")
    if not message:
        return {"error": "Message is required."}

    agent = active_agents.get(project_path)

    # If no agent exists for this project, create one.
    if not agent:

        def broadcast_to_project(event, data=None):
            socketio.emit(event, data, room=project_path)

        agent = Agent(
            project_path=project_path,
            emit_func=broadcast_to_project,
            sleep_func=socketio.sleep,
        )
        active_agents[project_path] = agent
        print(f"Created new agent for project: {project_path}")

    # Prevent new messages if the agent is already processing one.
    if agent.is_running:
        return {
            "error": "The agent is currently busy. "
            "Please wait for the current task to complete."
        }

    # Start the agent's run method in the background.
    socketio.start_background_task(agent.run, message)
    return {"message": "Agent has received the message."}


# --- UNCHANGED ROUTES BELOW ---
@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("connect")
def handle_connect():
    session["sid"] = request.sid
    print(f"Client connected: {request.sid}. SID stored in session.")


@app.route("/api/start_project", methods=["POST"])
def start_project():
    data = request.get_json(force=True)
    project_name = data.get("name", "").strip()
    if not project_name:
        return jsonify({"error": "Project name required"}), 400

    project_path = Path("workspaces") / project_name
    project_path.mkdir(parents=True, exist_ok=True)

    session["project_path"] = str(project_path)  # Save to the user's session
    return jsonify(
        {
            "message": f"Project “{project_name}” created.",
            "project_path": str(project_path),
        }
    )


def get_directory_structure(root_path):
    """Recursively builds a directory structure as a list of dicts."""
    structure = []
    try:
        for item_name in sorted(os.listdir(root_path)):
            item_path = os.path.join(root_path, item_name)
            relative_path = os.path.relpath(
                item_path, session.get("project_path")
            )

            if item_name.startswith(".") or item_name == "__pycache__":
                continue

            if os.path.isdir(item_path):
                structure.append(
                    {
                        "name": item_name,
                        "type": "directory",
                        "path": relative_path,
                        "children": get_directory_structure(item_path),
                    }
                )
            else:
                structure.append(
                    {"name": item_name, "type": "file", "path": relative_path}
                )
        return structure
    except OSError:
        return []


def build_file_tree(root_path: str, rel_path: str = "") -> dict:
    """
    Recursively build a tree where every node.path is **relative**
    to CURRENT_PROJECT_PATH.  That way the front-end never sees an
    absolute path and can send it straight back to /api/get_file_content.
    """
    root = Path(root_path)
    here = root / rel_path
    node = here
    children = []

    if node.is_dir():
        for child in sorted(
            node.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
        ):
            child_rel = os.path.join(rel_path, child.name)
            children.append(build_file_tree(root_path, child_rel))

    return {
        "name": node.name,
        "path": rel_path.replace("\\", "/"),  # forward slashes
        "type": "file" if node.is_file() else "directory",
        "children": children,
    }


@app.route("/api/download_project")
def download_project():
    project_path = session.get("project_path")
    if not project_path:
        return jsonify({"error": "No active project in session."}), 400

    project_name = os.path.basename(project_path)

    try:
        # Note: shutil creates the archive in the current working directory.
        # It returns the full path to the created .zip file.
        zip_archive_path = shutil.make_archive(project_name,
                                               "zip",
                                               project_path)

        # This function will run *after* the file has been sent.
        @after_this_request
        def cleanup(response):
            try:
                if os.path.exists(zip_archive_path):
                    os.remove(zip_archive_path)
            except Exception as e:
                print(
                    f"Error cleaning up zip file: {e}"
                )  # Log error instead of crashing
            return response

        return send_file(zip_archive_path, as_attachment=True)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/files", methods=["GET"])
def api_files():
    project_path = session.get("project_path")
    if not project_path:
        # No project in session -> return an empty tree
        return jsonify(
            {"name": "(no-project)",
             "path": "",
             "type": "directory",
             "children": []}
        )

    try:
        tree = build_file_tree(project_path)
        return jsonify(tree)
    except Exception as exc:
        return jsonify(
            {
                "name": Path(project_path).name,
                "path": "",
                "type": "directory",
                "children": [],
                "error": str(exc),
            }
        )


@app.route("/api/get_file_content", methods=["POST"])
def get_file_content():
    project_path = session.get("project_path")
    if not project_path:
        return jsonify({"error": "No project started yet."}), 400

    data = request.get_json(force=True)
    rel_path = data.get("filename", "").replace("\\", "/").strip()
    if not rel_path:
        return jsonify({"error": "filename required"}), 400

    try:
        # This helper function handles all the security checks
        full_path = get_safe_path(project_path, rel_path)
        content = Path(full_path).read_text(encoding="utf-8", errors="ignore")
        return jsonify({"filename": rel_path, "content": content})
    except PermissionError:
        return jsonify({"error": "Path escapes project folder."}), 400
    except FileNotFoundError:
        return jsonify({"error": f"File not found: {rel_path}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/create_file", methods=["POST"])
def create_file():
    project_path = session.get("project_path")
    if not project_path:
        return jsonify({"error": "No active project session"}), 400

    data = request.get_json()
    try:
        file_path = get_safe_path(project_path, data.get("filename"))
        if os.path.exists(file_path):
            return jsonify({"error": "File already exists"}), 409
        with open(file_path, "w", encoding="utf-8"):
            pass
        filename_to_save = data.get("filename")
        socketio.emit(
            "file_system_updated",
            {"filename": filename_to_save},
            room=project_path
        )
        return jsonify({"message":
                        f"File '{os.path.basename(file_path)}' created."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/delete_file", methods=["POST"])
def delete_file_route():
    project_path = session.get("project_path")
    if not project_path:
        return jsonify({"error": "No active project session"}), 400

    data = request.get_json()
    filename = data.get("filename")
    if not filename:
        return jsonify({"error": "Filename is required"}), 400

    try:
        from tools import delete_file

        result_message = delete_file(project_path, filename)

        if "Error:" in result_message:
            return jsonify({"error": result_message}), 404

        filename_to_save = data.get("filename")
        socketio.emit(
            "file_system_updated",
            {"filename": filename_to_save},
            room=project_path
        )
        return jsonify({"message": result_message})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/save_file_content", methods=["POST"])
def save_file_content():
    project_path = session.get("project_path")
    if not project_path:
        return jsonify({"error": "No active project session"}), 400

    data = request.get_json()
    try:
        file_path = get_safe_path(project_path, data.get("filename"))
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(data.get("content", ""))
        filename_to_save = data.get("filename")
        socketio.emit(
            "file_system_updated",
            {"filename": filename_to_save},
            room=project_path
        )
        return jsonify({"message":
                        f"File '{os.path.basename(file_path)}' saved."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/execute_code", methods=["POST"])
def execute_code():
    project_path = session.get("project_path")
    if not project_path:
        return jsonify({"error": "No active project session"}), 400

    data = request.get_json()
    code = data.get("code", "")
    if not code.strip():
        return jsonify({"error": "Cannot execute empty code"}), 400

    temp_filename = f"temp_{uuid.uuid4()}.py"

    try:
        temp_filepath = get_safe_path(project_path, temp_filename)
        with open(temp_filepath, "w", encoding="utf-8") as f:
            f.write(code)

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"

        result = subprocess.run(
            ["python", temp_filename],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=project_path,
            encoding="utf-8",
            env=env,
        )

        return jsonify(
            {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
            }
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Execution timed out after 30 seconds."}), 408
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if "temp_filepath" in locals() and os.path.exists(temp_filepath):
            os.remove(temp_filepath)


@app.route("/api/create_folder", methods=["POST"])
def create_folder():
    project_path = session.get("project_path")
    if not project_path:
        return jsonify({"error": "No active project session"}), 400

    data = request.get_json()
    folder_path = data.get("path")
    if not folder_path:
        return jsonify({"error": "Folder path is required"}), 400

    try:
        full_path = get_safe_path(project_path, folder_path)
        if os.path.exists(full_path):
            return jsonify({"error":
                            "Folder or file already exists at that path"}), 409

        os.makedirs(full_path)
        filename_to_save = data.get("filename")
        socketio.emit(
            "file_system_updated",
            {"filename": filename_to_save},
            room=project_path
        )
        return jsonify({"message":
                        f"Folder '{folder_path}' created successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/delete_folder", methods=["POST"])
def delete_folder():
    project_path = session.get("project_path")
    if not project_path:
        return jsonify({"error": "No active project session"}), 400

    data = request.get_json()
    folder_path = data.get("path")
    if not folder_path:
        return jsonify({"error": "Folder path is required"}), 400

    try:
        full_path = get_safe_path(project_path, folder_path)
        if not os.path.isdir(full_path):
            return jsonify({"error":
                            "The specified path is not a directory."}), 400

        shutil.rmtree(full_path)
        filename_to_save = data.get("filename")
        socketio.emit(
            "file_system_updated",
            {"filename": filename_to_save},
            room=project_path
        )
        return jsonify(
            {
                "message": f"Folder '{folder_path}' and all its contents "
                           "have been deleted."
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        debug=False,
        use_reloader=False,
        port=5001,
        allow_unsafe_werkzeug=True,
    )
