const blockRenderers = {};

export function registerBlock(type, fn) {
    blockRenderers[type] = fn;
}

export function renderBlock(node, dispatch, renderer) {
    const fn = blockRenderers[node.type];

    if (!fn) {
        return document.createElement("div");
    }

    return fn(node, dispatch, renderer);
}