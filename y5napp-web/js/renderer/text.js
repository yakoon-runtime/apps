import { renderInline } from "./inline/core.js";

export function renderTextContent(text, dispatch, container) {
    if (!text) return;

    if (typeof text === "string") {
        container.textContent = text;
        return;
    }

    for (const inline of text) {
        container.appendChild(renderInline(inline, dispatch, container));
    }
}