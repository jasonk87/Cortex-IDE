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
    let socket = null;
    const projectForm = document.getElementById('project-form');
    const projectNameInput = document.getElementById('project-name-input');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatSendBtn = document.getElementById('chat-send-btn');
    const createForm = document.getElementById('create-file-form');
    const newFilenameInput = document.getElementById('new-filename-input');
    const fileTreeList = document.getElementById('file-tree-list');
    const logContent = document.getElementById('log-content');
    const fileViewerHeader = document.getElementById('file-viewer-header');
    const terminalOutput = document.getElementById('terminal-output');
    const saveFileBtn = document.getElementById('save-file-btn');
    const runCodeBtn = document.getElementById('run-code-btn');
    let currentPath = null;
    let isAgentRunning = false;
    let codeRunnerState = 'idle'; // New: Manages the Run/Stop/Clear button state
    
    const codeMirrorEditor = CodeMirror.fromTextArea(editorTextarea, {
        lineNumbers: true, theme: "dracula", indentUnit: 4
    });
    
    const modeMap = { 'py': 'python', 'js': 'javascript', 'css': 'css', 'html': 'xml' };
    let currentStreamElement = null;

    function autoScrollLogIfAtBottom() {
        const threshold = 100; // Pixels from the bottom
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
        logContent.appendChild(entry, logContent.firstChild);
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
        currentFile = null;
        saveFileBtn.style.display = 'none';
        runCodeBtn.style.display = 'none';
    }

    async function executeCode() {
        const code = codeMirrorEditor.getValue();
        if (!code) {
            addLog('Editor is empty. Nothing to run.', false, 'var(--red)');
            return;
        }
        
        // --- 1. Set RUNNING state ---
        codeRunnerState = 'running';
        codeMirrorEditor.getWrapperElement().style.display = 'none';
        terminalOutput.textContent = 'Running...';
        terminalOutput.style.display = 'block';
        runCodeBtn.textContent = 'Stop'; // This is now just a visual cue
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
            // --- 2. Set FINISHED state ---
            codeRunnerState = 'finished';
            runCodeBtn.textContent = 'Clear';
            runCodeBtn.classList.remove('btn-stop');
            runCodeBtn.classList.add('btn-clear');
        }
    }
    
    async function getFileContent(path) {
        // Find the list item that was clicked.
        const liElement = document.querySelector(`#file-tree-list li[data-path="${path}"]`);

        // --- NEW LOGIC BLOCK ---
        // Check if the clicked item is already the active one.
        if (liElement && liElement.classList.contains('active')) {
            // If yes, deselect it and clear the view.
            clearEditorView(); // This function already resets the editor, buttons, and currentPath.
            liElement.classList.remove('active'); // Remove the visual highlight.
            return; // Stop the function here.
        }
        // --- END OF NEW LOGIC ---

        // If we get here, it means we are selecting a new or different file.
        // The original logic continues below.
        clearAndShowEditor();
        showEditor();

        // 1. Clear any previously active elements from the tree.
        document.querySelectorAll('#file-tree-list li.active').forEach(el => el.classList.remove('active'));

        // 2. Set the new active state on the correct list item.
        if (liElement) {
            liElement.classList.add('active');
        }

        try {
            // The backend still expects 'filename' key, so we pass the path to it.
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
        const result = await response.json();      // { message, project_path }
        if (!response.ok) throw new Error(result.error || response.status);
    
        addLog(`Successfully started project: ${projectName}.`);
        await updateFileTree();
    
        return result;                             // ← essential
    }
    
    async function updateFileTree() {
        try {
            const data = await (await fetch('/api/files')).json();
    
            if (data.error) {
                addLog(`Error loading files: ${data.error}`, false, 'var(--red)');
            }
    
            fileTreeList.innerHTML = '';                  // clear old tree
            if (!data || !data.name) {
                fileTreeList.innerHTML =
                    '<li><em>No files yet – start coding!</em></li>';
                return;
            }
            const treeHtml = createTreeHtml([data]);      // build fresh tree
            fileTreeList.appendChild(treeHtml);
    
            const rootLi = fileTreeList.querySelector('li');
            if (rootLi) {
                rootLi.classList.add('expanded');
                const childrenUl = rootLi.querySelector('ul'); // Get the child list
                if (childrenUl) { // Check if the child list actually exists
                    childrenUl.style.display = 'block'; // Only expand if it exists
                }
            }
        } catch (err) {
            addLog(`Error loading files: ${err.message}`, false, 'var(--red)');
            fileTreeList.innerHTML =
                '<li><em>Unable to load file list</em></li>';
        }
    }
    
    /* ---------- 1. openSocket ---------- */
    function openSocket(projectPath) {
        socket = io();                          // same host & port as the page
    
        socket.on('connect', () => {
            console.log('[Socket] connected:', socket.id);
            socket.emit('join_project_room', { project_path: projectPath });
    
            setupSocketListeners();             // attach after join succeeds
        });

        socket.on('file_system_updated', (data) => {
            // Log to the browser console for debugging
            console.log(`File system update received for: ${data.filename}`);
    
            // 1. Always refresh the file tree to show the new state
            updateFileTree();
    
            // 2. Check if the file open in the editor was the one modified
            // The 'currentPath' variable already holds the path of the open file
            if (currentPath && currentPath === data.filename) {
                // To prevent overwriting what the user might be typing,
                // we don't automatically reload the content. Instead, we notify them.
                addLog(`Heads up: The file you are editing (${data.filename}) was just modified by the agent. You may want to save your work and reload the file.`, false, 'var(--orange)');
            }
        });
    
        socket.io.on('error',  err => console.error('[Socket] error',  err));
        socket.io.on('reconnect_error',
                     err => console.error('[Socket] reconnect_error', err));
    }

    // New recursive function to build the HTML for the file tree
    function createTreeHtml(nodes) {
        const ul = document.createElement('ul');
    
        nodes.forEach(node => {
            const li = document.createElement('li');
            // *** store path RELATIVE to the project folder ***
            li.dataset.path = node.path.replace(/^.*?\bworkspaces[\\/][^\\/]+[\\/]/, '');
    
            if (node.type === 'directory') {
                li.classList.add('directory');
    
                const nameDiv = document.createElement('div');
                nameDiv.classList.add('directory-name');
                nameDiv.textContent = node.name;
    
                const delBtn = document.createElement('button');
                delBtn.textContent = '×';
                delBtn.className   = 'delete-folder-btn';
    
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
                a.href        = '#';
    
                const delBtn = document.createElement('button');
                delBtn.textContent = '×';
                delBtn.className   = 'delete-file-btn';
    
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
           addLog(result.message); await updateFileTree(); newFilenameInput.value = '';
       } catch (error) { addLog(`Error creating file: ${error.message}`, true); }
   }

   async function deleteFile(path) {
        try {
            const response = await fetch('/api/delete_file', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ filename: path }) // Pass the full path to the API
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error);

            addLog(result.message, false, 'var(--orange)');
            await updateFileTree();

            // If the deleted file was the one open in the editor, clear the view
            if (currentPath === path) { // Use the renamed variable here
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
            document.getElementById('new-folder-input').value = '';
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
            // Clear editor if the deleted folder contained the open file
            if (currentPath && currentPath.startsWith(path)) {
                clearEditorView();
            }
        } catch (error) {
            addLog(`Error deleting folder: ${error.message}`, false, 'var(--red)');
        }
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
            // Always reset the UI after attempting to stop
            clearAndShowEditor();
            codeRunnerState = 'idle'; // Reset state
        }
    }

    async function saveFileContent() {
        if (!currentPath) return; // Use the renamed variable here
        saveFileBtn.textContent = 'Saving...';
        saveFileBtn.disabled = true;
        try {
            const content = codeMirrorEditor.getValue();
            const response = await fetch('/api/save_file_content', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ filename: currentPath, content: content }) }); // And here
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
        if (isRunning) {
            chatSendBtn.textContent = 'Stop'; // Was 'Stop Task'
            chatSendBtn.classList.add('btn-stop');
            chatForm.classList.add('running');
        } else {
            chatSendBtn.textContent = 'Send'; // Was 'Start Task'
            chatSendBtn.classList.remove('btn-stop');
            chatForm.classList.remove('running');
            chatInput.value = '';
            chatInput.focus();
        }
    }
        // --- NEW: Professional Logging System ---

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
        titleSpan.textContent = title;

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
        
        logContent.appendChild(entry); // Append at the end
        autoScrollLogIfAtBottom();

        return body; // Return the body element to be filled with content
    }
    
    /* ---------- 2. setupSocketListeners ---------- */
    // ---------- setupSocketListeners (full replacement) ----------
    function setupSocketListeners() {
        /* debug — list every raw event in DevTools */
        socket.onAny((event, ...args) =>
            console.log(`[Socket ►] ${event}`, args));

        // ── 1. collapsible Agent Plan ─────────────────────────────
        socket.on('agent_plan_created', (data) => {
            /* remove old plan if present */
            const old = logContent.querySelector('.plan-container');
            if (old) old.remove();

            /* outer wrapper */
            const wrapper = document.createElement('div');
            wrapper.className = 'plan-container log-entry type-plan expanded';

            /* header with caret */
            const header = document.createElement('div');
            header.className = 'log-header collapsible';
            header.innerHTML =
                '<span class="log-caret"></span><span class="log-title">Agent Plan</span>';
            wrapper.appendChild(header);

            /* body for the <ol> list */
            const body = document.createElement('div');
            body.className = 'log-body';
            wrapper.appendChild(body);

            /* ordered list of steps */
            const ol = document.createElement('ol');
            (data.plan || []).forEach((step) => {
                const li = document.createElement('li');
                li.textContent =
                    typeof step === 'object' ? JSON.stringify(step) : step;
                ol.appendChild(li);
            });
            body.appendChild(ol);

            /* toggle collapse */
            header.addEventListener('click', () =>
                wrapper.classList.toggle('expanded')
            );

            logContent.appendChild(wrapper);
            autoScrollLogIfAtBottom();
        });

        // ── 2. “thinking” preamble & stream chunks ────────────────
        socket.on('agent_thinking', () => {
            const body = createLogEntry('Agent thinking…', 'thought', true, true);
            const pre  = document.createElement('pre');
            body.appendChild(pre);
            currentStreamEntry = pre;
        });

        socket.on('agent_stream_chunk', (data) => {
            if (!currentStreamEntry) {
                const body = createLogEntry('Agent Stream', 'thought', true, true);
                const pre  = document.createElement('pre');
                body.appendChild(pre);
                currentStreamEntry = pre;
            }
            currentStreamEntry.textContent += data.chunk;
            autoScrollLogIfAtBottom();
        });

        // ── 3. plain log lines & exec results ─────────────────────
        socket.on('agent_log', (data) =>
            createLogEntry(`${data.message}`, 'info')
        );

        socket.on('agent_exec_result', (data) => {
            const entry = createLogEntry(
                `Exec exit ${data.exit_code}`,
                data.exit_code === 0 ? 'success' : 'error',
                true,
                false
            );
            const pre = document.createElement('pre');
            pre.textContent = (data.stdout || '') + (data.stderr || '');
            entry.appendChild(pre);
        });

        // ── 4. task finished ──────────────────────────────────────
        socket.on('task_finished', () => {
            createLogEntry('Task finished', 'success');
            currentStreamEntry = null;
            setAgentRunningState(false);
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
            document.getElementById('download-project-btn').style.display = 'block'; // <-- ADD THIS LINE
            chatInput.focus();
            openSocket(result.project_path);                  // join room & stream
        } catch (err) {
            addLog(`Error: ${err.message}`, false, 'var(--red)');
        }
    });
    

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (isAgentRunning) {
            socket.emit('stop_agent');
            createLogEntry('Stop signal sent to agent...', 'user');
            return;
        }
    
        const message = chatInput.value.trim();
        if (!message) return;
    
        // Display the user's message immediately in the log
        createLogEntry(message, 'user');
        setAgentRunningState(true);
    
        // Emit 'agent_chat' instead of 'start_task'
        socket.emit('agent_chat', { message: message }, (response) => {
            if (response && response.error) {
                createLogEntry(`Error: ${response.error}`, 'error');
                setAgentRunningState(false);
            }
        });
        chatInput.value = ''; // Clear the input after sending
    });

    createForm.addEventListener('submit', (e) => { e.preventDefault(); const newFilename = newFilenameInput.value.trim(); if (newFilename) { createFile(newFilename); } });
    saveFileBtn.addEventListener('click', saveFileContent);
    runCodeBtn.addEventListener('click', () => {
        if (codeRunnerState === 'idle') {
            executeCode();
        } else if (codeRunnerState === 'finished') {
            clearAndShowEditor();
        }
        // No more 'running' state check here
    });
    document.getElementById('create-folder-form').addEventListener('submit', (e) => {
        e.preventDefault();
        const newFolderName = document.getElementById('new-folder-input').value.trim();
        if (newFolderName) {
            createFolder(newFolderName);
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
            if (confirm(`Are you sure you want to delete file: ${path}?`)) {
                deleteFile(path);
            }
        // --- ADD THIS BLOCK ---
        } else if (target.classList.contains('delete-folder-btn')) {
            if (confirm(`DELETE FOLDER? This will also delete all files and subfolders inside: ${path}`)) {
                deleteFolder(path);
            }
        }
        // --- END OF ADDED BLOCK ---
    });

    downloadProjectBtn.addEventListener('click', () => {
        window.location.href = '/api/download_project';
    });
});