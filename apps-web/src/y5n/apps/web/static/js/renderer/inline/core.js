const inlineRenderers = {};

export function registerInline(type, fn) {
    inlineRenderers[type] = fn;
}

export function renderInline(inline, dispatch, regionEl) {
    const fn = inlineRenderers[inline.type];

    if (!fn) {
        return document.createTextNode("[unknown inline]");
    }

    return fn(inline, dispatch, regionEl);
}