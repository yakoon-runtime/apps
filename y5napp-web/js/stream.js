
const DEFAULT_RUNTIME = "ws://localhost:9100";

function getRuntimeUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("runtime") || DEFAULT_RUNTIME;
}

export function createWS(onProjection) {
    const url = getRuntimeUrl();
    const ws = new WebSocket(url);

    ws.onopen = () => {
        ws.send(JSON.stringify({ type: "connect" }));
    };

    ws.onmessage = (msg) => {
        const data = JSON.parse(msg.data);

        if (data.type === "projection") {
            onProjection(data.payload);
        }
    };

    return ws;
}
