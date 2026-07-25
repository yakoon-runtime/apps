import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";

registerBlock("flow", () => {
    const el = createElement("div");
    el.classList.add("flow");
    return el;
});