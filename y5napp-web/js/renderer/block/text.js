import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";
import { renderTextContent } from "../text.js";

registerBlock("text", (node, dispatch) => {
    const el = createElement("p");

    el.classList.add("paragraph", "text");

    renderTextContent(node.props.text, dispatch, el);

    return el;
});