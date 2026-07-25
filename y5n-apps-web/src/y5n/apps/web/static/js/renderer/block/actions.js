import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";
import { renderActions } from "../actions.js";

registerBlock("actions", (node, dispatch) => {
    const el = createElement("div", "actions");
    renderActions(node, dispatch, el);
    return el;
});