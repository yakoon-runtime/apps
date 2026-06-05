import uvicorn

uvicorn.run(
    "y5n.web.app:app",
    host="0.0.0.0",
    port=8000,
    reload=True,
)
