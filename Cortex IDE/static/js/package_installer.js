// Cortex IDE/static/js/package_installer.js

async function installDependencies() {
    // Assume 'socket' and 'createLogEntry' are available in the global scope
    // or are passed as parameters if this were modularized further.
    // For this approach, we rely on them being globally accessible from script.js
    if (typeof socket === 'undefined' || !socket || !socket.connected) {
        if (typeof createLogEntry === 'function') {
            createLogEntry('Error: Not connected to a project. Please start or join a project first.', 'error');
        } else {
            console.error('Error: Not connected to a project. Socket or createLogEntry not available.');
            alert('Error: Not connected to a project. Please start or join a project first.');
        }
        return;
    }

    if (typeof createLogEntry !== 'function') {
        console.error('createLogEntry function is not available.');
        alert('Logging function not available. Cannot proceed.');
        return;
    }

    const initialLogBody = createLogEntry('Attempting to install dependencies from requirements.txt...', 'info', true, false);
    // Ensure the log entry is expanded
    if (initialLogBody && initialLogBody.parentNode && initialLogBody.parentNode.classList.contains('log-entry')) {
        initialLogBody.parentNode.classList.add('expanded');
    }

    try {
        const response = await fetch('/api/install_packages', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
            // No body needed, backend uses project_path from session
        });

        const result = await response.json();

        if (response.ok && result.success) {
            const successBody = createLogEntry('Dependencies installed successfully.', 'success', true, false);
            const pre = document.createElement('pre');
            pre.textContent = `Stdout:
${result.stdout || '(empty)'}

Stderr:
${result.stderr || '(empty)'}`;
            successBody.appendChild(pre);
            if (successBody.parentNode && successBody.parentNode.classList.contains('log-entry')) {
                successBody.parentNode.classList.add('expanded');
            }
        } else { // Handles both !response.ok or result.success === false
            const errorMsg = result.error || (result.message || 'Failed to install packages.');
            const errorBody = createLogEntry(`Installation Error: ${errorMsg}`, 'error', true, false);
            const pre = document.createElement('pre');
            let details = '';
            if (result.exit_code !== undefined) details += `Exit Code: ${result.exit_code}

`;
            details += `Stdout:
${result.stdout || '(empty)'}

Stderr:
${result.stderr || '(empty)'}`;
            pre.textContent = details.trim();
            errorBody.appendChild(pre);
            if (errorBody.parentNode && errorBody.parentNode.classList.contains('log-entry')) {
                errorBody.parentNode.classList.add('expanded');
            }
        }
    } catch (error) {
        console.error('Fetch error during installDependencies:', error);
        const errorBody = createLogEntry(`An error occurred while requesting package installation: ${error.message}`, 'error', true, false);
        if (errorBody.parentNode && errorBody.parentNode.classList.contains('log-entry')) {
           errorBody.parentNode.classList.add('expanded');
        }
    }
}
