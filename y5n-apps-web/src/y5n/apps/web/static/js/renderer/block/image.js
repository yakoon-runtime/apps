import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";

registerBlock("image", (node) => {
    const img = createElement("img");

    img.classList.add("image");

    img.src = node.props.src;

    if (node.props.alt) {
        img.alt = node.props.alt;
    }

    return img;
});