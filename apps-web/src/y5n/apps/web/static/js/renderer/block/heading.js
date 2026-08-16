import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";
import { renderTextContent } from "../text.js";

function tagForLevel(level) {
    if (level === 1) return "h1";
    if (level === 2) return "h2";
    if (level === 3) return "h3";
    return "div";
}

registerBlock("heading", (node, dispatch) => {
    const tag = tagForLevel(node.props.level);
    const el = createElement(tag);

    el.classList.add("heading", `heading-${node.props.level}`);

    renderTextContent(node.props.text, dispatch, el);

    return el;
});