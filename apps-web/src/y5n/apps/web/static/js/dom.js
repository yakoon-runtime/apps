// ----------
// PUBLIC API
// ----------

export function createElement(tag, className) {
    const el = document.createElement(tag);
    if (className) el.classList.add(className);
    return el;
}

export function findRegion(el) {
    if (!(el instanceof Element)) {
        return null;
    }
    return el.closest("[data-region-id]");
}

export function findScope(el, scopeName) {

    if (!scopeName) {
        throw new Error("Action requires scope");
    }

    // lokal im aktuellen Render-Kontext suchen
    const renderer = el.closest('[data-renderer="true"]');
    if (!renderer) {
        throw new Error("Renderer root not found");
    }

    const scope = renderer.querySelector(
        `[data-scope="${scopeName}"]`
    );
    if (!scope) {
        throw new Error(`Scope not found: ${scopeName}`);
    }

    return scope;
}