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

OLLAMA_ENDPOINT = "http://192.168.86.30:11434/api/generate"
OLLAMA_MODEL = "qwen3:8B"

def _extract_first_json(text: str) -> str | None:
    """
    Return the first **balanced** JSON object or array found in `text`.
    Handles nested braces/brackets and ignores string literals.
    """
    start_obj = text.find('{')
    start_arr = text.find('[')

    if start_obj == -1 and start_arr == -1:
        return None

    # whichever appears first
    if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
        opening, closing, pos = '[', ']', start_arr
    else:
        opening, closing, pos = '{', '}', start_obj

    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[pos:], pos):
        if in_str:
            esc = (ch == '\\' and not esc)
            if ch == '"' and not esc:
                in_str = False
            continue

        if ch == '"':
            in_str = True
        elif ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return text[pos:i + 1]
    return None

def call_llm_stream(prompt, emit_func):
    """
    Calls the LLM with a prompt and streams the response.
    Returns the full aggregated response string at the end.
    """
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

                        # FIX: Check for the 'done' signal from the API
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
        self.max_consecutive_failures = 3

    def log(self, message):
        print(f"Agent Log: {message}")
        self.log_history.append(message)
        self.emit('agent_log', {'message': message})
        time.sleep(0.5)

    def stop(self):
        self.log("Stop signal received. Finishing current step...")
        self.stop_requested = True

    def run(self, objective):
        """The main entry point for the agent to start a task."""
        self.is_running = True
        self.stop_requested = False
        self.conversation_history = [{"role": "user", "content": objective}]

        try:
            # Phase 0: Get Context.
            self.log("Phase 0: Generating initial project code map...")
            code_map = generate_code_map(self.project_path)
            self.log("Initial code map generated.")

            # Enter the main planning-execution loop
            while self.is_running and not self.stop_requested:
                # Phase 1: Plan with Context.
                self.log("Phase 1: Creating a new plan...")
                plan = self._create_plan(code_map)

                if not plan:
                    self.log("Failed to create a plan. Aborting task.")
                    break # Exit the loop if planning fails

                # Phase 2: Execute with Context.
                execution_status = self._execute_plan(plan, code_map)

                if execution_status == "REPLAN_REQUESTED":
                    self.log("Re-planning as requested by the agent.")
                    # The loop will now naturally restart, creating a new plan
                    code_map = generate_code_map(self.project_path) # Refresh map before replanning
                    continue
                else:
                    # If execution finished successfully or failed without a replan, exit.
                    break

        finally:
            self.log("Task finished.")
            self.is_running = False
            self.emit('task_finished')

    def _create_plan(self, code_map: str):
        """Generates the initial high-level plan using a provided code map."""
        self.log("Creating a plan with full project context...")
        self.emit('agent_thinking')

        planning_prompt = f"""
        You are a diligent and thoughtful AI planning assistant. Your goal is to create a robust, step-by-step plan in a JSON array of strings.

        **Guidelines:**

        1.  **Analyze the Code Map:** Base your plan on the files and components outlined in the **Project Code Map**.
        2.  **Stick to Facts:** Avoid making assumptions about files that don't exist.
        3.  **Clear Steps:** Each string in the JSON array should be a clear, high-level step.
        4.  **JSON Format:** Your final output must be a JSON array of strings.

        **Example of a good plan:**
        ```json
        [
            "Delete the old 'menu.py' and 'menu_functions.py' files as they are not well-integrated.",
            "Rewrite 'main.py' to be the single entry point for the game, containing all logic.",
            "Execute the new 'main.py' to test the final game."
        ]
        ```

        **Available Tools:**
        {self.tool_registry.get_tool_definitions()}

        ---
        ## **Project Code Map**
        {code_map}
        ---

        ## **User Request:**
        {self.conversation_history[-1]['content']}

        Please provide the plan as a single, valid JSON array of strings.
        """

        response_str = call_llm_stream(planning_prompt, self.emit)
        if not response_str:
            self.log("Planning failed: LLM call returned no response.")
            return None

        return self._parse_json_plan(response_str)

    def _execute_plan(self, plan: list, code_map: str):
        """
        Executes a plan, handling failures and replan signals robustly.
        If any step fails or a replan is requested, it aborts the plan and returns a status.
        """
        self.log(f"Phase 2: Executing plan ({len(plan)} steps)")
        current_code_map = code_map

        for step_index, step in enumerate(plan):
            if self.stop_requested:
                self.log("Execution stopped by user.")
                return "STOPPED"

            # The f-string here correctly uses the full length of the current plan
            self.log(f"--- Executing Step {step_index + 1}/{len(plan)}: {step} ---")

            action_json = self._determine_next_action(plan, step, current_code_map, self.conversation_history)

            if not action_json:
                self.log(f"Failed to determine action for step. Requesting a new plan.")
                self.conversation_history.append({"role": "system", "content": "Could not determine the next action. A new plan is required."})
                return "REPLAN_REQUESTED"

            # This is the critical check. If the agent decides to replan, we stop everything.
            if action_json.get("tool_name") == 'replan':
                self.log("Agent has requested a replan. Aborting current plan.")
                reason = action_json.get("arguments", {}).get("reason", "No reason specified.")
                self.conversation_history.append({"role": "system", "content": f"The plan was flawed. Reason: {reason}. A new plan is required."})
                return "REPLAN_REQUESTED" # This return exits the function

            result = self._execute_tool(action_json)

            if "Error:" in result or "failed" in result.lower():
                self.log(f"Step failed critically. Error: {result}")
                self.log("Aborting current plan and requesting a new one.")
                self.conversation_history.append({"role": "system", "content": f"The last step failed. Reason: {result}. A new plan is required to correct the error."})
                return "REPLAN_REQUESTED"

            if action_json.get("tool_name") in ['save_file', 'delete_file', 'create_folder', 'delete_folder']:
                self.log("File system changed. Refreshing code map for the next step...")

                filename_changed = action_json.get("arguments", {}).get("filename")
                self.emit('file_system_updated', {'filename': filename_changed})

                current_code_map = generate_code_map(self.project_path)

        self.log("Plan execution completed successfully.")
        return "COMPLETED"

    def _determine_next_action(self, plan: list, current_step: str, code_map: str, conversation_history: list):
        """Calls the LLM to get the next tool call for a given step, using the code map."""
        self.emit('agent_thinking')

        execution_prompt = f"""
        You are a helpful AI assistant. Your task is to execute one step from a plan by emitting a single JSON tool call.

        **Context:**

        1.  **Code Map:** Refer to the **Project Code Map** for the current state of the files.
        2.  **Conversation History:** Review the **Conversation History** to understand the user's goals and previous actions.
        3.  **Current Task:** Focus on executing the **Current Task** from the plan.
        4.  **Tool Use:** If a task is too complex for one tool, use the `replan` tool to request a better plan.
        5.  **Code Generation:** When writing code, do not use placeholders. Write the full code yourself.

        **Example `replan` call:**
        ```json
        {{
            "thought": "The current step requires deleting two files, but `delete_file` only handles one at a time. I need to replan.",
            "action": {{
                "tool_name": "replan",
                "arguments": {{
                    "reason": "The plan step 'Delete file A and file B' is invalid. The plan should have separate steps for each file deletion."
                }}
            }}
        }}
        ```

        **Response Format:**
        Your response must be a single JSON object with "thought" and "action" keys.

        **Available Tools:**
        {self.tool_registry.get_tool_definitions()}

        ---
        ## **Conversation History**
        {json.dumps(conversation_history, indent=2)}
        ---
        ## **Project Code Map**
        {code_map}
        ---
        ## **Plan:**
        {json.dumps(plan)}
        ---
        ## **Current Task:**
        **{current_step}**

        Generate the required JSON response.
        """
        response_str = call_llm_stream(execution_prompt, self.emit)
        if not response_str:
            self.log("Action determination failed: LLM call returned no response.")
            return None

        return self._parse_json_action(response_str)

    def _execute_tool(self, action_json: dict):
        """Executes a tool and returns the result."""
        try:
            tool_name = action_json["tool_name"]
            arguments = action_json.get("arguments", {})
            self.conversation_history.append({"role": "agent", "content": json.dumps(action_json, indent=2)})

            tool_function = self.tool_registry.get_tool(tool_name)
            if not tool_function:
                result = f"Error: Unknown tool '{tool_name}'"
            else:
                self.log(f"Action: {tool_name}, Arguments: {arguments}")
                # Pass project_path to all tools, and unpack the rest of the args
                result = str(tool_function(self.project_path, **arguments))
        except Exception as e:
            result = f"Error executing tool '{tool_name}': {e}"

        self.log(f"Result: {result}")
        self.conversation_history.append({"role": "tool", "content": result})
        return result

    def _parse_json_plan(self, response_str: str):
        """
        Parses the plan from an LLM response, with self-correction for format errors.
        """
        try:
            # First attempt to parse and validate
            json_str = _extract_first_json(response_str)
            if not json_str:
                raise ValueError("No JSON array found in the response.")

            plan_data = json.loads(json_str)

            plan = []
            if isinstance(plan_data, list):
                plan = plan_data
            elif isinstance(plan_data, dict):
                plan = plan_data.get("plan", [])

            if not isinstance(plan, list) or not all(isinstance(i, str) for i in plan):
                raise ValueError("Parsed data is not a valid plan (a JSON array of strings).")

            # If successful, log and return
            self.log("Plan created successfully.")
            self.emit('agent_plan_created', {'plan': plan})
            self.conversation_history.append({"role": "agent", "content": f"I have created a plan: {json.dumps(plan)}"})
            return plan

        except (ValueError, json.JSONDecodeError) as e:
            self.log(f"Planning failed: {e}. Attempting to self-correct the plan format...")
            print(f"--- FAILED TO PARSE PLAN ---\n{response_str}\n--------------------------")

            # If parsing fails, ask the LLM to fix its own output.
            correction_prompt = f'''
            The following text was supposed to be a single, valid JSON array of strings, but it is malformed or in the wrong format.
            Correct the syntax errors and ensure the output is ONLY a valid JSON array of strings.

            Example of a correct response:
            [
                "Delete the old 'menu.py' file.",
                "Rewrite 'main.py' to contain all game logic.",
                "Execute 'main.py' to test the final game."
            ]

            Broken text:
            {response_str}

            Return ONLY the corrected, valid JSON array of strings. Do not add any other text or commentary.
            '''

            corrected_response = call_llm_stream(correction_prompt, None)
            try:
                # Re-run validation on the corrected response
                json_str = _extract_first_json(corrected_response)
                if not json_str:
                    raise ValueError("No JSON array found in the corrected response.")

                corrected_data = json.loads(json_str)

                plan = []
                if isinstance(corrected_data, list):
                    plan = corrected_data
                elif isinstance(corrected_data, dict):
                    plan = corrected_data.get("plan", [])

                if not isinstance(plan, list) or not all(isinstance(i, str) for i in plan):
                    raise ValueError("Corrected data is still not a valid plan (a JSON array of strings).")

                self.log("Plan created successfully after self-correction.")
                self.emit('agent_plan_created', {'plan': plan})
                self.conversation_history.append({"role": "agent", "content": f"I have created a plan: {json.dumps(plan)}"})
                return plan

            except (ValueError, json.JSONDecodeError) as final_e:
                self.log(f"Fatal Error: Plan self-correction failed. The corrected response was still invalid. Error: {final_e}")
                print(f"--- FAILED TO PARSE CORRECTED PLAN ---\n{corrected_response}\n--------------------------------------")
                self.conversation_history.append({"role": "system", "content": f"Error: Failed to create a valid plan. Response was: {corrected_response}"})
                return None

    def _parse_json_action(self, response_str: str):
        """
        Parses a tool action from an LLM response, with a built-in
        self-correction mechanism to handle malformed JSON.
        """
        try:
            # First-pass attempt to find and parse a valid JSON object.
            json_str = _extract_first_json(response_str)
            if not json_str:
                raise ValueError("No JSON object found in the response.")

            action_data = json.loads(json_str)

            # Stricter validation of the parsed JSON.
            if not isinstance(action_data, dict):
                raise ValueError("JSON is not a dictionary/object.")
            if "thought" not in action_data or "action" not in action_data:
                raise ValueError("Response missing 'thought' or 'action' keys.")
            action = action_data.get("action")
            if not isinstance(action, dict) or "tool_name" not in action:
                raise ValueError("The 'action' key must be an object with a 'tool_name'.")

            self.log(f"Thought: {action_data['thought']}")
            return action_data['action'] # Return the action object

        except (ValueError, json.JSONDecodeError) as e:
            self.log(f"Action parsing failed: {e}. Attempting to self-correct...")
            print(f"--- FAILED TO PARSE ACTION ---\n{response_str}\n----------------------------")

            # If parsing fails, ask the LLM to fix its own output.
            correction_prompt = f'''
            The following text was supposed to be a single, valid JSON object, but it is malformed.
            Correct the syntax errors and return ONLY the valid JSON object.

            The JSON object MUST have a "thought" key (string) and an "action" key.
            The "action" key's value MUST be another JSON object containing a "tool_name" (string) and "arguments" (object).

            Example of a correct response:
            {{
                "thought": "I need to read the main file.",
                "action": {{
                    "tool_name": "read_file",
                    "arguments": {{ "filename": "main.py" }}
                }}
            }}

            Broken text:
            {response_str}

            Return ONLY the corrected, valid JSON object. Do not add any other text or commentary.
            '''

            corrected_response = call_llm_stream(correction_prompt, None) # No streaming for correction
            try:
                # Re-run validation on the corrected response
                json_str = _extract_first_json(corrected_response)
                if not json_str:
                    raise ValueError("No JSON object found in the corrected response.")

                corrected_data = json.loads(json_str)

                if "thought" not in corrected_data or "action" not in corrected_data:
                    raise ValueError("Corrected response is still missing 'thought' or 'action' keys.")

                action = corrected_data.get("action")
                if not isinstance(action, dict) or "tool_name" not in action:
                    raise ValueError("The corrected 'action' key must be an object with a 'tool_name'.")

                self.log(f"Thought (after correction): {corrected_data.get('thought', 'N/A')}")
                return corrected_data['action']
            except (ValueError, json.JSONDecodeError) as final_e:
                self.log(f"Fatal Error: Self-correction failed. The corrected response was still invalid. Error: {final_e}")
                print(f"--- FAILED TO PARSE CORRECTED ACTION ---\n{corrected_response}\n--------------------------------------")
                return None
