// ----------
// PUBLIC API
// ----------

export function collectFields(root) {

    const data = {};

    const inputs = root.querySelectorAll("[name]");

    for (const input of inputs) {

        const value = input.value;

        if (value == null || value === "") continue;

        data[input.name] = value;
    }

    return data;
}

export function buildCommand(base, data) {

    const args = [];

    for (const [key, value] of Object.entries(data)) {
        args.push(`--${key}`, quote(value));
    }

    return [base, ...args].join(" ");
}

// ----------
// INTERNALS
// ----------

function quote(value) {
    const str = String(value);

    if (!/\s/.test(str)) return str;

    return `"${str.replace(/"/g, '\\"')}"`;
}

