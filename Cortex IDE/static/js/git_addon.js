document.addEventListener('DOMContentLoaded', () => {
    const gitInitBtn = document.getElementById('git-init-btn');
    const gitStatusBtn = document.getElementById('git-status-btn');
    const gitAddAllBtn = document.getElementById('git-add-all-btn');
    const gitCommitForm = document.getElementById('git-commit-form');
    const commitMessageInput = document.getElementById('commit-message-input');
    const gitOutput = document.getElementById('git-output');

    async function handleGitCommand(url, options = {}) {
        try {
            const response = await fetch(url, options);
            const result = await response.json();

            let outputText = '';
            if (result.stdout) {
                outputText += `STDOUT:\n${result.stdout}\n\n`;
            }
            if (result.stderr) {
                outputText += `STDERR:\n${result.stderr}\n\n`;
            }
            if (result.message) {
                outputText += `MESSAGE: ${result.message}\n\n`;
            }
            if (result.error) {
                outputText += `ERROR: ${result.error}\n\n`;
            }

            gitOutput.textContent = outputText;

        } catch (error) {
            gitOutput.textContent = `An unexpected error occurred: ${error.toString()}`;
        }
    }

    gitInitBtn.addEventListener('click', () => {
        handleGitCommand('/api/git/init', { method: 'POST' });
    });

    gitStatusBtn.addEventListener('click', () => {
        handleGitCommand('/api/git/status', { method: 'GET' });
    });

    gitAddAllBtn.addEventListener('click', () => {
        handleGitCommand('/api/git/add_all', { method: 'POST' });
    });

    gitCommitForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const message = commitMessageInput.value.trim();
        if (message) {
            handleGitCommand('/api/git/commit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message })
            });
            commitMessageInput.value = '';
        }
    });
});
