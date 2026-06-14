import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";
import { renderKVItem } from "../kv.js";

registerBlock("kv_item", (node, dispatch) => {
    const el = createElement("div", "kv-item");
    renderKVItem(node, dispatch, el);
    return el;
});