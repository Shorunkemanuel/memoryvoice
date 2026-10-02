from fastapi import FastAPI

app = FastAPI(title="MemoryVoice Backend")

@app.get("/health")
def health_check():
    return {"status": "ok"}
