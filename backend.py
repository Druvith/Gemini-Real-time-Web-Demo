import os
import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from google import genai

# Environment / Config
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("Missing GOOGLE_API_KEY environment variable.")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

# Gemini Config
MODEL = "models/gemini-2.0-flash-exp"
system_instruction = (
    "You're an expert assistant, you work by the principles of scientific method, "
    "you're curious, you ask questions to understand the user's problem deeply. "
    "You provide detailed, clear and concise answers without leaving any room for ambiguity. "
    "Please introduce yourself (nicely!) and ask the user how they're feeling today."
)
CONFIG = {
    "tools": [{"google_search": {}}],
    "generation_config": {
        "response_modalities": ["AUDIO"],
        "system_instruction": system_instruction,
    },
}

# Google GENAI client
client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={"api_version": "v1alpha"},
)

# Audio Specs
SEND_SAMPLE_RATE = 16000    # Browser -> Server -> Gemini
RECEIVE_SAMPLE_RATE = 24000 # Gemini -> Server -> Browser

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("[Server] WebSocket connected from client.")
    current_response = None

    await websocket.send_text("ACK:SERVER_READY")

    async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:
        print("[Server] Gemini session started.")

        async def from_client():
            try:
                while True:
                    pkt = await websocket.receive()
                    if "text" in pkt:
                        text_msg = pkt["text"]
                        if text_msg.startswith("TEXT:"):
                            user_text = text_msg[5:].strip()
                            print(f"[Server] Received TEXT: {user_text}")
                            # Don't try to close previous turn, just send new message
                            await session.send(user_text, end_of_turn=True)
                        elif text_msg.startswith("ACK:"):
                            print(f"[Server] Received ACK from client: {text_msg}")
                        else:
                            print(f"[Server] Unknown text message: {text_msg}")
                    elif "bytes" in pkt:
                        audio_bytes = pkt["bytes"]
                        if len(audio_bytes) == 0:
                            continue
                        print(f"[Server] Received {len(audio_bytes)} bytes of PCM")
                        await session.send({
                            "mime_type": "audio/pcm",
                            "data": audio_bytes
                        }, end_of_turn=True)
            except WebSocketDisconnect:
                print("[Server] Client disconnected.")
            except Exception as e:
                print(f"[Server] Error in from_client: {e}")
                raise  # Re-raise to see full traceback

        async def from_gemini():
            try:
                while True:
                    async for response in session.receive():
                        if response.data:
                            raw_audio = response.data
                            print(f"[Server] Sending {len(raw_audio)} bytes of PCM")
                            await websocket.send_bytes(b"AUDIO:" + raw_audio)
                        if response.text:
                            print(f"[Server] Sending TEXT: {response.text}")
                            await websocket.send_text("TEXT:" + response.text)
            except Exception as e:
                print(f"[Server] Error in from_gemini: {e}")
                raise  # Re-raise to see full traceback

        client_task = asyncio.create_task(from_client())
        gemini_task = asyncio.create_task(from_gemini())

        done, pending = await asyncio.wait(
            [client_task, gemini_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()

    print("[Server] Gemini session closed. WebSocket endpoint done.")
    await websocket.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)