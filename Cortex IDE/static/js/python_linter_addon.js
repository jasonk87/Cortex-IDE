// Cortex IDE/static/js/python_linter_addon.js

async function pythonLinter(text, callback, options, cm) {
    // 'cm' (CodeMirror instance) is passed by the lint addon.
    // 'callback' is the modern way for async linters in CM5.
    // It expects (foundAnnotations) or (cmInstance, foundAnnotations).
    // For CodeMirror 5, it's typically callback(cm, annotations) or callback(annotations)
    // We will use callback(annotations) as it's simpler if cm is not strictly needed by the callback itself.

    if (!text.trim()) {
        if (typeof callback === 'function') callback([]);
        return;
    }

    // Only lint if the current mode is Python
    // Access CodeMirror constructor and Pos from the global CodeMirror object
    if (typeof CodeMirror === 'undefined' || !cm || cm.getOption("mode") !== "python") {
        if (typeof callback === 'function') callback([]);
        return;
    }

    try {
        const response = await fetch('/api/lint_code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: text })
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({ error: "Unknown linting API error" }));
            console.error('Linting API error:', errData.error || response.status);
            if (typeof callback === 'function') callback([]);
            return;
        }

        const result = await response.json();
        if (result.success && result.issues) {
            const found = result.issues.map(issue => {
                let severity = 'warning';
                if (issue.code && (issue.code.startsWith('F') || issue.code.startsWith('E'))) {
                    severity = 'error';
                }
                // Flake8: 1-based lines/cols. CodeMirror: 0-based lines/cols.
                const line = Math.max(0, issue.line - 1);
                const col = Math.max(0, issue.col - 1);

                // Determine the end column for the annotation
                const lineText = cm.getLine(line) || "";
                let endCol = col + 1; // Default to one character highlight for simplicity

                // A more sophisticated approach might try to find the end of the token
                // For now, a single character or fixed length highlight is often sufficient for markers
                // Example: highlight the character/token at the issue column
                if (lineText.length > col) {
                    const charAfter = lineText.substring(col);
                    const match = charAfter.match(/^([a-zA-Z0-9_]+|\S)/); // Match word or single non-space char
                    if (match && match[0]) {
                        endCol = col + match[0].length;
                    }
                }


                return {
                    from: CodeMirror.Pos(line, col),
                    to: CodeMirror.Pos(line, endCol),
                    message: `[${issue.code}] ${issue.message}`,
                    severity: severity
                };
            });
            if (typeof callback === 'function') callback(found);
        } else {
            console.error('Linting data error from API:', result.error);
            if (typeof callback === 'function') callback([]);
        }
    } catch (error) {
        console.error('Error fetching linting results:', error);
        if (typeof callback === 'function') callback([]);
    }
}

// Make sure CodeMirror is available when this script runs.
// This function will be attached to CodeMirror options in script.js
if (typeof CodeMirror !== 'undefined') {
    // Optionally, register it if CodeMirror has a global registry for linters,
    // but typically it's passed directly in options.
    // CodeMirror.registerHelper("lint", "python", pythonLinter); // This is one way if using mode-based linters
}
