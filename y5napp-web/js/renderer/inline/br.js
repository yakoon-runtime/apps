import { registerInline } from "./core.js";

registerInline("break", () => {
    return document.createElement("br");
});