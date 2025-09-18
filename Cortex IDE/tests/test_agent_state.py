import os
import json
import pytest
from unittest.mock import patch, MagicMock
from agent import Agent

DUMMY_PROJECT_PATH = "/tmp/dummy_project_for_agent_state_test"


@pytest.fixture(autouse=True)
def setup_teardown():
    """Ensure the dummy project path exists and is clean for each test."""
    os.makedirs(DUMMY_PROJECT_PATH, exist_ok=True)
    state_dir = os.path.join(DUMMY_PROJECT_PATH, ".cortex_agent")
    if os.path.exists(state_dir):
        for f in os.listdir(state_dir):
            os.remove(os.path.join(state_dir, f))
        os.rmdir(state_dir)
    yield
    if os.path.exists(state_dir):
        for f in os.listdir(state_dir):
            os.remove(os.path.join(state_dir, f))
        os.rmdir(state_dir)


@patch("agent.ToolRegistry")
@patch("agent.MemoryManager")
def test_save_state(mock_memory_manager, mock_tool_registry):
    """Tests that the agent's state is saved correctly."""
    agent = Agent(
        project_path=DUMMY_PROJECT_PATH,
        emit_func=MagicMock(),
        sleep_func=MagicMock(),
    )
    agent.objective = "test objective"
    agent.plan = ["step 1", "step 2"]
    agent.conversation_history = [{"role": "user", "content": "hello"}]

    agent.save_state()

    state_file = os.path.join(DUMMY_PROJECT_PATH, ".cortex_agent", "state.json")
    assert os.path.exists(state_file)

    with open(state_file, "r") as f:
        state = json.load(f)

    assert state["objective"] == "test objective"
    assert state["plan"] == ["step 1", "step 2"]
    assert state["conversation_history"] == [{"role": "user", "content": "hello"}]


@patch("agent.ToolRegistry")
@patch("agent.MemoryManager")
def test_load_state_success(mock_memory_manager, mock_tool_registry):
    """Tests that the agent's state is loaded correctly when the objective matches."""
    agent = Agent(
        project_path=DUMMY_PROJECT_PATH,
        emit_func=MagicMock(),
        sleep_func=MagicMock(),
    )
    agent.objective = "test objective"

    state_dir = os.path.join(DUMMY_PROJECT_PATH, ".cortex_agent")
    os.makedirs(state_dir, exist_ok=True)
    state = {
        "objective": "test objective",
        "plan": ["step 1", "step 2"],
        "conversation_history": [{"role": "user", "content": "hello"}],
    }
    with open(os.path.join(state_dir, "state.json"), "w") as f:
        json.dump(state, f)

    assert agent.load_state() is True
    assert agent.plan == ["step 1", "step 2"]
    assert agent.conversation_history == [{"role": "user", "content": "hello"}]


@patch("agent.ToolRegistry")
@patch("agent.MemoryManager")
def test_load_state_objective_mismatch(mock_memory_manager, mock_tool_registry):
    """Tests that the agent's state is not loaded when the objective does not match."""
    agent = Agent(
        project_path=DUMMY_PROJECT_PATH,
        emit_func=MagicMock(),
        sleep_func=MagicMock(),
    )
    agent.objective = "new objective"

    state_dir = os.path.join(DUMMY_PROJECT_PATH, ".cortex_agent")
    os.makedirs(state_dir, exist_ok=True)
    state = {
        "objective": "old objective",
        "plan": ["step 1", "step 2"],
        "conversation_history": [{"role": "user", "content": "hello"}],
    }
    with open(os.path.join(state_dir, "state.json"), "w") as f:
        json.dump(state, f)

    assert agent.load_state() is False
    assert agent.plan == []
    assert agent.conversation_history == []


@patch("agent.ToolRegistry")
@patch("agent.MemoryManager")
def test_clear_state(mock_memory_manager, mock_tool_registry):
    """Tests that the agent's state file is cleared correctly."""
    state_dir = os.path.join(DUMMY_PROJECT_PATH, ".cortex_agent")
    os.makedirs(state_dir, exist_ok=True)
    state_file = os.path.join(state_dir, "state.json")
    with open(state_file, "w") as f:
        f.write("test")

    agent = Agent(
        project_path=DUMMY_PROJECT_PATH,
        emit_func=MagicMock(),
        sleep_func=MagicMock(),
    )
    agent.clear_state()

    assert not os.path.exists(state_file)
