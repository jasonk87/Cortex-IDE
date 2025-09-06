from playwright.sync_api import sync_playwright, expect
import json
import time

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto("http://127.0.0.1:5001")

            # Start a project
            page.get_by_placeholder("Enter new project name...").fill("approval-ui-test-mock")
            page.get_by_role("button", name="Start New Project").click()
            expect(page.locator("#chat-form")).to_be_visible(timeout=10000)

            # Mock the agent_plan_created event to show the buttons
            plan_data = {
                'plan': [
                    "Step 1: This is a mocked plan.",
                    "Step 2: The agent is not actually running.",
                    "Step 3: This is just for UI verification."
                ]
            }

            # Wait for the socket to be available
            page.wait_for_function("() => window.socket")

            # Emit the event
            page.evaluate(f"window.socket.emit('agent_plan_created', {json.dumps(plan_data)})")

            # Wait for the plan container to be visible
            expect(page.locator(".plan-container")).to_be_visible(timeout=5000)

            # Take a screenshot of the plan with the approval buttons
            page.locator("#main-panel").screenshot(path="jules-scratch/verification/04_plan_approval_mock.png")

        except Exception as e:
            print(f"An error occurred: {e}")
            page.screenshot(path="jules-scratch/verification/error.png")
        finally:
            browser.close()

if __name__ == "__main__":
    run_verification()
