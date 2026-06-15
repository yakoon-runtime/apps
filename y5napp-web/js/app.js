import { createWS } from "./stream.js";
import { Renderer } from "./renderer/renderer.js";
import { createElement } from "./dom.js";

// -----------
// APPLICATION
// -----------

function initApp() {

    const dom = {
        app: document.getElementById("app"),
        stream: document.getElementById("stream"),
        input: document.getElementById("commandbar-input"),
        sidebar: document.getElementById("toggle-sidebar"),
    };

    function handleProjection(event) {

        if (event.view_params && event.view_params.clear) {
            dom.stream.innerHTML = "";
            return;
        }

        const regionId = event.context.origin;

        const regionEl = document.querySelector(`[data-region-id="${regionId}"]`);
        if (!regionEl) {
            console.warn("Stale response dropped:", regionId);
            return;
        }

        let renderer = regionEl._renderer;
        if (!renderer) {
            renderer = new Renderer(regionEl, dispatch);
            regionEl._renderer = renderer;
            regionEl.dataset.renderer = "true";
        }

        if (event.state) {
            updatePrompt(event.state);
        }

        renderer.apply(event);
    }

    const ws = createWS(handleProjection);
    const dispatch = createDispatcher(ws, createRootRegion);

    wireCommandBar(dom, dispatch, createRootRegion);
    registerSideBarToggle(dom);

    function createRootRegion(command) {
        const container = createElement("div", "turn");

        if (command) {
            const line = createElement("div", "input-line");
            line.textContent = `$ ${command}`;
            container.appendChild(line);
        }

        const region = createElement("div", "turn-region");
        region.dataset.regionId = "r-" + crypto.randomUUID();

        container.appendChild(region);
        dom.stream.appendChild(container);

        return region;
    }

}

// -----------
// INTERNALS
// -----------

function scrollToBottom() {
    const el = document.getElementById("stream");
    if (!el) return;

    //el.scrollTop = el.scrollHeight;
    el.lastElementChild?.scrollIntoView({ behavior: "smooth" });
}

function createDispatcher(ws, createRootRegion) {

    function send(command, payload = {}, regionEl) {
        const regionId = regionEl.dataset.regionId;

        ws.send(JSON.stringify({
            type: "input",
            channel: "command",
            payload: {
                raw: command,
                context: {
                    command,
                    origin: regionId,
                }
            }
        }));
    }

    function newTurn(command) {
        const regionEl = createRootRegion(command);
        send(command, {}, regionEl);
    }

    return {
        command: send,
        newTurn
    };
}

function wireCommandBar(dom, dispatch, createRootRegion) {

    function send() {
        const value = dom.input.value;
        if (!value) return;

        const regionEl = createRootRegion(value);

        dispatch.command(value, {}, regionEl);

        dom.input.value = "";
        scrollToBottom();
    }

    dom.input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") send();
    });
}

function registerSideBarToggle(dom) {
    dom.sidebar.onclick = () => {
        dom.app.classList.toggle("sidebar-collapsed");
    };
}

function updatePrompt(state) {
    const prefixEl = document.querySelector(".prefix");
    const pathEl = document.querySelector(".path");
    if (!prefixEl || !pathEl) return;

    const name = state.controller
        ? state.controller.charAt(0).toUpperCase() + state.controller.slice(1)
        : "";
    const user = state.user || "";
    prefixEl.textContent = user ? `${user}@${name}:` : name ? `${name}:` : "";

    const nodePath = state.node_path || "/";
    pathEl.textContent = `${nodePath}$`;
}

initApp();