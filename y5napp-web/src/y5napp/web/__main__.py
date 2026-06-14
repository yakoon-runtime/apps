import uvicorn

uvicorn.run(
    "y5napp.web.app:app",
    host="127.0.0.1",
    port=8000,
)
