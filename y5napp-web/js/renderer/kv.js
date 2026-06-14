import { createElement } from "../dom.js";
import { renderTextContent } from "./text.js";

export function renderKVItem(node, dispatch, container) {

    const key = createElement("div", "kv-key");
    key.textContent = node.props.key;

    const value = createElement("div", "kv-value");
    renderTextContent(node.props.value, dispatch, value);

    container.appendChild(key);
    container.appendChild(value);
}