import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";

registerBlock("stack", () => {
    const el = createElement("div");
    el.classList.add("stack");
    return el;
});