import { registerInline } from "./core.js";

registerInline("text", (inline) => {
    return document.createTextNode(inline.text);
});