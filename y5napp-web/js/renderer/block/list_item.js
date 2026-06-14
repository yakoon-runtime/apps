import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";
import { renderTextContent } from "../text.js";

registerBlock("list_item", (node, dispatch) => {
    const el = createElement("li", "list-item");
    renderTextContent(node.props.text, dispatch, el);
    return el;
});