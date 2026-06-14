import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";

registerBlock("kv", () => {
    return createElement("div", "kv");
});