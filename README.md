# Gemini Real-Time Web Demo

A web-based demo implementing Google's Gemini real-time streaming API for interactive audio conversations. This project explores the capabilities of Gemini's real-time audio features in a web context.

## Project Overview

This implementation converts Google's original CLI-based demo into a web application, allowing for:
- Real-time audio streaming to/from Gemini
- Text-based interactions
- Push-to-talk functionality
- Volume controls and mute options

## Technical Architecture

### Frontend
- Web Audio API for audio capture and playback
- AudioWorklet for sample rate conversion and streaming
- WebSocket for real-time communication

### Backend
- FastAPI server handling WebSocket connections
- Integration with Gemini's real-time API
- Audio format conversion and streaming

## Setup and Installation

1. Clone the repository
2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   ```bash
   # On Unix/macOS:
   export GOOGLE_API_KEY=your_api_key_here

   # On Windows:
   set GOOGLE_API_KEY=your_api_key_here
   ```
   
   Alternatively, create a `.env` file:
   ```bash
   GOOGLE_API_KEY=your_api_key_here
   ```

5. Run the web app:
   ```bash
   uvicorn backend:app --reload
   ```

6. Open your browser and navigate to:
   ```
   http://localhost:8000
   ```

## Current Status

The application is functional with these features:
- Real-time audio conversations
- Text input/output
- Push-to-talk functionality
- Volume control and mute options
- Keyboard shortcuts

### Known Issues
- Occasional audio disruptions during playback (approximately 1 in 4 responses)
- Buffer management needs optimization for varying chunk sizes
- Initial buffering strategy needs improvement

## Planned Improvements

### UI Enhancements
1. Visual Feedback
   - Audio visualization
   - Speaking indicators
   - Connection status improvements

2. Conversation UI
   - Chat-like interface
   - Message history
   - Timestamps

3. Controls
   - Enhanced push-to-talk
   - Better volume controls
   - Session management

4. Accessibility
   - Screen reader support
   - Keyboard navigation
   - High contrast mode

### Technical Improvements
- Better buffer management for audio streaming
- Enhanced error recovery
- Performance optimizations
- Network stability improvements

## Credits

- Backend integration logic and original CLI implementation by [Google's Gemini Team](https://github.com/google/generative-ai-python)
- Web implementation assistance by [Claude 3.5 Sonnet](https://www.anthropic.com/claude)
- Audio streaming optimizations by [GitHub Copilot](https://github.com/features/copilot)

## License

This project is intended for demonstration purposes. All Gemini-related components are subject to Google's terms and conditions.
