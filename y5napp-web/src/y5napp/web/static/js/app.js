import { Renderer } from "./renderer/renderer.js";
import { createElement } from "./dom.js";

// -----------
// TAB
// -----------

class Tab {

    constructor(id, name, url, onConnect) {
        this.id = id;
        this.name = name;
        this.url = url;
        this.ws = null;
        this._onConnect = onConnect;

        this.pane = createElement("div", "tab-pane");
        this.stream = createElement("div", "tab-stream");

        const inputCard = createElement("div", "input-card");
        this.input = createElement("input", "tab-input");
        this.input.placeholder = "Type a command...";

        const statusLine = createElement("div", "status-line");
        this.brand = createElement("span", "brand");
        this.brand.textContent = "Yakoon";
        this.sep = createElement("span", "sep");
        this.sep.textContent = "·";
        this.prefix = createElement("span", "prefix");
        this.prefix.textContent = `${name}:`;
        this.path = createElement("span", "path");
        this.path.textContent = "/$";

        statusLine.append(this.brand, this.sep, this.prefix, this.path);
        inputCard.append(this.input, statusLine);
        this.pane.append(this.stream, inputCard);

        this.input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                this._submit();
            }
            if (e.key === "Escape") {
                e.preventDefault();
                this._submit("bg");
            }
        });
    }

    _submit(text) {
        if (text === undefined) {
            text = this.input.value.trim();
        }
        this.input.value = "";

        if (text) {
            if (text.startsWith("/connect ")) {
                const url = text.slice(9).trim();
                if (this._onConnect) this._onConnect(url, url);
                return;
            }
            if (text === "/disconnect") {
                this.disconnect();
                return;
            }
        }

        if (!this.ws) return;
        this.ws.send(JSON.stringify({
            type: "input",
            channel: "command",
            payload: {
                raw: text,
                context: { command: text, origin: "human" },
            },
        }));
    }

    handleProjection(event) {
        if (event.view_params) {
            const connectUrl = event.view_params.connect;
            if (connectUrl) {
                const name = event.view_params.connect_name || connectUrl;
                if (this._onConnect) this._onConnect(name, connectUrl);
                return;
            }
            if (event.view_params.clear) {
                this.stream.innerHTML = "";
                return;
            }
        }

        const regionKey = event.job || (event.context && event.context.origin) || crypto.randomUUID();
        let regionEl = this.stream.querySelector(`[data-region-id="${regionKey}"]`);
        if (!regionEl) {
            const turn = createElement("div", "turn");
            const echo = event.context && event.context.echo;
            if (echo) {
                const line = createElement("div", "input-line");
                line.textContent = `$ ${echo}`;
                turn.appendChild(line);
            }
            regionEl = createElement("div", "turn-region");
            regionEl.dataset.regionId = regionKey;
            turn.appendChild(regionEl);
            this.stream.appendChild(turn);
            this.stream.lastElementChild?.scrollIntoView({ behavior: "smooth" });

            regionEl._dispatch = {
                command: (cmd, payload, el) => {
                    if (!this.ws) return;
                    this.ws.send(JSON.stringify({
                        type: "input",
                        channel: "command",
                        payload: {
                            raw: cmd,
                            context: { command: cmd, origin: "human" },
                        },
                    }));
                },
            };
        }

        let renderer = regionEl._renderer;
        if (!renderer) {
            renderer = new Renderer(regionEl, regionEl._dispatch);
            regionEl._renderer = renderer;
            regionEl.dataset.renderer = "true";
        }

        if (event.state) {
            this._updatePrompt(event.state);
        }

        renderer.apply(event);
    }

    _updatePrompt(state) {
        const name = state.controller
            ? state.controller.charAt(0).toUpperCase() + state.controller.slice(1)
            : "";
        const user = state.user || "";
        this.prefix.textContent = user
            ? `${user}@${name}:`
            : name
              ? `${name}:`
              : "";
        this.path.textContent = `${state.node_path || "/"}$`;
    }

    connect() {
        if (this.ws) return;
        this.ws = new WebSocket(this.url);
        this.ws.onopen = () => {
            this.ws.send(JSON.stringify({ type: "connect" }));
        };
        this.ws.onmessage = (msg) => {
            try {
                const data = JSON.parse(msg.data);
                if (data.type === "projection") {
                    this.handleProjection(data.payload);
                }
            } catch (e) {
                console.warn("WS parse error:", e);
            }
        };
        this.ws.onclose = () => {
            this.ws = null;
        };
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    activate() {
        this.pane.classList.add("active");
        this.input.focus();
    }

    deactivate() {
        this.pane.classList.remove("active");
    }
}

// -----------
// APPLICATION
// -----------

function initApp() {
    const dom = {
        app: document.getElementById("app"),
        sidebarToggle: document.getElementById("toggle-sidebar"),
        tabbar: document.getElementById("tabbar"),
        tabsContainer: document.getElementById("tabs-container"),
    };

    let activeTab = null;
    const tabs = {};

    function switchTab(id) {
        if (activeTab) {
            tabs[activeTab].deactivate();
            document.querySelector(`.tab-btn[data-tab="${activeTab}"]`)?.classList.remove("active");
        }
        activeTab = id;
        tabs[id].activate();
        document.querySelector(`.tab-btn[data-tab="${id}"]`)?.classList.add("active");
    }

    function createTab(name, url, autoconnect) {
        const id = "tab-" + crypto.randomUUID().slice(0, 8);
        const tab = new Tab(id, name, url, (n, u) => createTab(n, u, true));
        tabs[id] = tab;

        const btn = createElement("button", "tab-btn");
        btn.textContent = name;
        btn.dataset.tab = id;
        btn.onclick = () => switchTab(id);
        dom.tabbar.appendChild(btn);

        dom.tabsContainer.appendChild(tab.pane);

        switchTab(id);
        if (autoconnect) tab.connect();

        return id;
    }

    const runtimes = window.__YAKOON_RUNTIMES || [
        { name: "local", url: "ws://localhost:9100", autoconnect: true },
    ];

    for (const rt of runtimes) {
        createTab(rt.name, rt.url, rt.autoconnect);
    }

    dom.sidebarToggle.onclick = () => {
        dom.app.classList.toggle("sidebar-collapsed");
    };
}

initApp();
