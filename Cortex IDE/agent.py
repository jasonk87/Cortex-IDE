# agent.py
import json
import re
import requests
import time
from tools import ToolRegistry, generate_code_map
import os
import ast
from pathlib import Path
from typing import Dict, List, Any
from memory_manager import MemoryManager

# Load configuration from config.json
try:
    with open('Cortex IDE/config.json', 'r') as f:
        config = json.load(f)
    OLLAMA_ENDPOINT = config.get("OLLAMA_ENDPOINT", "http://127.0.0.1:11434/api/generate")
    OLLAMA_MODEL = config.get("OLLAMA_MODEL", "llama2")
except (FileNotFoundError, json.JSONDecodeError):
    OLLAMA_ENDPOINT = "http://127.0.0.1:11434/api/generate"
    OLLAMA_MODEL = "llama2"

def _extract_first_json(text: str) -> str | None:
    # Simplified JSON extraction
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            # Verify it's valid JSON
            json.loads(match.group(0))
            return match.group(0)
        except json.JSONDecodeError:
            return None
    return None

def call_llm_stream(prompt, emit_func):
    full_response = ""
    try:
        with requests.post(
            OLLAMA_ENDPOINT,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": True, "options": {"temperature": 0.0, "num_ctx": 8192}},
            stream=True, timeout=180
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_lines():
                if chunk:
                    decoded_chunk = chunk.decode('utf-8')
                    try:
                        json_chunk = json.loads(decoded_chunk)
                        content = json_chunk.get("response", "")
                        full_response += content
                        if emit_func:
                            emit_func('agent_stream_chunk', {'chunk': content})
                        if json_chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
        print("\n--- RAW LLM STREAM RESPONSE ---\n")
        print(full_response)
        print("\n-----------------------------\n")
        return full_response
    except requests.exceptions.RequestException as e:
        if emit_func:
            emit_func('agent_log', {'message': f"Error calling LLM: {e}"})
        return ""

class Agent:
    def __init__(self, project_path, emit_func, sleep_func):
        self.project_path = project_path
        self.emit = emit_func
        self.sleep = sleep_func
        self.tool_registry = ToolRegistry(project_path)
        self.conversation_history = []
        self.log_history = []
        self.is_running = False
        self.stop_requested = False
        self.memory = MemoryManager(project_path)
        self.log("MemoryManager initialized.")

    def log(self, message):
        print(f"Agent Log: {message}")
        self.log_history.append(message)
        self.emit('agent_log', {'message': message})
        time.sleep(0.5)

    def stop(self):
        self.log("Stop signal received. Finishing current step...")
        self.stop_requested = True

    def run(self, objective):
        self.is_running = True
        self.stop_requested = False
        self.conversation_history.append({"role": "user", "content": objective})

        try:
            self.log("Phase 1: Creating a high-level plan...")
            plan = self._create_high_level_plan()
            if not plan:
                self.log("Failed to create a plan. Aborting task.")
                return

            self.log("Executing plan...")
            for i, step in enumerate(plan):
                if self.stop_requested:
                    self.log("Execution stopped by user.")
                    break

                self.log(f"--- Executing Step {i+1}/{len(plan)}: {step} ---")
                status = self._execute_step_with_react(step)
                if status != "COMPLETED":
                    self.log(f"Step failed with status: {status}. Aborting task.")
                    break

            if not self.stop_requested:
                self.log("All steps completed successfully.")
                self._summarize_and_save_memory()

        finally:
            self.log("Task finished.")
            self.is_running = False
            self.emit('task_finished')

    def _create_high_level_plan(self):
        # This method now only creates the high-level plan, not sub-plans.
        # The ReAct loop handles the low-level execution.
        last_user_message = self.conversation_history[-1]['content']
        relevant_memories = self.memory.search_memories(last_user_message, n_results=3)
        memories_context = "No relevant memories found."
        if relevant_memories:
            self.log(f"Found {len(relevant_memories)} relevant memories.")
            formatted_memories = "\n".join([f"- {mem}" for mem in relevant_memories])
            memories_context = f"Here are some relevant memories from past tasks:\n{formatted_memories}"

        planning_prompt = f"""
        You are an expert AI software developer. Your goal is to create a high-level, step-by-step plan to accomplish the user's objective. The plan should consist of logical steps, not tool calls. The execution of each step will be handled by a separate ReAct loop.

        **INSTRUCTIONS: CHAIN OF THOUGHT**
        1.  **Deconstruct the Goal:** What is the user's ultimate objective?
        2.  **Identify Key Stages:** What are the major phases needed (e.g., setup, implementation, testing, cleanup)?
        3.  **Draft the Steps:** Create a high-level plan. Each step should be a clear, logical objective for the ReAct agent to achieve.

        **CONTEXT:**
        **Relevant Memories:**
        {memories_context}
        ---
        **Full Conversation History:**
        {json.dumps(self.conversation_history, indent=2)}
        ---
        **Project Code Map:**
        {generate_code_map(self.project_path)}
        ---
        Begin your thinking process now. After you have reasoned through the plan, provide the JSON output.
        """

        self.emit('agent_thinking')
        response_str = call_llm_stream(planning_prompt, self.emit)
        if not response_str:
            self.log("Planning failed: LLM call returned no response.")
            return None
        return self._parse_json_plan(response_str)

    def _execute_step_with_react(self, objective: str, max_iterations=10):
        """
        Executes a single high-level plan step using a ReAct loop.
        """
        react_history = []
        for i in range(max_iterations):
            if self.stop_requested:
                return "STOPPED"

            self.log(f"ReAct Iteration {i+1}/{max_iterations} for objective: '{objective}'")

            code_map = generate_code_map(self.project_path)

            react_prompt = f"""
            You are an autonomous agent executing a task. Your goal is to achieve the following objective: **{objective}**

            You will proceed in a Reason-Act-Observe loop.
            1.  **Reason:** Based on the objective and previous observations, decide the best tool to use next. Your reasoning should be concise.
            2.  **Act:** Output a single, valid JSON tool call.

            **Previous Actions & Observations:**
            {json.dumps(react_history, indent=2)}

            **Available Tools:**
            {self.tool_registry.get_tool_definitions()}

            **Project Code Map:**
            {code_map}
            ---
            Provide your reasoning and then the action to take.
            """

            self.emit('agent_thinking')
            response_str = call_llm_stream(react_prompt, self.emit)
            if not response_str:
                self.log("ReAct failed: LLM call returned no response.")
                return "REACT_FAILED"

            action_json = self._parse_json_action(response_str)
            if not action_json:
                self.log("ReAct failed: Could not parse action from LLM response.")
                # Add the failed response to history so it can self-correct
                react_history.append({"observation": f"Error: Invalid JSON action provided. Raw response: {response_str}"})
                continue

            # The 'finish' tool indicates the objective for this step is complete.
            if action_json.get("tool_name") == 'finish':
                self.log(f"Agent concluded objective '{objective}' is complete. Reason: {action_json.get('arguments', {}).get('reason', 'N/A')}")
                return "COMPLETED"

            observation = self._execute_tool(action_json)
            react_history.append({
                "action": action_json,
                "observation": observation
            })

            # Keep history from getting too long
            if len(react_history) > 5:
                react_history.pop(0)

        self.log("Reached max iterations for ReAct loop.")
        return "MAX_ITERATIONS_REACHED"

    def _summarize_and_save_memory(self):
        self.log("Reflecting on the completed task to create a memory...")
        summarization_prompt = f"""
        Based on the conversation, what is the most important lesson learned or accomplishment?
        Summarize it as a concise, single sentence for a future AI agent.

        CONVERSATION:
        {json.dumps(self.conversation_history, indent=2)}

        Respond with only the single sentence summary.
        """
        self.emit('agent_thinking')
        summary = call_llm_stream(summarization_prompt, None)
        if summary:
            summary = summary.strip().replace('"', '')
            self.log(f"Generated memory summary: {summary}")
            self.memory.add_memory(summary)
        else:
            self.log("Could not generate a memory for this task.")

    def _execute_tool(self, action_json: dict):
        try:
            tool_name = action_json["tool_name"]
            arguments = action_json.get("arguments", {})
            self.conversation_history.append({"role": "agent", "content": json.dumps(action_json, indent=2)})
            tool_function = self.tool_registry.get_tool(tool_name)
            if not tool_function:
                result = f"Error: Unknown tool '{tool_name}'"
            else:
                self.log(f"Action: {tool_name}, Arguments: {arguments}")
                result = str(tool_function(self.project_path, **arguments))
        except Exception as e:
            result = f"Error executing tool '{tool_name}': {e}"

        self.log(f"Result: {result}")
        self.conversation_history.append({"role": "tool", "content": result})
        return result

    def _parse_json_plan(self, response_str: str):
        try:
            json_str = _extract_first_json(response_str)
            if not json_str:
                raise ValueError("No JSON array found in the response.")
            plan_data = json.loads(json_str)
            plan = plan_data if isinstance(plan_data, list) else plan_data.get("plan", [])
            if not isinstance(plan, list) or not all(isinstance(i, str) for i in plan):
                raise ValueError("Parsed data is not a valid plan (a JSON array of strings).")
            self.log("Plan created successfully.")
            self.emit('agent_plan_created', {'plan': plan})
            self.conversation_history.append({"role": "agent", "content": json.dumps({"plan": plan})})
            return plan
        except (ValueError, json.JSONDecodeError) as e:
            self.log(f"Fatal Error: Plan parsing failed. Error: {e}")
            return None

    def _parse_json_action(self, response_str: str):
        try:
            json_str = _extract_first_json(response_str)
            if not json_str:
                raise ValueError("No JSON object found in the response.")
            action_data = json.loads(json_str)
            if not isinstance(action_data, dict) or "action" not in action_data:
                raise ValueError("Response missing 'action' key.")
            action = action_data.get("action")
            if not isinstance(action, dict) or "tool_name" not in action:
                raise ValueError("The 'action' key must be an object with a 'tool_name'.")
            self.log(f"Thought: {action_data.get('thought', 'N/A')}")
            return action
        except (ValueError, json.JSONDecodeError) as e:
            self.log(f"Action parsing failed: {e}. Raw response: {response_str}")
            return None
