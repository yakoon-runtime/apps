import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";
import { renderFields } from "../fields.js";

registerBlock("fields", (node, dispatch) => {
    const el = createElement("div", "fields");
    renderFields(node, dispatch, el);
    return el;
});