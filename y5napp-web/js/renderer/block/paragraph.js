import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";
import { renderTextContent } from "../text.js";

registerBlock("paragraph", (node, dispatch) => {
    const el = createElement("p", "paragraph");
    renderTextContent(node.props.text, dispatch, el);
    return el;
});