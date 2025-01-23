# -*- coding: utf-8 -*-
# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
## Setup

To install the dependencies for this script, run:

``` 
pip install google-genai opencv-python pyaudio pillow mss
```

Before running this script, ensure the `GOOGLE_API_KEY` environment
variable is set to the api-key you obtained from Google AI Studio.

Important: **Use headphones**. This script uses the system default audio
input and output, which often won't include echo cancellation. So to prevent
the model from interrupting itself it is important that you use headphones. 

## Run

To run the script:

```
python live_api_starter.py
```

The script takes a video-mode flag `--mode`, this can be "camera", "screen", or "none".
The default is "camera". To share your screen run:

```
python live_api_starter.py --mode screen
```
"""

import asyncio
import base64
import io
import os
import sys
import traceback
import time

import cv2
import pyaudio
import PIL.Image
import mss

import argparse

from google import genai

# Backports for Python < 3.11
if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup

    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

# Audio constants
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000        # fps : frames per second 
RECEIVE_SAMPLE_RATE = 24000     # fps : frames per second
CHUNK_SIZE = 1024

# Model and mode settings
MODEL = "models/gemini-2.0-flash-exp"
DEFAULT_MODE = "camera"
#system_instruction = "You're an expert psychologist, you talk in a calm and peaceful demeanor, your goal is to understand (deeply) about user's problems and solve them. You ask questions (if you're unsure) to understand user's problem deeply. You provide detailed, clear and concise answers without leaving any room for ambiguity. Please introduce yourself (nicely!) and ask the user how they're feeling today."
system_instruction = "You're an expert assistant, you work by the principles of scientific method, you're curious, you ask questions to understand user's problem deeply. You provide detailed, clear and concise answers without leaving any room for ambiguity. Please introduce yourself (nicely!) and ask the user how they're feeling today."
# Create a genai client (ensure GOOGLE_API_KEY is set)
client = genai.Client(
    api_key=os.environ["GOOGLE_API_KEY"],
    http_options={"api_version": "v1alpha"},
)

# Request AUDIO responses from the model
if system_instruction != None:
    CONFIG = {"tools": [{'google_search': {}}], "generation_config": {"response_modalities": ["AUDIO"], "system_instruction": system_instruction}}
else:
    CONFIG = {"tools": [{'google_search': {}}], "generation_config": {"response_modalities": ["AUDIO"]}}

pya = pyaudio.PyAudio()


def print_greeting_and_instructions():
    """
    Prints a warm greeting (ASCII art) and concise instructions on how to use this application.
    """
    ascii_art = r"""
       /\                             *    .  
      /**\          *       .    *        .   
     /****\   *            .         .  *     
    /      \       .   *    *   .             
   /  /\    \                 .    .    *      
  /  /  \    \    *    .           *          
 /  /    \    \            *                  
/__/      \____\      G E M I N I - 2 . 0           
                                             
              L I V E -  D E M O        
"""

    print(ascii_art)
    print("=" * 60)
    print("WELCOME to the GEMINI-DEMO!")
    print(" ")
    print("Capabilities:")
    print(" • The model accepts *audio* (from your microphone) and text.")
    print(" • The model responds with *audio only* in real-time.")
    print(" ")
    print("Usage Instructions:")
    print(" 1. Wear headphones to avoid echo or feedback loops.")
    print(" 2. Type your message after the prompt `message > `.")
    print(" 3. Press ENTER to send it to the model.")
    print(" 4. Type 'q' and press ENTER to end the session.")
    print(" ")
    print("Additional Details:")
    print(" • Default video mode: camera.")
    print(" • Use `--mode screen` to share your screen.")
    print(" • Use `--mode none` to disable video/screen sharing.")
    print("=" * 60)
    print("\nSession starting... Have fun!\n")


class AudioLoop:
    def __init__(self, video_mode=DEFAULT_MODE):
        self.video_mode = video_mode
        
        self.audio_in_queue = None
        self.out_queue = None
        self.session = None

        # Track stats
        self.user_message_count = 0  # number of messages user typed
        self.start_time = None

    async def send_text(self):
        """
        Continuously reads text from the user and sends it to the AI session.
        We also increment user_message_count each time the user sends a message.
        """
        while True:
            # Show prompt on a fresh line to avoid interruption:
            text = await asyncio.to_thread(input, "\nmessage > ")
            if text.lower() == "q":
                break

            # Count only actual user messages (ignore empty string).
            if text.strip():
                self.user_message_count += 1

            await self.session.send(text or ".", end_of_turn=True)

    def _get_frame(self, cap):
        """Captures a single frame from camera, resizes, encodes, returns dict."""
        ret, frame = cap.read()
        if not ret:
            return None
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(frame_rgb)
        img.thumbnail([1024, 1024])

        image_io = io.BytesIO()
        img.save(image_io, format="jpeg")
        image_io.seek(0)

        mime_type = "image/jpeg"
        image_bytes = image_io.read()
        return {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}

    async def get_frames(self):
        """Continuously captures frames from the default camera."""
        cap = await asyncio.to_thread(cv2.VideoCapture, 0)
        while True:
            frame = await asyncio.to_thread(self._get_frame, cap)
            if frame is None:
                break
            await asyncio.sleep(1.0)
            await self.out_queue.put(frame)
        cap.release()

    def _get_screen(self):
        """Captures the entire screen as a screenshot, returns dict."""
        sct = mss.mss()
        monitor = sct.monitors[0]
        i = sct.grab(monitor)

        mime_type = "image/jpeg"
        image_bytes = mss.tools.to_png(i.rgb, i.size)
        img = PIL.Image.open(io.BytesIO(image_bytes))

        image_io = io.BytesIO()
        img.save(image_io, format="jpeg")
        image_io.seek(0)

        image_bytes = image_io.read()
        return {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}

    async def get_screen(self):
        """Continuously captures screenshots every ~1 second."""
        while True:
            frame = await asyncio.to_thread(self._get_screen)
            if frame is None:
                break
            await asyncio.sleep(1.0)
            await self.out_queue.put(frame)

    async def send_realtime(self):
        """Sends frames or mic-audio data from out_queue to the AI session."""
        while True:
            msg = await self.out_queue.get()
            await self.session.send(msg)

    async def listen_audio(self):
        """Captures mic audio in real-time, sends it to the AI session."""
        mic_available, mic_info = check_audio_input()
        if not mic_available:
            pass
        self.audio_stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=mic_info["index"],
            frames_per_buffer=CHUNK_SIZE,
        )
        if __debug__:
            kwargs = {"exception_on_overflow": False}
        else:
            kwargs = {}

        while True:
            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
            await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})      # sends data in uncompressed binary format. pcm : pulse control modulation. 

    async def receive_audio(self):
        """
        Receives audio bytes from the AI and puts them into audio_in_queue for playback.
        Also prints the model's text, but in this application, the model output is Audio Only.
        We insert a line-break before printing to avoid overwriting the user's prompt.
        """
        while True:
            turn = self.session.receive()
            async for response in turn:
                # If there's audio data, queue it for playback
                if data := response.data:
                    self.audio_in_queue.put_nowait(data)
                    continue

                # If there's text, print it on a new line (not typical in this example,
                # but left here if the model occasionally produces text).
                if text := response.text:
                    print("\n[Model Text]:", text)

            # If the model's turn completes, clear any unplayed audio data.
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()

    async def play_audio(self):
        """
        Plays back the model's audio output in real-time.
        Displays a note that audio is being received and played.
        """
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        while True:
            bytestream = await self.audio_in_queue.get()
            # Let the user know we’re receiving/playing model audio
            await asyncio.to_thread(stream.write, bytestream)

    def print_session_summary(self):
        """
        Prints session duration, number of user messages, and a friendly goodbye message.
        """
        end_time = time.time()
        elapsed_seconds = round(end_time - self.start_time, 2)
        print("\n" + "=" * 60)
        print("SESSION SUMMARY")
        print(f" • Duration: {elapsed_seconds} seconds")
        print(f" • Number of messages you sent: {self.user_message_count}")
        print("Thanks for trying the GEMINI-DEMO! Have a great day!")
        print("=" * 60 + "\n")

    async def run(self):
        try:
            self.start_time = time.time()  # Start timing the session

            async with (
                client.aio.live.connect(model=MODEL, config=CONFIG) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session

                # Queues for inbound/outbound data
                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue(maxsize=5)

                # Start tasks
                tg.create_task(self.send_realtime())
                tg.create_task(self.listen_audio())

                if self.video_mode == "camera":
                    tg.create_task(self.get_frames())
                elif self.video_mode == "screen":
                    tg.create_task(self.get_screen())

                tg.create_task(self.receive_audio())
                tg.create_task(self.play_audio())

                # We await send_text so that if user types 'q', the session closes gracefully
                send_text_task = tg.create_task(self.send_text())
                await send_text_task

                # Raise CancelledError to break out of TaskGroup on user exit
                raise asyncio.CancelledError("User requested exit")

        except asyncio.CancelledError:
            pass
        except ExceptionGroup as EG:
            # In case of grouped exceptions
            self.audio_stream.close()
            traceback.print_exception(EG)
        finally:
            # Print session summary
            self.print_session_summary()
            # Clean up audio devices if not already closed
            if hasattr(self, "audio_stream"):
                self.audio_stream.close()


def check_audio_input():
    """Check if a valid audio input device is available"""
    try:
        mic_info = pya.get_default_input_device_info()
        return True, mic_info
    except Exception:
        print("\n⚠️  No microphone detected!")
        print("Please connect headphones with a microphone to use this application.")
        print("Some built-in microphones may not be supported by PyAudio.")
        print("💡 Tip: Most USB/Bluetooth headphones should work fine.\n")
        return False, None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        type=str,
        default=DEFAULT_MODE,
        choices=["camera", "screen", "none"],
        help="Options: 'camera' to use webcam, 'screen' to capture screen, 'none' for no video feed.",
    )
    args = parser.parse_args()

    # Print a greeting and usage instructions
    print_greeting_and_instructions()

    main = AudioLoop(video_mode=args.mode)
    asyncio.run(main.run())
