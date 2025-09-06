// static/js/script.js (Updated for UX/UI)
io.opts = {
    transports  : ['websocket', 'polling'], // fallback is fine
    timeout     : 20000,   // 20 s handshake timeout
    pingTimeout : 60000,   // 60 s server-silence tolerance
    pingInterval: 25000    // 25 s heartbeat
};

document.addEventListener('DOMContentLoaded', () => {
    const editorTextarea = document.getElementById('editor-textarea');
    const downloadProjectBtn = document.getElementById('download-project-btn');
    window.socket = null; // Expose socket to global scope for testing
    const projectForm = document.getElementById('project-form');
    const projectNameInput = document.getElementById('project-name-input');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatSendBtn = document.getElementById('chat-send-btn');
    const fileTreeList = document.getElementById('file-tree-list');
    const logContent = document.getElementById('log-content');
    const fileViewerHeader = document.getElementById('file-viewer-header');
    const terminalOutput = document.getElementById('terminal-output');
    const saveFileBtn = document.getElementById('save-file-btn');
    const runCodeBtn = document.getElementById('run-code-btn');
    const installDepsBtn = document.getElementById('install-deps-btn');
    const formatCodeBtn = document.getElementById('format-code-btn');

    // New UI elements
    const addFileBtn = document.getElementById('add-file-btn');
    const addFolderBtn = document.getElementById('add-folder-btn');
    const createItemForm = document.getElementById('create-item-form');
    const newItemInput = document.getElementById('new-item-input');

    // Modal and Spinner elements
    const confirmationModal = document.getElementById('confirmation-modal');
    const modalText = document.getElementById('modal-text');
    const modalConfirmBtn = document.getElementById('modal-confirm-btn');
    const modalCancelBtn = document.getElementById('modal-cancel-btn');
    const agentSpinner = document.getElementById('agent-spinner');

    // Tab UI elements
    const sidePanelTabs = document.querySelector('.side-panel-tabs');
    const filesTabBtn = document.getElementById('files-tab-btn');
    const agentTabBtn = document.getElementById('agent-tab-btn');
    const fileTreeContent = document.getElementById('file-tree-content');
    const agentLogsContent = document.getElementById('agent-logs-content');

    let currentPath = null;
    let isAgentRunning = false;
    let codeRunnerState = 'idle';

    const codeMirrorEditor = CodeMirror.fromTextArea(editorTextarea, {
        lineNumbers: true,
        theme: "dracula",
        indentUnit: 4,
        gutters: ["CodeMirror-linenumbers", "CodeMirror-lint-markers"],
        lint: { async: true, getAnnotations: pythonLinter, delay: 750 }
    });

    const modeMap = { 'py': 'python', 'js': 'javascript', 'css': 'css', 'html': 'xml' };
    let currentStreamElement = null;

    function autoScrollLogIfAtBottom() {
        const threshold = 100;
        const isScrolledToBottom = logContent.scrollHeight - logContent.clientHeight <= logContent.scrollTop + threshold;
        if (isScrolledToBottom) {
            logContent.scrollTop = logContent.scrollHeight;
        }
    }

    function addLog(message, isAgentMsg = false, color = null) {
        currentStreamElement = null;
        const entry = document.createElement('div');
        entry.textContent = `> ${message}`;
        if (isAgentMsg) { entry.classList.add('agent-log-msg'); }
        if (color) { entry.style.color = color; }
        logContent.appendChild(entry);
    }

    function addExecutionResult(result, source = "Manual") {
        const headerText = `--- ${source} Execution (Exit Code: ${result.exit_code}) ---`;
        const fullOutput = `${result.stdout || ''}\n${result.stderr || ''}`;

        terminalOutput.textContent = fullOutput;
        addLog(headerText, false, result.exit_code === 0 ? 'var(--green)' : 'var(--red)');
    }

    function showEditor() {
        terminalOutput.style.display = 'none';
        codeMirrorEditor.getWrapperElement().style.display = 'block';
        codeMirrorEditor.refresh();
    }

    function clearAndShowEditor() {
        showEditor();
        runCodeBtn.textContent = 'Run';
        runCodeBtn.classList.remove('btn-clear', 'btn-stop');
        saveFileBtn.style.display = 'inline-block';
        codeRunnerState = 'idle';
    }

    function clearEditorView() {
        fileViewerHeader.textContent = 'File Viewer';
        codeMirrorEditor.setValue('');
        currentPath = null;
        saveFileBtn.style.display = 'none';
        runCodeBtn.style.display = 'none';
    }

    async function executeCode() {
        const code = codeMirrorEditor.getValue();
        if (!code) {
            addLog('Editor is empty. Nothing to run.', false, 'var(--red)');
            return;
        }

        codeRunnerState = 'running';
        codeMirrorEditor.getWrapperElement().style.display = 'none';
        terminalOutput.textContent = 'Running...';
        terminalOutput.style.display = 'block';
        runCodeBtn.textContent = 'Stop';
        runCodeBtn.classList.add('btn-stop');
        saveFileBtn.style.display = 'none';

        try {
            const response = await fetch('/api/execute_code', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ code: code, language: 'python' })
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || `HTTP Error ${response.status}`);
            addExecutionResult(result, "Manual");
        } catch (error) {
            addLog(`Error during execution: ${error.message}`, false, 'var(--red)');
            terminalOutput.textContent = `Error during execution:\n${error.message}`;
        } finally {
            codeRunnerState = 'finished';
            runCodeBtn.textContent = 'Clear';
            runCodeBtn.classList.remove('btn-stop');
            runCodeBtn.classList.add('btn-clear');
        }
    }

    async function getFileContent(path) {
        const liElement = document.querySelector(`#file-tree-list li[data-path="${path}"]`);

        if (liElement && liElement.classList.contains('active')) {
            clearEditorView();
            liElement.classList.remove('active');
            return;
        }

        clearAndShowEditor();
        showEditor();

        document.querySelectorAll('#file-tree-list li.active').forEach(el => el.classList.remove('active'));
        if (liElement) {
            liElement.classList.add('active');
        }

        try {
            const response = await fetch('/api/get_file_content', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ filename: path }) });
            if (!response.ok) { const errData = await response.json(); throw new Error(errData.error || `HTTP error! status: ${response.status}`); }
            const data = await response.json();

            fileViewerHeader.textContent = data.filename;
            codeMirrorEditor.setValue(data.content);
            currentPath = path;

            const extension = data.filename.split('.').pop();
            const mode = modeMap[extension] || 'python';
            codeMirrorEditor.setOption("mode", mode);

            saveFileBtn.style.display = 'inline-block';
            runCodeBtn.style.display = (mode === 'python') ? 'inline-block' : 'none';

        } catch (error) {
            addLog(`Error opening file: ${error.message}`, false, 'var(--red)');
            currentPath = null;
            saveFileBtn.style.display = 'none';
            runCodeBtn.style.display = 'none';
        }
    }

    async function startProject(projectName) {
        const response = await fetch('/api/start_project', {
            method : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({ name: projectName })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || response.status);

        addLog(`Successfully started project: ${projectName}.`);
        await updateFileTree();

        return result;
    }

    async function updateFileTree() {
        try {
            const data = await (await fetch('/api/files')).json();

            if (data.error) {
                addLog(`Error loading files: ${data.error}`, false, 'var(--red)');
            }

            fileTreeList.innerHTML = '';
            if (!data || !data.name) {
                fileTreeList.innerHTML = '<li><em>No files yet – start coding!</em></li>';
                return;
            }
            const treeHtml = createTreeHtml([data]);
            fileTreeList.appendChild(treeHtml);

            const rootLi = fileTreeList.querySelector('li');
            if (rootLi) {
                rootLi.classList.add('expanded');
                const childrenUl = rootLi.querySelector('ul');
                if (childrenUl) {
                    childrenUl.style.display = 'block';
                }
            }
        } catch (err) {
            addLog(`Error loading files: ${err.message}`, false, 'var(--red)');
            fileTreeList.innerHTML = '<li><em>Unable to load file list</em></li>';
        }
    }

    function openSocket(projectPath) {
        window.socket = io();

        window.socket.on('connect', () => {
            console.log('[Socket] connected:', window.socket.id);
            window.socket.emit('join_project_room', { project_path: projectPath });

            setupSocketListeners();
        });

        window.socket.on('file_system_updated', (data) => {
            console.log(`File system update received for: ${data.filename}`);
            updateFileTree();
            if (currentPath && currentPath === data.filename) {
                addLog(`Heads up: The file you are editing (${data.filename}) was just modified by the agent. You may want to save your work and reload the file.`, false, 'var(--orange)');
            }
        });

        window.socket.io.on('error',  err => console.error('[Socket] error',  err));
        window.socket.io.on('reconnect_error', err => console.error('[Socket] reconnect_error', err));
    }

    function createTreeHtml(nodes) {
        const ul = document.createElement('ul');

        nodes.forEach(node => {
            const li = document.createElement('li');
            li.dataset.path = node.path.replace(/^.*?\bworkspaces[\\/][^\\/]+[\\/]/, '');

            if (node.type === 'directory') {
                li.classList.add('directory');
                const nameDiv = document.createElement('div');
                nameDiv.classList.add('directory-name');
                nameDiv.textContent = node.name;
                const delBtn = document.createElement('button');
                delBtn.textContent = '×';
                delBtn.className = 'delete-folder-btn';
                li.append(nameDiv, delBtn);
                if (node.children && node.children.length) {
                    const childrenUl = createTreeHtml(node.children);
                    childrenUl.style.display = 'none';
                    li.appendChild(childrenUl);
                }
            } else {
                li.classList.add('file');
                const a = document.createElement('a');
                a.textContent = node.name;
                a.href = '#';
                const delBtn = document.createElement('button');
                delBtn.textContent = '×';
                delBtn.className = 'delete-file-btn';
                li.append(a, delBtn);
            }
            ul.appendChild(li);
        });
        return ul;
    }

   async function createFile(filename) {
       try {
           const response = await fetch('/api/create_file', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ filename: filename }) });
           const result = await response.json();
           if (!response.ok) throw new Error(result.error);
           addLog(result.message);
           await updateFileTree();
       } catch (error) { addLog(`Error creating file: ${error.message}`, true); }
   }

   async function deleteFile(path) {
        try {
            const response = await fetch('/api/delete_file', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ filename: path })
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error);
            addLog(result.message, false, 'var(--orange)');
            await updateFileTree();
            if (currentPath === path) {
                clearEditorView();
            }
        } catch (error) {
            addLog(`Error deleting file: ${error.message}`, false, 'var(--red)');
        }
    }

    async function createFolder(path) {
        try {
            const response = await fetch('/api/create_folder', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ path: path })
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error);
            addLog(result.message);
            await updateFileTree();
        } catch (error) {
            addLog(`Error creating folder: ${error.message}`, false, 'var(--red)');
        }
    }

    async function deleteFolder(path) {
        try {
            const response = await fetch('/api/delete_folder', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ path: path })
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error);
            addLog(result.message, false, 'var(--orange)');
            await updateFileTree();
            if (currentPath && currentPath.startsWith(path)) {
                clearEditorView();
            }
        } catch (error) {
            addLog(`Error deleting folder: ${error.message}`, false, 'var(--red)');
        }
    }

    function showDeleteConfirmationModal(path, type) {
        const itemType = type === 'file' ? 'file' : 'folder';
        const message = `Are you sure you want to delete the ${itemType}: ${path}?`;
        modalText.textContent = message;

        // Clone and replace the button to remove old event listeners
        const newConfirmBtn = modalConfirmBtn.cloneNode(true);
        modalConfirmBtn.parentNode.replaceChild(newConfirmBtn, modalConfirmBtn);

        // Update reference to the new button
        const modalConfirmBtnRef = document.getElementById('modal-confirm-btn');

        const confirmHandler = () => {
            if (type === 'file') {
                deleteFile(path);
            } else {
                deleteFolder(path);
            }
            confirmationModal.style.display = 'none';
        };

        modalConfirmBtnRef.addEventListener('click', confirmHandler, { once: true });

        const cancelHandler = () => {
            confirmationModal.style.display = 'none';
            // Clean up the confirm handler to be safe
            modalConfirmBtnRef.removeEventListener('click', confirmHandler);
        };

        modalCancelBtn.addEventListener('click', cancelHandler, { once: true });

        confirmationModal.style.display = 'flex';
    }

    async function stopCode() {
        try {
            const response = await fetch('/api/stop_code', { method: 'POST' });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Failed to stop process.');
            addLog(result.message, false, 'var(--orange)');
        } catch (error) {
            addLog(`Error stopping process: ${error.message}`, false, 'var(--red)');
        } finally {
            clearAndShowEditor();
            codeRunnerState = 'idle';
        }
    }

    async function saveFileContent() {
        if (!currentPath) return;
        saveFileBtn.textContent = 'Saving...';
        saveFileBtn.disabled = true;
        try {
            const content = codeMirrorEditor.getValue();
            const response = await fetch('/api/save_file_content', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ filename: currentPath, content: content }) });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error);
            addLog(result.message);
            saveFileBtn.textContent = 'Saved!';
            setTimeout(() => { saveFileBtn.textContent = 'Save'; }, 2000);
        } catch (error) {
            addLog(`Error saving file: ${error.message}`, true);
            saveFileBtn.textContent = 'Save';
        } finally {
            saveFileBtn.disabled = false;
        }
    }

    function setAgentRunningState(isRunning) {
        isAgentRunning = isRunning;
        chatInput.disabled = isRunning;
        agentSpinner.style.display = isRunning ? 'block' : 'none'; // Control spinner

        if (isRunning) {
            chatSendBtn.textContent = 'Stop';
            chatSendBtn.classList.add('btn-stop');
            chatForm.classList.add('running');
        } else {
            chatSendBtn.textContent = 'Send';
            chatSendBtn.classList.remove('btn-stop');
            chatForm.classList.remove('running');
            chatInput.value = '';
            chatInput.focus();
        }
    }

    let currentStreamEntry = null;

    function createLogEntry(title, type = 'info', isCollapsible = false, isCollapsed = true) {
        const entry = document.createElement('div');
        entry.className = `log-entry type-${type}`;
        const header = document.createElement('div');
        header.className = 'log-header';
        const caret = document.createElement('span');
        caret.className = 'log-caret';
        if (isCollapsible) {
            header.classList.add('collapsible');
            if (!isCollapsed) {
                entry.classList.add('expanded');
            }
        }
        const titleSpan = document.createElement('span');
        titleSpan.className = 'log-title';
        if (type === 'user') {
            titleSpan.textContent = `You: ${title}`;
        } else {
            titleSpan.textContent = title;
        }
        header.appendChild(caret);
        header.appendChild(titleSpan);
        entry.appendChild(header);
        const body = document.createElement('div');
        body.className = 'log-body';
        entry.appendChild(body);
        if (isCollapsible) {
            header.addEventListener('click', () => {
                entry.classList.toggle('expanded');
            });
        }
        logContent.appendChild(entry);
        autoScrollLogIfAtBottom();
        return body;
    }

    function setupSocketListeners() {
        window.socket.onAny((event, ...args) => console.log(`[Socket ►] ${event}`, args));

        window.socket.on('agent_plan_created', (data) => {
            const old = logContent.querySelector('.plan-container');
            if (old) old.remove();
            const wrapper = document.createElement('div');
            wrapper.className = 'plan-container log-entry type-plan expanded';
            const header = document.createElement('div');
            header.className = 'log-header collapsible';
            header.innerHTML = '<span class="log-caret"></span><span class="log-title">Agent Plan</span>';
            wrapper.appendChild(header);
            const body = document.createElement('div');
            body.className = 'log-body';
            wrapper.appendChild(body);
            const ol = document.createElement('ol');
            (data.plan || []).forEach((step) => {
                const li = document.createElement('li');
                li.textContent = typeof step === 'object' ? JSON.stringify(step) : step;
                ol.appendChild(li);
            });
            body.appendChild(ol);
            header.addEventListener('click', () => wrapper.classList.toggle('expanded'));
            logContent.appendChild(wrapper);
            autoScrollLogIfAtBottom();
        });

        window.socket.on('agent_thinking', () => {
            const body = createLogEntry('Agent thinking…', 'thought', true, true);
            const pre  = document.createElement('pre');
            body.appendChild(pre);
            currentStreamEntry = pre;
        });

        window.socket.on('agent_stream_chunk', (data) => {
            if (!currentStreamEntry) {
                const body = createLogEntry('Agent Stream', 'thought', true, true);
                const pre  = document.createElement('pre');
                body.appendChild(pre);
                currentStreamEntry = pre;
            }
            currentStreamEntry.textContent += data.chunk;
            autoScrollLogIfAtBottom();
        });

        window.socket.on('agent_log', (data) => createLogEntry(`${data.message}`, 'info'));

        window.socket.on('agent_exec_result', (data) => {
            const entry = createLogEntry(`Exec exit ${data.exit_code}`, data.exit_code === 0 ? 'success' : 'error', true, false);
            const pre = document.createElement('pre');
            pre.textContent = (data.stdout || '') + (data.stderr || '');
            entry.appendChild(pre);
        });

        window.socket.on('task_finished', () => {
            createLogEntry('Task finished', 'success');
            currentStreamEntry = null;
            setAgentRunningState(false);
        });

        window.socket.on('packages_installed', (data) => {
            const body = createLogEntry('Packages installed via background process.', 'success', true, false);
            const pre = document.createElement('pre');
            pre.textContent = (data.stdout || '') + '\n' + (data.stderr || '');
            body.appendChild(pre);
        });

        window.socket.on('installation_failed', (data) => {
            const body = createLogEntry(`Package installation failed via background process: ${data.message}`, 'error', true, false);
            if (data.stdout || data.stderr || data.exit_code !== undefined) {
                const pre = document.createElement('pre');
                let content = '';
                if (data.exit_code !== undefined) content += `Exit Code: ${data.exit_code}\n`;
                if (data.stdout) content += `Stdout: ${data.stdout}\n`;
                if (data.stderr) content += `Stderr: ${data.stderr}`;
                pre.textContent = content.trim();
                body.appendChild(pre);
            }
        });

        window.socket.on('debug_message', (data) => {
            console.log('[Socket DEBUG]', data.message, data.stdout || '', data.stderr || '');
        });
    }

    projectForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const projectName = projectNameInput.value.trim();
        if (!projectName) return;
        addLog(`Starting project: ${projectName}.`);
        try {
            const result = await startProject(projectName);
            projectForm.style.display = 'none';
            chatForm.style.display   = 'flex';
            document.getElementById('download-project-btn').style.display = 'block';
            chatInput.focus();
            openSocket(result.project_path);
        } catch (err) {
            addLog(`Error: ${err.message}`, false, 'var(--red)');
        }
    });

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (isAgentRunning) {
            window.socket.emit('stop_agent');
            createLogEntry('Stop signal sent to agent...', 'user');
            return;
        }
        const message = chatInput.value.trim();
        if (!message) return;
        createLogEntry(message, 'user');
        setAgentRunningState(true);
        window.socket.emit('agent_chat', { message: message }, (response) => {
            if (response && response.error) {
                createLogEntry(`Error: ${response.error}`, 'error');
                setAgentRunningState(false);
            }
        });
        chatInput.value = '';
    });

    function showCreateInput(type) {
        createItemForm.style.display = 'block';
        createItemForm.dataset.type = type; // 'file' or 'folder'
        newItemInput.placeholder = `Enter new ${type} name...`;
        newItemInput.focus();
    }

    addFileBtn.addEventListener('click', () => showCreateInput('file'));
    addFolderBtn.addEventListener('click', () => showCreateInput('folder'));

    createItemForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const itemName = newItemInput.value.trim();
        const itemType = createItemForm.dataset.type;

        if (itemName) {
            if (itemType === 'file') {
                createFile(itemName);
            } else if (itemType === 'folder') {
                createFolder(itemName);
            }
        }
        newItemInput.value = '';
        createItemForm.style.display = 'none';
    });

    newItemInput.addEventListener('blur', () => {
        // Hide the form if the input loses focus and is empty
        if (newItemInput.value.trim() === '') {
            createItemForm.style.display = 'none';
        }
    });

    saveFileBtn.addEventListener('click', saveFileContent);

    runCodeBtn.addEventListener('click', () => {
        if (codeRunnerState === 'idle') {
            executeCode();
        } else if (codeRunnerState === 'finished') {
            clearAndShowEditor();
        }
    });

    fileTreeList.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const target = e.target;
        const li = target.closest('li');
        if (!li) return;
        const path = li.dataset.path;

        if (target.classList.contains('directory-name')) {
            li.classList.toggle('expanded');
            const childrenUl = li.querySelector('ul');
            if (childrenUl) {
                childrenUl.style.display = childrenUl.style.display === 'none' ? 'block' : 'none';
            }
        } else if (target.tagName === 'A') {
            getFileContent(path);
        } else if (target.classList.contains('delete-file-btn')) {
            showDeleteConfirmationModal(path, 'file');
        } else if (target.classList.contains('delete-folder-btn')) {
            showDeleteConfirmationModal(path, 'folder');
        }
    });

    downloadProjectBtn.addEventListener('click', () => {
        window.location.href = '/api/download_project';
    });

    installDepsBtn.addEventListener('click', installDependencies);
    formatCodeBtn.addEventListener('click', formatCode);

    sidePanelTabs.addEventListener('click', (e) => {
        const clickedTab = e.target.closest('.tab-btn');
        if (!clickedTab) return;

        // Deactivate all tabs and content
        filesTabBtn.classList.remove('active');
        agentTabBtn.classList.remove('active');
        fileTreeContent.classList.remove('active');
        agentLogsContent.classList.remove('active');

        // Activate the clicked tab and its content
        if (clickedTab.id === 'files-tab-btn') {
            filesTabBtn.classList.add('active');
            fileTreeContent.classList.add('active');
        } else if (clickedTab.id === 'agent-tab-btn') {
            agentTabBtn.classList.add('active');
            agentLogsContent.classList.add('active');
        }
    });
});