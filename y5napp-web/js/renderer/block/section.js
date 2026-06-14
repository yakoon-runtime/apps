import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";

registerBlock("section", (node) => {
    const el = createElement("div");
    el.classList.add("section");
    return el;
});