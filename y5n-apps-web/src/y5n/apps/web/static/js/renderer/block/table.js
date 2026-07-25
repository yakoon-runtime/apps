import { registerBlock } from "./core.js";

registerBlock("table", (node) => {
    const table = document.createElement("table");
    table.classList.add("table");

    const columns = node.props.columns || [];

    if (columns.length > 0) {
        const thead = document.createElement("thead");
        const tr = document.createElement("tr");
        for (const col of columns) {
            const th = document.createElement("th");
            th.textContent = col.title || col.key || "";
            tr.appendChild(th);
        }
        thead.appendChild(tr);
        table.appendChild(thead);
    }

    const tbody = document.createElement("tbody");
    for (const row of node.props.rows || []) {
        const tr = document.createElement("tr");
        for (let i = 0; i < row.length; i++) {
            const td = document.createElement("td");
            td.textContent = row[i];
            tr.appendChild(td);
        }
        tbody.appendChild(tr);
    }
    table.appendChild(tbody);

    return table;
});
