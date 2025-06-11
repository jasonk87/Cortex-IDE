# main.py

import autogen
import os

# Create a 'project_files' directory to store the output
if not os.path.exists("project_files"):
    os.makedirs("project_files")

# --- Agent Configuration ---

# For this example, we'll use a local LLM.
# Make sure your Ollama or other local server is running.
config_list = [
    {
        # NOTE: Update this with your actual model and endpoint.
        "model": "qwen3:8B",
        "base_url": "http://192.168.86.30:11434/v1",
        "api_key": "ollama",
    }
]

# LLM configuration for the agents
llm_config = {
    "config_list": config_list,
    "cache_seed": 42, # Use a seed for reproducibility
}

# --- Agent Roles ---

# 1. Planner/Project Manager Agent
planner = autogen.AssistantAgent(
    name="Planner",
    llm_config=llm_config,
    system_message="""You are a project planner. Your job is to create a step-by-step plan to build a web application.
    The application should have a UI with three panels: a file tree on the left, a central panel for logs/chat, and a file editor on the right, inspired by 'go-agent-company/frontend/index.html'.
    Break down the task into small, manageable steps for the developers. Start with creating a simple Python Flask backend to serve an HTML file and provide a file API.
    Ensure each step results in a single, complete, and correct file. The project files must be saved inside the 'project_files/' directory.
    When the project is complete, you must state that the goal has been achieved and `TERMINATE`.
    """
)

# 2. Developer Agent (handles both Frontend and Backend)
developer = autogen.AssistantAgent(
    name="Developer",
    llm_config=llm_config,
    system_message="""You are a senior software developer. You will write Python Flask code for the backend and HTML/CSS/JS for the frontend.
    You must write complete, correct, and runnable code. Do not use placeholder comments.
    All files must be created in the 'project_files/' directory.
    - For the backend, create a file `app.py`. It should have two routes:
        1. A root route `/` that serves an `index.html` file.
        2. An API route `/api/files` that returns a JSON list of filenames in the `project_files/` directory.
    - For the frontend, create an `index.html` file. It should fetch data from the `/api/files` endpoint and display it.
    Wait for the Planner to give you a task.
    """
)

# 3. Critic Agent
critic = autogen.AssistantAgent(
    name="Critic",
    llm_config=llm_config,
    system_message="""You are a code critic. Your job is to review the code and the plan for any flaws, errors, or inconsistencies.
    You must verify that the code is complete and adheres to the plan. You should also check for bugs.
    You do not write code, but you can suggest improvements.
    """
)

# 4. User Proxy Agent (with code execution)
user_proxy = autogen.UserProxyAgent(
    name="User_Proxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=10,
    is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
    code_execution_config={
        "work_dir": "project_files", # Set the working directory for code execution
        "use_docker": False,
    },
    llm_config=llm_config,
    system_message="A human user. Executes code and reports back the results."
)


# --- Group Chat Setup ---

groupchat = autogen.GroupChat(
    agents=[user_proxy, planner, developer, critic],
    messages=[],
    max_round=20
)
manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=llm_config)


# --- Start the Task ---

user_proxy.initiate_chat(
    manager,
    message="""
    Let's build a web application from scratch.
    
    The UI should be inspired by the 'go-agent-company/frontend/index.html' file, featuring a three-panel layout: a file tree, a main content/log area, and a file editor.
    
    Please start by creating a plan, then write the necessary backend and frontend files. All generated code should be placed in the 'project_files/' directory.
    """
)