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
        self.conversation_history.append({"role": "user", "content": objective})

        try:
            # Phase 0: Get Context.
            self.log("Phase 0: Generating initial project code map...")
            code_map = generate_code_map(self.project_path)
            self.log("Initial code map generated.")

            # Phase 1: Create the main plan
            self.log("Phase 1: Creating a new plan...")
            main_plan = self._create_plan(self.conversation_history)
            if not main_plan:
                self.log("Failed to create a main plan. Aborting task.")
                return

            # Phase 2: Execute the main plan
            execution_status = self._execute_plan(main_plan, code_map)

            if execution_status == "COMPLETED":
                self.log("Main plan executed successfully.")
            else:
                self.log(f"Main plan execution failed with status: {execution_status}")

        finally:
            self.log("Task finished.")
            self.is_running = False
            self.emit('task_finished')

    def _create_plan(self, conversation_history, is_sub_plan=False, failed_step=""):
        """
        Generates a plan or a sub-plan based on the conversation history.
        """
        if is_sub_plan:
            self.log("Creating a sub-plan...")
            prompt_context = f"""
            You are a sub-planner. Your goal is to break down the following complex or failed task into a series of simple, executable steps.
            The original task was: '{failed_step}'
            """
        else:
            self.log("Creating a plan with full project context...")
            prompt_context = "You are a diligent and thoughtful AI planning assistant. Your goal is to create a robust, step-by-step plan."

        planning_prompt = f"""
        {prompt_context}

        **Guidelines:**
        1.  **Analyze Context:** Base your plan on the **Full Conversation History** and the **Project Code Map**.
        2.  **Correct Errors:** If you are creating a sub-plan, your purpose is to correct a previous error or break down a complex step.
        3.  **JSON Format:** Your final output must be a JSON array of strings.

        **Available Tools:**
        {self.tool_registry.get_tool_definitions()}

        ---
        ## **Full Conversation History**
        {json.dumps(conversation_history, indent=2)}
        ---
        ## **Project Code Map**
        {generate_code_map(self.project_path)}
        ---
        Please provide the plan as a single, valid JSON array of strings.
        """

        self.emit('agent_thinking')
        response_str = call_llm_stream(planning_prompt, self.emit)
        if not response_str:
            self.log("Planning failed: LLM call returned no response.")
            return None

        return self._parse_json_plan(response_str)


    def _execute_plan(self, plan: list, code_map: str, depth=0):
        """
        Recursively executes a plan. If a sub-plan is created, it calls itself to execute it.
        """
        plan_type = "Sub-plan" if depth > 0 else "Plan"
        self.log(f"Executing {plan_type} ({len(plan)} steps)")

        current_code_map = code_map
        for step_index, step in enumerate(plan):
            if self.stop_requested:
                self.log(f"Execution stopped by user during {plan_type}.")
                return "STOPPED"

            self.log(f"--- Executing Step {step_index + 1}/{len(plan)} of {plan_type}: {step} ---")

            action_json = self._determine_next_action(plan, step, current_code_map, self.conversation_history)

            if not action_json:
                self.log(f"Failed to determine action for step. Aborting {plan_type}.")
                return "ACTION_FAILED"

            if action_json.get("tool_name") == 'replan':
                self.log(f"Step requires a sub-plan. Reason: {action_json.get('arguments', {}).get('reason', 'N/A')}")

                sub_plan = self._create_plan(self.conversation_history, is_sub_plan=True, failed_step=step)

                if not sub_plan:
                    self.log("Failed to create sub-plan. Aborting current plan.")
                    return "REPLAN_FAILED"

                # Recursive call to execute the sub-plan
                sub_plan_status = self._execute_plan(sub_plan, current_code_map, depth + 1)

                if sub_plan_status != "COMPLETED":
                    self.log(f"Sub-plan execution failed with status {sub_plan_status}. Aborting main plan.")
                    return "SUB_PLAN_FAILED"

                self.log("Sub-plan completed successfully. Resuming main plan.")
                # After sub-plan completes, continue to the next step of the current plan
                continue

            result = self._execute_tool(action_json)

            if "Error:" in result or "failed" in result.lower():
                self.log(f"Step failed critically. Error: {result}. Aborting {plan_type}.")
                return "STEP_FAILED"

            if action_json.get("tool_name") in ['save_file', 'delete_file', 'create_folder', 'delete_folder']:
                self.log("File system changed. Refreshing code map for the next step...")
                filename_changed = action_json.get("arguments", {}).get("filename")
                self.emit('file_system_updated', {'filename': filename_changed})
                current_code_map = generate_code_map(self.project_path)

        self.log(f"{plan_type} execution completed successfully.")
        return "COMPLETED"

    def _determine_next_action(self, plan: list, current_step: str, code_map: str, conversation_history: list):
        """Calls the LLM to get the next tool call for a given step."""
        self.emit('agent_thinking')

        execution_prompt = f"""
        You are a helpful AI assistant. Your task is to select the next action to take to progress the plan.

        **Context:**
        1.  **Code Map & History:** Use the **Project Code Map** and **Conversation History** for context.
        2.  **Current Task:** Your goal is to execute the **Current Task** from the plan.
        3.  **Sub-planning:** If the **Current Task** is too complex for a single tool (e.g., deleting multiple files) or if you notice it's already been completed, call the `replan` tool. This will trigger the creation of a "micro-plan" to handle this step.
        4.  **Full Code:** When using `save_file`, always provide the complete, final code. Do not use placeholders.

        **Example `replan` call:**
        ```json
        {{
            "thought": "The current step 'Delete old files' requires multiple `delete_file` calls. I must trigger a sub-plan to handle this.",
            "action": {{
                "tool_name": "replan",
                "arguments": {{
                    "reason": "The step is too complex and requires multiple deletions."
                }}
            }}
        }}
        ```

        **Response Format:**
        Your response MUST be a single JSON object with "thought" and "action" keys.

        **Available Tools:**
        {self.tool_registry.get_tool_definitions()}

        ---
        ## **Conversation History**
        {json.dumps(conversation_history, indent=2)}
        ---
        ## **Project Code Map**
        {code_map}
        ---
        ## **Current Plan**
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
