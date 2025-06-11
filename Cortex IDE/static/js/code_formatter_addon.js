// Cortex IDE/static/js/code_formatter_addon.js

async function formatCode() {
    // Assume codeMirrorEditor, createLogEntry, and formatCodeBtn are globally available
    // or would be passed if this was further modularized.
    if (typeof codeMirrorEditor === 'undefined' || codeMirrorEditor.getOption("mode") !== "python") {
        if (typeof createLogEntry === 'function') {
            createLogEntry("Formatting is only available for Python files.", "warning");
        } else {
            console.warn("Formatting is only available for Python files. (createLogEntry not found)");
        }
        return;
    }

    const code = codeMirrorEditor.getValue();
    if (!code.trim()) {
        if (typeof createLogEntry === 'function') {
            createLogEntry("No code to format.", "info");
        }
        return;
    }

    if (typeof formatCodeBtn === 'undefined') {
        console.error("formatCodeBtn is not defined.");
        return;
    }

    formatCodeBtn.textContent = 'Formatting...';
    formatCodeBtn.disabled = true;

    try {
        const response = await fetch('/api/format_code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: code })
        });

        const result = await response.json();

        if (result.success) {
            codeMirrorEditor.setValue(result.formatted_code);
            if (typeof createLogEntry === 'function') {
                createLogEntry("Code formatted successfully with Black.", "success");
            }
        } else {
            let errorMessage = "Failed to format code.";
            if (result.error) {
                errorMessage += ` Error: ${result.error}`;
            }
            if (result.details) {
                 errorMessage += ` Details: ${result.details}`;
            }
            if (typeof createLogEntry === 'function') {
                const errorBody = createLogEntry(errorMessage, "error", true, false); // Expand error messages
                // Ensure parent is expanded - createLogEntry might need to handle this or be called on an existing expanded entry
                if (errorBody && errorBody.parentNode && errorBody.parentNode.classList.contains('log-entry')) {
                     errorBody.parentNode.classList.add('expanded');
                }
            } else {
                console.error(errorMessage);
            }
        }
    } catch (error) {
        console.error('Error calling format_code API:', error);
        if (typeof createLogEntry === 'function') {
            createLogEntry(`Error during formatting request: ${error.message}`, "error");
        }
    } finally {
        formatCodeBtn.textContent = 'Format';
        formatCodeBtn.disabled = false;
    }
}
