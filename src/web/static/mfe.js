class SquadAgentMFE extends HTMLElement {
    constructor() {
        super();
        this.baseUrl = '';
        this.statusData = { healthy: false, status: 'Offline', version: 'N/A', timestamp: 0 };
        this.activeMode = { mode: '4', name: 'Direct-Action', description: '' };
        this.commands = [];
        this.eventSource = null;
        this.chatEventSource = null;

        // Session & Delivery Tracking State
        this.activeSessionId = localStorage.getItem('squad_agent_active_session') || 'squad_sync_session';
        this.sessions = JSON.parse(localStorage.getItem('squad_agent_session_list') || '["squad_sync_session", "feature_dev_1", "qa_audit_1"]');
        if (!this.sessions.includes(this.activeSessionId)) {
            this.sessions.unshift(this.activeSessionId);
        }
        this.isProcessing = false;
    }

    async connectedCallback() {
        this.baseUrl = this.getAttribute('base-url') || window.location.origin;
        if (this.baseUrl.endsWith('/')) {
            this.baseUrl = this.baseUrl.slice(0, -1);
        }

        this.renderSkeleton();
        await this.loadAll();
        this.setupEventListeners();

        // Start streaming collaborative chat for active session
        this.renderSessionList();
        await this.loadChatHistory(this.activeSessionId);
        this.startChatStream(this.activeSessionId);
    }

    disconnectedCallback() {
        if (this.eventSource) {
            this.eventSource.close();
        }
        if (this.chatEventSource) {
            this.chatEventSource.close();
        }
    }

    async loadAll() {
        await Promise.all([
            this.loadStatus(),
            this.loadActiveMode(),
            this.loadCommands()
        ]);
        this.updateUI();
    }

    async loadStatus() {
        try {
            const resp = await fetch(`${this.baseUrl}/api/v1/status`);
            if (resp.ok) {
                this.statusData = await resp.json();
            } else {
                this.statusData.healthy = false;
                this.statusData.status = 'Degraded';
            }
        } catch (e) {
            this.statusData.healthy = false;
            this.statusData.status = 'Offline';
        }
    }

    async loadActiveMode() {
        try {
            const resp = await fetch(`${this.baseUrl}/api/v1/squad/active-mode`);
            if (resp.ok) {
                const data = await resp.json();
                if (data.success) {
                    this.activeMode = {
                        mode: data.mode,
                        name: data.name,
                        description: data.description
                    };
                }
            }
        } catch (e) {
            console.error('Failed to load active mode:', e);
        }
    }

    async loadCommands() {
        try {
            const resp = await fetch(`${this.baseUrl}/api/v1/squad/commands`);
            if (resp.ok) {
                const data = await resp.json();
                if (data.success) {
                    this.commands = data.commands;
                }
            }
        } catch (e) {
            console.error('Failed to load commands:', e);
        }
    }

    renderSkeleton() {
        this.innerHTML = `
            <style>
                .squad-container {
                    font-family: var(--font-sans, 'Outfit', 'Inter', system-ui, sans-serif);
                    color: var(--color-text-primary, #eaeaea);
                    width: 100%;
                    max-width: var(--content-max-width, 1400px);
                    margin: 0 auto;
                    padding: clamp(1.25rem, 2.5vh, 2.25rem) clamp(1.25rem, 3vw, 2.5rem) 3.5rem;
                    box-sizing: border-box;
                }
                .squad-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 24px;
                    border-bottom: 1px solid var(--color-border-subtle, #333);
                    padding-bottom: 16px;
                }
                .squad-title h1 {
                    font-size: var(--font-size-2xl, 1.8rem);
                    font-weight: 700;
                    margin: 0 0 4px 0;
                    background: linear-gradient(135deg, #FF416C 0%, #FF4B2B 100%);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }
                .squad-title p {
                    color: var(--color-text-muted, #888);
                    margin: 0;
                    font-size: var(--font-size-sm, 0.9rem);
                }
                
                .squad-status-badge {
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                    padding: 6px 12px;
                    border-radius: 20px;
                    font-weight: 600;
                    font-size: var(--font-size-xs, 0.8rem);
                    background-color: var(--color-bg-secondary, #222);
                    border: 1px solid var(--color-border-subtle, #333);
                }
                .squad-dot {
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                }
                .squad-dot.healthy {
                    background-color: var(--color-accent-success, #4CAF50);
                    box-shadow: 0 0 8px var(--color-accent-success, #4CAF50);
                }
                .squad-dot.offline {
                    background-color: var(--color-accent-danger, #F44336);
                    box-shadow: 0 0 8px var(--color-accent-danger, #F44336);
                }

                /* GitHub Token Alert Banner */
                .squad-github-banner {
                    display: none;
                    align-items: flex-start;
                    gap: 16px;
                    padding: 16px 20px;
                    margin-bottom: 24px;
                    background: linear-gradient(135deg, rgba(255, 75, 43, 0.12) 0%, rgba(244, 67, 54, 0.08) 100%);
                    border: 1px solid rgba(255, 75, 43, 0.4);
                    border-left: 5px solid #FF4B2B;
                    border-radius: 8px;
                    box-shadow: 0 4px 15px rgba(255, 75, 43, 0.1);
                }
                .squad-github-banner__icon {
                    color: #FF4B2B;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    flex-shrink: 0;
                    margin-top: 2px;
                }
                .squad-github-banner__content {
                    flex: 1;
                }
                .squad-github-banner__title {
                    font-size: var(--font-size-sm, 0.95rem);
                    font-weight: 700;
                    color: #ff6b4a;
                    margin-bottom: 4px;
                }
                .squad-github-banner__desc {
                    font-size: var(--font-size-xs, 0.85rem);
                    color: #ccc;
                    line-height: 1.5;
                }
                .squad-github-banner__desc code {
                    background: rgba(255, 255, 255, 0.1);
                    color: #ff9e80;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-family: var(--font-mono, monospace);
                    font-size: 0.8rem;
                }

                /* Tab Styles */
                .squad-tabs {
                    display: flex;
                    gap: 8px;
                    margin-bottom: 24px;
                }
                .squad-tab-btn {
                    background: transparent;
                    border: 1px solid transparent;
                    color: var(--color-text-muted, #888);
                    font-size: var(--font-size-sm, 0.95rem);
                    font-weight: 600;
                    padding: 8px 20px;
                    cursor: pointer;
                    border-radius: 6px;
                    transition: all 0.2s ease;
                }
                .squad-tab-btn:hover {
                    color: #fff;
                    background-color: var(--color-bg-secondary, #222);
                }
                .squad-tab-btn.active {
                    color: #fff;
                    background: linear-gradient(135deg, rgba(255, 65, 108, 0.15) 0%, rgba(255, 75, 43, 0.15) 100%);
                    border-color: var(--color-accent-primary, #ff4b2b);
                }

                .tab-content {
                    display: none;
                }
                .tab-content.active {
                    display: block;
                }

                /* Grid Layouts */
                .squad-grid {
                    display: grid;
                    grid-template-columns: 1fr;
                    gap: 24px;
                    margin-bottom: 24px;
                }
                @media(min-width: 768px) {
                    .squad-grid {
                        grid-template-columns: 1fr 2fr;
                    }
                }

                .squad-card {
                    background: var(--color-bg-surface, #1e1e1e);
                    border: 1px solid var(--color-border-subtle, #2d2d2d);
                    border-radius: 12px;
                    padding: 20px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
                }
                .squad-card-title {
                    font-size: var(--font-size-sm, 0.9rem);
                    text-transform: uppercase;
                    letter-spacing: 1px;
                    color: var(--color-text-muted, #777);
                    font-weight: 700;
                    margin-bottom: 16px;
                    border-bottom: 1px solid var(--color-border-subtle, #2a2a2a);
                    padding-bottom: 8px;
                }

                /* Mode Switcher */
                .mode-selector {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }
                .mode-item {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 12px 16px;
                    border-radius: 8px;
                    background-color: var(--color-bg-primary, #121212);
                    border: 1px solid var(--color-border-subtle, #2a2a2a);
                    cursor: pointer;
                    transition: all 0.2s ease;
                }
                .mode-item:hover {
                    border-color: var(--color-accent-primary, #ff4b2b);
                    transform: translateX(4px);
                }
                .mode-item.active {
                    background: linear-gradient(135deg, rgba(255, 65, 108, 0.1) 0%, rgba(255, 75, 43, 0.1) 100%);
                    border-color: var(--color-accent-primary, #ff4b2b);
                }
                .mode-name {
                    font-weight: 600;
                    font-size: var(--font-size-sm, 0.95rem);
                }
                .mode-desc {
                    font-size: var(--font-size-xs, 0.75rem);
                    color: var(--color-text-muted, #777);
                    margin-top: 2px;
                }
                
                /* Subcommands Runner */
                .cmd-list {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                    max-height: 400px;
                    overflow-y: auto;
                    padding-right: 4px;
                }
                .cmd-item {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 12px 16px;
                    border-radius: 8px;
                    background-color: var(--color-bg-primary, #121212);
                    border: 1px solid var(--color-border-subtle, #2a2a2a);
                }
                .cmd-info {
                    flex: 1;
                }
                .cmd-name {
                    font-weight: 600;
                    font-family: var(--font-mono, monospace);
                    font-size: var(--font-size-sm, 0.9rem);
                    color: var(--color-accent-primary, #ff4b2b);
                }
                .cmd-desc {
                    font-size: var(--font-size-xs, 0.75rem);
                    color: var(--color-text-muted, #888);
                    margin-top: 4px;
                }
                .cmd-run-btn {
                    background: linear-gradient(135deg, #FF416C 0%, #FF4B2B 100%);
                    border: none;
                    color: white;
                    padding: 8px 16px;
                    border-radius: 6px;
                    font-size: var(--font-size-xs, 0.8rem);
                    font-weight: 600;
                    cursor: pointer;
                    transition: opacity 0.2s, transform 0.1s;
                }
                .cmd-run-btn:hover {
                    opacity: 0.9;
                }
                .cmd-run-btn:active {
                    transform: scale(0.97);
                }

                /* Terminal Card */
                .terminal-card {
                    background: #0d0d0d;
                    border: 1px solid #1f1f1f;
                    border-radius: 12px;
                    box-shadow: inset 0 0 10px rgba(0,0,0,0.8);
                    overflow: hidden;
                    display: flex;
                    flex-direction: column;
                    height: 380px;
                }
                .terminal-header {
                    background: #141414;
                    padding: 10px 16px;
                    border-bottom: 1px solid #1f1f1f;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .terminal-title {
                    font-family: var(--font-mono, monospace);
                    font-size: var(--font-size-xs, 0.8rem);
                    color: #888;
                }
                .terminal-controls {
                    display: flex;
                    gap: 8px;
                }
                .terminal-btn {
                    background: #222;
                    border: 1px solid #333;
                    color: #bbb;
                    padding: 4px 10px;
                    border-radius: 4px;
                    font-size: 11px;
                    cursor: pointer;
                    font-family: var(--font-mono, monospace);
                }
                .terminal-btn:hover {
                    background: #333;
                    color: #fff;
                }
                .terminal-body {
                    flex: 1;
                    padding: 16px;
                    overflow-y: auto;
                    font-family: var(--font-mono, 'Courier New', Courier, monospace);
                    font-size: 12px;
                    line-height: 1.5;
                    color: #39FF14;
                    background-color: #050505;
                }
                .terminal-line {
                    white-space: pre-wrap;
                    margin-bottom: 4px;
                }
                .terminal-line.start { color: #00e5ff; font-weight: bold; }
                .terminal-line.complete { color: #39FF14; font-weight: bold; }
                .terminal-line.failed { color: #ff3d00; font-weight: bold; }
                .terminal-line.error { color: #ff3d00; font-weight: bold; }

                /* Chat Layout with Session Drawer */
                .chat-container-layout {
                    display: grid;
                    grid-template-columns: 240px 1fr;
                    gap: 16px;
                    height: 640px;
                }
                @media(max-width: 768px) {
                    .chat-container-layout {
                        grid-template-columns: 1fr;
                        height: auto;
                    }
                }
                .session-sidebar {
                    background: var(--color-bg-surface, #1e1e1e);
                    border: 1px solid var(--color-border-subtle, #2d2d2d);
                    border-radius: 12px;
                    padding: 14px;
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
                }
                .session-sidebar-title {
                    font-size: 0.75rem;
                    font-weight: 700;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                    color: #888;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .new-session-btn {
                    background: rgba(255, 75, 43, 0.15);
                    border: 1px solid var(--color-accent-primary, #ff4b2b);
                    color: #fff;
                    font-size: 0.75rem;
                    font-weight: 600;
                    padding: 4px 8px;
                    border-radius: 4px;
                    cursor: pointer;
                    transition: background 0.2s;
                }
                .new-session-btn:hover {
                    background: rgba(255, 75, 43, 0.3);
                }
                .session-list {
                    flex: 1;
                    overflow-y: auto;
                    display: flex;
                    flex-direction: column;
                    gap: 6px;
                }
                .session-item {
                    padding: 8px 12px;
                    border-radius: 6px;
                    background: #141414;
                    border: 1px solid #2a2a2a;
                    font-size: 0.8rem;
                    font-weight: 500;
                    color: #ccc;
                    cursor: pointer;
                    word-break: break-all;
                    transition: all 0.2s;
                }
                .session-item:hover {
                    border-color: #ff4b2b;
                    color: #fff;
                }
                .session-item.active {
                    background: linear-gradient(135deg, rgba(255, 65, 108, 0.15) 0%, rgba(255, 75, 43, 0.15) 100%);
                    border-color: #ff4b2b;
                    color: #fff;
                    font-weight: 600;
                }

                .chat-layout {
                    display: flex;
                    flex-direction: column;
                    height: 100%;
                    background: var(--color-bg-surface, #1e1e1e);
                    border: 1px solid var(--color-border-subtle, #2d2d2d);
                    border-radius: 12px;
                    overflow: hidden;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
                }
                .chat-header-bar {
                    background: #141414;
                    padding: 10px 16px;
                    border-bottom: 1px solid #2a2a2a;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    font-size: 0.85rem;
                }
                .chat-messages {
                    flex: 1;
                    padding: 20px;
                    overflow-y: auto;
                    display: flex;
                    flex-direction: column;
                    gap: 16px;
                }
                .chat-bubble {
                    display: flex;
                    gap: 12px;
                    padding: 12px 16px;
                    border-radius: 8px;
                    background-color: var(--color-bg-primary, #121212);
                    border: 1px solid var(--color-border-subtle, #2a2a2a);
                    max-width: 85%;
                    align-self: flex-start;
                    position: relative;
                }
                .chat-bubble.user {
                    align-self: flex-end;
                    background-color: rgba(255, 75, 43, 0.08);
                    border-color: rgba(255, 75, 43, 0.25);
                }
                .chat-bubble.orchestrator { border-left: 3px solid #ff4b2b; }
                .chat-bubble.developer { border-left: 3px solid #00e5ff; }
                .chat-bubble.qa { border-left: 3px solid #4CAF50; }
                .chat-bubble.architect { border-left: 3px solid #E040FB; }
                .chat-bubble.thinking {
                    border-left: 3px solid #FFC107;
                    background-color: rgba(255, 193, 7, 0.08);
                    animation: pulseThinking 1.5s infinite ease-in-out;
                }
                @keyframes pulseThinking {
                    0% { opacity: 0.6; }
                    50% { opacity: 1; }
                    100% { opacity: 0.6; }
                }

                .chat-status-badge {
                    display: inline-block;
                    font-size: 0.7rem;
                    padding: 2px 6px;
                    border-radius: 4px;
                    margin-left: 8px;
                    font-weight: 600;
                    text-transform: uppercase;
                }
                .chat-status-badge.sending { background: rgba(255, 193, 7, 0.2); color: #ffc107; }
                .chat-status-badge.processing { background: rgba(0, 229, 255, 0.2); color: #00e5ff; }
                .chat-status-badge.delivered { background: rgba(76, 175, 80, 0.2); color: #4caf50; }

                .chat-avatar {
                    font-size: 1.3rem;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background-color: #252525;
                    width: 36px;
                    height: 36px;
                    border-radius: 50%;
                }
                .chat-content { flex: 1; }
                .chat-sender {
                    font-size: 0.75rem;
                    font-weight: 700;
                    color: var(--color-text-muted, #888);
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin-bottom: 4px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .chat-text {
                    font-size: 0.9rem;
                    line-height: 1.5;
                    white-space: pre-wrap;
                }

                /* Quick Target Agent Chips */
                .agent-chips-bar {
                    display: flex;
                    gap: 6px;
                    padding: 8px 16px 0;
                    background: #141414;
                    overflow-x: auto;
                }
                .agent-chip {
                    background: #222;
                    border: 1px solid #333;
                    color: #aaa;
                    font-size: 0.75rem;
                    padding: 4px 10px;
                    border-radius: 12px;
                    cursor: pointer;
                    font-weight: 600;
                    white-space: nowrap;
                    transition: all 0.2s;
                }
                .agent-chip:hover {
                    background: #333;
                    color: #fff;
                    border-color: #ff4b2b;
                }

                .chat-input-area {
                    display: flex;
                    gap: 12px;
                    padding: 12px 16px 16px;
                    border-top: 1px solid var(--color-border-subtle, #2a2a2a);
                    background: #141414;
                }
                .chat-input-box {
                    flex: 1;
                    background-color: #0d0d0d;
                    border: 1px solid #2a2a2a;
                    border-radius: 6px;
                    color: #fff;
                    padding: 12px;
                    font-size: 0.9rem;
                    outline: none;
                }
                .chat-input-box:focus {
                    border-color: var(--color-accent-primary, #ff4b2b);
                }
                .chat-send-btn {
                    background: linear-gradient(135deg, #FF416C 0%, #FF4B2B 100%);
                    border: none;
                    color: white;
                    padding: 0 24px;
                    border-radius: 6px;
                    font-size: 0.9rem;
                    font-weight: 600;
                    cursor: pointer;
                    transition: opacity 0.2s;
                }
                .chat-send-btn:hover { opacity: 0.9; }

                .chat-tools {
                    margin-top: 10px;
                    font-size: 0.8rem;
                    border: 1px solid #333;
                    border-radius: 4px;
                    overflow: hidden;
                    background-color: #0d0d0d;
                }
                .chat-tool-header {
                    background-color: #222;
                    color: #aaa;
                    padding: 6px 12px;
                    font-family: var(--font-mono, monospace);
                    cursor: pointer;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .chat-tool-header:hover {
                    background-color: #2a2a2a;
                    color: #fff;
                }
                .chat-tool-body {
                    background-color: #050505;
                    color: #39FF14;
                    padding: 10px;
                    font-family: var(--font-mono, monospace);
                    white-space: pre-wrap;
                    max-height: 250px;
                    overflow-y: auto;
                    border-top: 1px solid #222;
                }
            </style>
            
            <div class="squad-container">
                <div class="squad-header">
                    <div class="squad-title">
                        <h1>🚀 Squad Control Centre</h1>
                        <p>Independent agent executor interface and collaborative runtime</p>
                    </div>
                    <div id="status-badge" class="squad-status-badge">
                        <span class="squad-dot offline"></span>
                        <span id="status-text">Connecting...</span>
                    </div>
                </div>

                <!-- GitHub Token Banner on Squad-Agent Page -->
                <div id="github-token-banner" class="squad-github-banner" role="alert">
                    <div class="squad-github-banner__icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="12" y1="8" x2="12" y2="12"></line>
                            <line x1="12" y1="16" x2="12.01" y2="16"></line>
                        </svg>
                    </div>
                    <div class="squad-github-banner__content">
                        <div class="squad-github-banner__title">⚠️ GitHub Authentication Token ($GITHUB_TOKEN) Missing &mdash; Squad Disabled</div>
                        <div class="squad-github-banner__desc">
                            The Squad Agent has been deactivated because <code>GITHUB_TOKEN</code> is not configured in the host environment. Git operations, code generation, and autonomous squad agents require authenticated GitHub access. Configure <code>export GITHUB_TOKEN="ghp_..."</code> (or <code>setx GITHUB_TOKEN "ghp_..."</code> on Windows) in your OS environment to enable the squad.
                        </div>
                    </div>
                </div>

                <div class="squad-tabs">
                    <button class="squad-tab-btn active" data-tab="runner">🎛️ Command Control</button>
                    <button class="squad-tab-btn" data-tab="chat">💬 Squad Chat</button>
                </div>

                <!-- Runner View -->
                <div id="tab-runner" class="tab-content active">
                    <div class="squad-grid">
                        <div class="squad-card">
                            <div class="squad-card-title">🕹️ Active Squad Mode</div>
                            <div id="mode-selector" class="mode-selector">
                                <div class="mode-item" data-mode="1">
                                    <div>
                                        <div class="mode-name">🛡️ Spec-First</div>
                                        <div class="mode-desc">High safety, BDD mandatory.</div>
                                    </div>
                                </div>
                                <div class="mode-item" data-mode="2">
                                    <div>
                                        <div class="mode-name">🧪 Free-Labs</div>
                                        <div class="mode-desc">High speed, experimentations.</div>
                                    </div>
                                </div>
                                <div class="mode-item" data-mode="3">
                                    <div>
                                        <div class="mode-name">🛰️ Fleet-Commander</div>
                                        <div class="mode-desc">Global sync, multi-repo.</div>
                                    </div>
                                </div>
                                <div class="mode-item" data-mode="4">
                                    <div>
                                        <div class="mode-name">🥷 Direct-Action</div>
                                        <div class="mode-desc">Bypass mode logic.</div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="squad-card">
                            <div class="squad-card-title">⚙️ Subcommand Execution</div>
                            <div id="commands-list" class="cmd-list">
                                <div style="color: #777; font-size: var(--font-size-xs);">Loading command manifest...</div>
                            </div>
                        </div>
                    </div>

                    <div class="terminal-card">
                        <div class="terminal-header">
                            <div class="terminal-title">📟 live_execution_feed.log</div>
                            <div class="terminal-controls">
                                <button id="btn-clear-term" class="terminal-btn">Clear Log</button>
                            </div>
                        </div>
                        <div id="terminal-body" class="terminal-body">
                            <div class="terminal-line">[SYSTEM] Ready for command dispatch. Select a command above to execute.</div>
                        </div>
                    </div>
                </div>

                <!-- Chat View -->
                <div id="tab-chat" class="tab-content">
                    <div class="chat-container-layout">
                        <!-- Session Drawer Sidebar -->
                        <div class="session-sidebar">
                            <div class="session-sidebar-title">
                                <span>💬 Sessions</span>
                                <button id="new-session-btn" class="new-session-btn">➕ New</button>
                            </div>
                            <div id="session-list" class="session-list"></div>
                        </div>

                        <!-- Chat Layout -->
                        <div class="chat-layout">
                            <div class="chat-header-bar">
                                <span id="current-session-label">Session: <strong>squad_sync_session</strong></span>
                                <span id="chat-live-status" style="color: #4CAF50; font-size: 0.75rem;">● Live SSE Active</span>
                            </div>

                            <div id="chat-messages" class="chat-messages">
                                <div class="chat-bubble system">
                                    <span class="chat-avatar">🤖</span>
                                    <div class="chat-content">
                                        <div class="chat-sender">System</div>
                                        <div class="chat-text">Welcome to the AI Squad Chat room. Type a goal below or target a specific agent (@orchestrator, @developer, @qa, @architect).</div>
                                    </div>
                                </div>
                            </div>

                            <!-- Agent Target Quick Chips Bar -->
                            <div class="agent-chips-bar">
                                <span class="agent-chip" data-tag="@orchestrator ">🤖 @orchestrator</span>
                                <span class="agent-chip" data-tag="@developer ">💻 @developer</span>
                                <span class="agent-chip" data-tag="@qa ">🧪 @qa</span>
                                <span class="agent-chip" data-tag="@architect ">📐 @architect</span>
                            </div>

                            <div class="chat-input-area">
                                <input type="text" id="chat-input-box" class="chat-input-box" placeholder="Ask the squad or target @agent..." />
                                <button id="chat-send-btn" class="chat-send-btn">Send</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    setupEventListeners() {
        // Tab switching
        const tabBtns = this.querySelectorAll('.squad-tab-btn');
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                tabBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                const tab = btn.dataset.tab;
                this.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                this.querySelector(`#tab-${tab}`).classList.add('active');
            });
        });

        // Clear terminal button
        const clearBtn = this.querySelector('#btn-clear-term');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                const body = this.querySelector('#terminal-body');
                if (body) {
                    body.innerHTML = '<div class="terminal-line">[SYSTEM] Terminal logs cleared.</div>';
                }
            });
        }

        // Mode selectors
        const modeItems = this.querySelectorAll('.mode-item');
        modeItems.forEach(item => {
            item.addEventListener('click', async () => {
                const mode = item.dataset.mode;
                await this.switchMode(mode);
            });
        });

        // New Session button
        const newSessionBtn = this.querySelector('#new-session-btn');
        if (newSessionBtn) {
            newSessionBtn.addEventListener('click', () => {
                const sessionName = prompt("Enter new session name (e.g., feature_dev_2):", `session_${Date.now().toString().slice(-4)}`);
                if (sessionName && sessionName.trim()) {
                    const cleanName = sessionName.trim().replace(/\s+/g, '_');
                    if (!this.sessions.includes(cleanName)) {
                        this.sessions.push(cleanName);
                        localStorage.setItem('squad_agent_session_list', JSON.stringify(this.sessions));
                    }
                    this.switchSession(cleanName);
                }
            });
        }

        // Quick Agent Chips
        const chips = this.querySelectorAll('.agent-chip');
        const chatInputBox = this.querySelector('#chat-input-box');
        chips.forEach(chip => {
            chip.addEventListener('click', () => {
                if (chatInputBox) {
                    const tag = chip.dataset.tag;
                    if (!chatInputBox.value.includes(tag.trim())) {
                        chatInputBox.value = tag + chatInputBox.value;
                    }
                    chatInputBox.focus();
                }
            });
        });

        // Chat send interaction
        const chatSendBtn = this.querySelector('#chat-send-btn');
        if (chatSendBtn && chatInputBox) {
            const sendMsg = async () => {
                const text = chatInputBox.value.trim();
                if (!text) return;
                chatInputBox.value = '';
                await this.handleUserSend(text);
            };
            chatSendBtn.addEventListener('click', sendMsg);
            chatInputBox.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') sendMsg();
            });
        }
    }

    renderSessionList() {
        const list = this.querySelector('#session-list');
        if (!list) return;
        list.innerHTML = '';
        this.sessions.forEach(sessId => {
            const item = document.createElement('div');
            item.className = `session-item ${sessId === this.activeSessionId ? 'active' : ''}`;
            item.textContent = sessId;
            item.addEventListener('click', () => this.switchSession(sessId));
            list.appendChild(item);
        });
        const label = this.querySelector('#current-session-label');
        if (label) {
            label.innerHTML = `Session: <strong>${this.activeSessionId}</strong>`;
        }
    }

    async switchSession(sessionId) {
        if (this.activeSessionId === sessionId) return;
        this.activeSessionId = sessionId;
        localStorage.setItem('squad_agent_active_session', sessionId);
        this.renderSessionList();

        // Load history and reconnect SSE
        await this.loadChatHistory(this.activeSessionId);
        this.startChatStream(this.activeSessionId);
    }

    async switchMode(mode) {
        if (this.statusData.github_configured === false) {
            this.printTerminalLine('[ERROR] Cannot switch mode: Squad Agent is disabled (missing GITHUB_TOKEN).', 'error');
            return;
        }
        try {
            const resp = await fetch(`${this.baseUrl}/api/v1/squad/active-mode`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode })
            });
            if (resp.ok) {
                const data = await resp.json();
                if (data.success) {
                    this.printTerminalLine(`[SYSTEM] Mode switched: ${data.message}`, 'start');
                    await this.loadActiveMode();
                    this.updateUI();
                } else {
                    this.printTerminalLine(`[SYSTEM] Mode switch failed: ${data.message}`, 'error');
                }
            }
        } catch (e) {
            this.printTerminalLine(`[SYSTEM] Connection error switching mode: ${e}`, 'error');
        }
    }

    runCommand(cmdName) {
        if (this.statusData.github_configured === false) {
            this.printTerminalLine(`[ERROR] Cannot execute "${cmdName}": Squad Agent is disabled (missing GITHUB_TOKEN).`, 'error');
            return;
        }
        if (this.eventSource) {
            this.eventSource.close();
        }

        const terminalBody = this.querySelector('#terminal-body');
        if (terminalBody) {
            terminalBody.innerHTML = '';
        }

        this.printTerminalLine(`[SYSTEM] Connecting to stream for subcommand "${cmdName}"...`, 'start');

        this.eventSource = new EventSource(`${this.baseUrl}/api/v1/squad/run/${cmdName}`);

        this.eventSource.onmessage = (event) => {
            const data = event.data;
            let type = '';
            if (data.startsWith('[START]')) type = 'start';
            else if (data.startsWith('[COMPLETE]')) type = 'complete';
            else if (data.startsWith('[FAILED]')) type = 'failed';
            else if (data.startsWith('[ERROR]')) type = 'error';

            this.printTerminalLine(data, type);
        };

        this.eventSource.onerror = (err) => {
            this.printTerminalLine('[SYSTEM] EventSource stream closed.', 'error');
            this.eventSource.close();
        };
    }

    printTerminalLine(text, type = '') {
        const body = this.querySelector('#terminal-body');
        if (!body) return;

        const line = document.createElement('div');
        line.className = 'terminal-line';
        if (type) {
            line.classList.add(type);
        }
        line.textContent = text;
        body.appendChild(line);
        body.scrollTop = body.scrollHeight;
    }

    async loadChatHistory(sessionId) {
        try {
            const resp = await fetch(`${this.baseUrl}/api/v1/squad/chat/${sessionId}`);
            if (resp.ok) {
                const data = await resp.json();
                const chatMessages = this.querySelector('#chat-messages');
                if (chatMessages) {
                    chatMessages.innerHTML = `
                        <div class="chat-bubble system">
                            <span class="chat-avatar">🤖</span>
                            <div class="chat-content">
                                <div class="chat-sender">System</div>
                                <div class="chat-text">Session <strong>${sessionId}</strong> loaded. Ask the squad to implement, test, or review code.</div>
                            </div>
                        </div>
                    `;
                    if (data.success && Array.isArray(data.history)) {
                        data.history.forEach(msg => this.appendChatMessage(msg));
                    }
                }
            }
        } catch (e) {
            console.error("Failed to load chat history:", e);
        }
    }

    startChatStream(sessionId) {
        if (this.chatEventSource) {
            this.chatEventSource.close();
        }

        this.chatEventSource = new EventSource(`${this.baseUrl}/api/v1/squad/chat/stream/${sessionId}`);
        this.chatEventSource.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                this.removeThinkingIndicator();
                this.updateLastUserBadge('delivered');
                this.setProcessingState(false);
                this.appendChatMessage(msg);
            } catch (e) {
                console.error("Failed to parse SSE chat message:", e);
                this.setProcessingState(false);
            }
        };
        this.chatEventSource.onerror = () => {
            // Re-enable input if SSE drops or disconnects
            this.setProcessingState(false);
        };
    }

    async handleUserSend(text) {
        if (this.statusData.github_configured === false) {
            this.appendChatMessage({
                sender: 'system',
                content: '⚠️ Squad Agent is disabled: GITHUB_TOKEN is not configured.'
            });
            return;
        }
        const msgId = 'user_msg_' + Date.now();
        // Lock UI send button & input box while task is being processed
        this.setProcessingState(true);

        // 1. Immediately render user bubble with 'Sending... 📤' status badge
        this.appendChatMessage({
            id: msgId,
            sender: 'user',
            content: text,
            status: 'sending'
        });

        // 2. Post message to backend
        try {
            const resp = await fetch(`${this.baseUrl}/api/v1/squad/chat/${this.activeSessionId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });

            if (resp.ok) {
                // Update badge to 'Thinking 🧠' and show animated Agent Thinking Bar
                this.updateUserBadge(msgId, 'processing');
                this.showThinkingIndicator("Squad AI", "Analyzing workspace context & executing agent pipeline...");
            } else {
                this.updateUserBadge(msgId, 'error');
                this.setProcessingState(false);
            }
        } catch (e) {
            console.error("Connection error posting chat message:", e);
            this.updateUserBadge(msgId, 'error');
            this.setProcessingState(false);
        }
    }

    setProcessingState(isProcessing) {
        this.isProcessing = isProcessing;
        const sendBtn = this.querySelector('#chat-send-btn');
        const inputBox = this.querySelector('#chat-input-box');
        const statusLabel = this.querySelector('#chat-live-status');
        const isGhConfigured = this.statusData.github_configured !== false;

        if (sendBtn) {
            if (!isGhConfigured) {
                sendBtn.disabled = true;
                sendBtn.style.opacity = '0.35';
                sendBtn.style.cursor = 'not-allowed';
                sendBtn.textContent = 'Send';
            } else {
                sendBtn.disabled = isProcessing;
                sendBtn.style.opacity = isProcessing ? '0.6' : '1';
                sendBtn.style.cursor = isProcessing ? 'not-allowed' : 'pointer';
                sendBtn.textContent = isProcessing ? 'Processing... ⏳' : 'Send';
            }
        }
        if (inputBox) {
            if (!isGhConfigured) {
                inputBox.disabled = true;
                inputBox.style.opacity = '0.5';
                inputBox.style.cursor = 'not-allowed';
            } else {
                inputBox.disabled = isProcessing;
                inputBox.style.opacity = '';
                inputBox.style.cursor = '';
                if (!isProcessing) {
                    inputBox.focus();
                }
            }
        }
        if (statusLabel) {
            if (!isGhConfigured) {
                statusLabel.style.color = '#F44336';
                statusLabel.textContent = '● Squad Disabled (No GitHub Token)';
            } else if (isProcessing) {
                statusLabel.style.color = '#FFC107';
                statusLabel.textContent = '⚡ Task Processing Active...';
            } else {
                statusLabel.style.color = '#4CAF50';
                statusLabel.textContent = '● Live SSE Ready';
            }
        }
    }

    showThinkingIndicator(agentName = "Squad AI", stepText = "Analyzing prompt & generating turn...") {
        this.removeThinkingIndicator();
        const chatMessages = this.querySelector('#chat-messages');
        if (!chatMessages) return;

        const thinking = document.createElement('div');
        thinking.id = 'agent-thinking-indicator';
        thinking.className = 'chat-bubble thinking';
        thinking.innerHTML = `
            <span class="chat-avatar">🤖</span>
            <div class="chat-content">
                <div class="chat-sender">
                    <span>${agentName}</span>
                    <span class="chat-status-badge processing">Processing ⏳</span>
                </div>
                <div class="chat-text">
                    <div style="font-weight: 600; color: #ffc107;">${stepText}</div>
                    <div style="font-size: 0.75rem; color: #aaa; margin-top: 4px;">
                        <i class="fa fa-spinner fa-spin"></i> Squad agents are parsing knowledge base, evaluating tools, and generating response...
                    </div>
                </div>
            </div>
        `;
        chatMessages.appendChild(thinking);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    removeThinkingIndicator() {
        const thinking = this.querySelector('#agent-thinking-indicator');
        if (thinking) {
            thinking.remove();
        }
    }

    updateUserBadge(msgId, status) {
        const msgEl = this.querySelector(`#${msgId}`);
        if (!msgEl) return;
        const badgeEl = msgEl.querySelector('.chat-status-badge');
        if (badgeEl) {
            badgeEl.className = `chat-status-badge ${status}`;
            if (status === 'sending') badgeEl.textContent = 'Sending 📤';
            else if (status === 'processing') badgeEl.textContent = 'Thinking 🧠';
            else if (status === 'delivered') badgeEl.textContent = 'Delivered ✅';
            else if (status === 'error') badgeEl.textContent = 'Failed ❌';
        }
    }

    updateLastUserBadge(status) {
        const userBubbles = this.querySelectorAll('.chat-bubble.user');
        if (userBubbles.length > 0) {
            const lastUserBubble = userBubbles[userBubbles.length - 1];
            const badgeEl = lastUserBubble.querySelector('.chat-status-badge');
            if (badgeEl) {
                badgeEl.className = `chat-status-badge ${status}`;
                if (status === 'delivered') badgeEl.textContent = 'Delivered ✅';
            }
        }
    }

    appendChatMessage(msg) {
        const chatMessages = this.querySelector('#chat-messages');
        if (!chatMessages) return;

        // Prevent duplicate user messages if already rendered dynamically via handleUserSend
        if (msg.sender === 'user' && msg.id && this.querySelector(`#${msg.id}`)) {
            return;
        }

        // Map avatars
        const avatars = {
            'user': '👤',
            'orchestrator': '🤖',
            'developer': '💻',
            'qa': '🧪',
            'architect': '📐',
            'codeindexer': '🔍',
            'docindexer': '📚',
            'fleetcommander': '🛰️'
        };
        const avatar = avatars[msg.sender] || '🤖';

        const bubble = document.createElement('div');
        if (msg.id) bubble.id = msg.id;
        bubble.className = `chat-bubble ${msg.sender || 'system'}`;

        let statusBadgeHtml = '';
        if (msg.sender === 'user') {
            const st = msg.status || 'delivered';
            const badgeLabel = st === 'sending' ? 'Sending 📤' : (st === 'processing' ? 'Thinking 🧠' : 'Delivered ✅');
            statusBadgeHtml = `<span class="chat-status-badge ${st}">${badgeLabel}</span>`;
        }

        let toolCallsHtml = '';
        let toolCalls = msg.tool_calls;
        if (typeof toolCalls === 'string') {
            try {
                toolCalls = JSON.parse(toolCalls);
            } catch (e) {
                toolCalls = [];
            }
        }
        if (Array.isArray(toolCalls) && toolCalls.length > 0) {
            toolCalls.forEach((tool) => {
                const toolArgs = JSON.stringify(tool.args || {});
                toolCallsHtml += `
                    <div class="chat-tools">
                        <div class="chat-tool-header" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'">
                            <span>🛠️ Tool: ${tool.name || 'Action'}</span>
                            <span style="font-size: 10px;">[Toggle Output]</span>
                        </div>
                        <div class="chat-tool-body" style="display: none;">
                            <strong>Arguments:</strong> ${toolArgs}
                            <hr style="border-color: #333; margin: 8px 0;" />
                            <strong>Result:</strong><br />${tool.result || ''}
                        </div>
                    </div>
                `;
            });
        }

        bubble.innerHTML = `
            <span class="chat-avatar">${avatar}</span>
            <div class="chat-content">
                <div class="chat-sender">
                    <span>${msg.sender || 'system'}</span>
                    ${statusBadgeHtml}
                </div>
                <div class="chat-text">${msg.content || ''}</div>
                ${toolCallsHtml}
            </div>
        `;

        chatMessages.appendChild(bubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    updateUI() {
        const badge = this.querySelector('#status-badge');
        const statusText = this.querySelector('#status-text');
        const dot = this.querySelector('.squad-dot');
        const isGhConfigured = this.statusData.github_configured !== false;

        if (badge && statusText && dot) {
            if (!isGhConfigured) {
                dot.className = 'squad-dot offline';
                statusText.textContent = 'Squad Disabled (No GitHub Token)';
                badge.style.borderColor = 'rgba(255, 75, 43, 0.5)';
            } else {
                dot.className = 'squad-dot ' + (this.statusData.healthy ? 'healthy' : 'offline');
                statusText.textContent = this.statusData.healthy ? 'Healthy (v' + this.statusData.version + ')' : this.statusData.status;
                badge.style.borderColor = '';
            }
        }

        // Toggle GitHub Token Alert Banner on Squad-Agent Page
        const ghBanner = this.querySelector('#github-token-banner');
        if (ghBanner) {
            ghBanner.style.display = isGhConfigured ? 'none' : 'flex';
        }

        // Mode Switcher Controls
        const modeItems = this.querySelectorAll('.mode-item');
        modeItems.forEach(item => {
            if (!isGhConfigured) {
                item.style.pointerEvents = 'none';
                item.style.opacity = '0.35';
                item.style.cursor = 'not-allowed';
                item.title = 'Squad disabled: GITHUB_TOKEN is not configured.';
                item.classList.remove('active');
            } else {
                item.style.pointerEvents = '';
                item.style.opacity = '';
                item.style.cursor = 'pointer';
                item.title = '';
                if (item.dataset.mode === String(this.activeMode.mode)) {
                    item.classList.add('active');
                } else {
                    item.classList.remove('active');
                }
            }
        });

        // Command Runner Execution List
        const list = this.querySelector('#commands-list');
        if (list && this.commands.length > 0) {
            list.innerHTML = '';
            this.commands.forEach(cmd => {
                if (cmd.name === 'squad-agent') return;

                const item = document.createElement('div');
                item.className = 'cmd-item';
                item.innerHTML = `
                    <div class="cmd-info">
                        <div class="cmd-name">${cmd.name}</div>
                        <div class="cmd-desc">${cmd.description}</div>
                    </div>
                    <button class="cmd-run-btn" data-cmd="${cmd.name}" ${!isGhConfigured ? 'disabled style="opacity: 0.35; cursor: not-allowed;" title="Squad disabled: GITHUB_TOKEN is not configured."' : ''}>Execute</button>
                `;
                list.appendChild(item);
            });

            if (isGhConfigured) {
                const runBtns = list.querySelectorAll('.cmd-run-btn');
                runBtns.forEach(btn => {
                    btn.addEventListener('click', () => {
                        const cmd = btn.dataset.cmd;
                        this.runCommand(cmd);
                    });
                });
            }
        }

        // Chat Input and Controls
        const chatInput = this.querySelector('#chat-input-box');
        const chatSend = this.querySelector('#chat-send-btn');
        const newSessionBtn = this.querySelector('#new-session-btn');
        const agentChips = this.querySelectorAll('.agent-chip');

        if (chatInput && chatSend) {
            if (!isGhConfigured) {
                chatInput.disabled = true;
                chatInput.placeholder = '⚠️ Squad disabled: GITHUB_TOKEN is not configured in OS environment';
                chatInput.style.opacity = '0.5';
                chatInput.style.cursor = 'not-allowed';
                chatSend.disabled = true;
                chatSend.style.opacity = '0.35';
                chatSend.style.cursor = 'not-allowed';
            } else if (!this.isProcessing) {
                chatInput.disabled = false;
                chatInput.placeholder = 'Ask the squad or target @agent...';
                chatInput.style.opacity = '';
                chatInput.style.cursor = '';
                chatSend.disabled = false;
                chatSend.style.opacity = '';
                chatSend.style.cursor = 'pointer';
            }
        }

        if (newSessionBtn) {
            if (!isGhConfigured) {
                newSessionBtn.disabled = true;
                newSessionBtn.style.opacity = '0.4';
                newSessionBtn.style.cursor = 'not-allowed';
            } else {
                newSessionBtn.disabled = false;
                newSessionBtn.style.opacity = '';
                newSessionBtn.style.cursor = 'pointer';
            }
        }

        agentChips.forEach(chip => {
            if (!isGhConfigured) {
                chip.style.pointerEvents = 'none';
                chip.style.opacity = '0.35';
            } else {
                chip.style.pointerEvents = '';
                chip.style.opacity = '';
            }
        });
    }
}

customElements.define('squad-agent-mfe', SquadAgentMFE);

