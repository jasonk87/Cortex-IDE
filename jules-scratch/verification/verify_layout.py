import re
from playwright.sync_api import sync_playwright, Page, expect

def verify_layout(page: Page):
    """
    This script verifies the new two-column layout and tab functionality.
    """
    # 1. Navigate to the app
    page.goto("http://127.0.0.1:5001")

    # 2. Create a new project to get to the main IDE view
    project_name_input = page.get_by_placeholder("Enter new project name...")
    expect(project_name_input).to_be_visible()
    project_name_input.fill("test-layout-project")
    page.get_by_role("button", name="Start New Project").click()

    # 3. Verify that the main app container is visible
    app_container = page.locator("#app-container")
    expect(app_container).to_be_visible()

    # 4. Find and click the 'Agent' tab
    agent_tab = page.get_by_role("button", name="Agent")
    expect(agent_tab).to_be_visible()
    agent_tab.click()

    # 5. Verify the agent log panel is now visible
    agent_log_panel = page.locator("#agent-logs-content")
    expect(agent_log_panel).to_be_visible()

    # 6. Take the final screenshot for verification
    page.screenshot(path="jules-scratch/verification/layout_verification.png")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Create a new context to ensure no caching
        context = browser.new_context()
        page = context.new_page()
        verify_layout(page)
        browser.close()

if __name__ == "__main__":
    main()
