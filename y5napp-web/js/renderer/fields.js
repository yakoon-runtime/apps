import { createElement, findRegion } from "../dom.js"
import { Renderer } from "./renderer.js";

export function renderFields(node, dispatch, container) {

    if (node.props.name) {
        container.dataset.scope = node.props.name;
    }

    for (const field of node.props.fields || []) {

        const fieldBlock = createElement("div", "field-block");
        const row = createElement("div", "field-row");

        const label = createElement("label", "field-label");
        label.textContent = field.title || field.var || "";

        const inputWrap = createElement("div", "field-wrap");

        const input = createElement("input", "field-input");
        input.name = field.name;
        input.value = field.query ?? field.default ?? "";
        input.placeholder = field.hint || "";

        const region = createElement("div", "field-region");
        region.dataset.regionId = "r-" + crypto.randomUUID();

        inputWrap.appendChild(input);

        if (field.lookup) {
            const icon = createElement("button", "field-lookup");
            icon.textContent = "▾";

            icon.onclick = () => {
                const renderer = Renderer.from(region);
                if (!renderer) return;
                renderer.openInteraction(region, field.lookup);
            };

            inputWrap.appendChild(icon);
        }

        row.appendChild(label);
        row.appendChild(inputWrap);

        fieldBlock.appendChild(row);
        fieldBlock.appendChild(region);

        container.appendChild(fieldBlock);
    }
}