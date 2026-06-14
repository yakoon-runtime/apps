import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";

registerBlock("list", () => {
    return createElement("ul", "list");
});