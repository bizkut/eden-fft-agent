# Eden LLM Agent for Final Fantasy Tactics: The Ivalice Chronicles

A vision-based autonomous agent that plays *Final Fantasy Tactics: The Ivalice Chronicles* (Nintendo Switch) using the Eden Emulator.

## 🧠 Core Features
- **Vision-Only Perception**: Uses `GLM-4V` (or other Vision LLMs) to "see" the screen. No memory hacking or OCR dependency.
- **Self-Learning**: Observes visual feedback (e.g., "Pressing A opened a menu") and learns mechanics dynamically.
- **RAG Knowledge Base**: Integrated wiki knowledge (50+ battle guides, job data) for tactical decision making.
- **Platform Agnostic**: Uses standard macOS window capture and Cemuhook UDP protocol. Works with any UDP-compatible emulator.

## 🛠️ Setup

1. **Install Dependencies**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure Emulator**
   - Use **Eden Emulator** (Yuzu Fork).
   - Enable "Cemuhook UDP Server" in settings (Port 26760).
   - Ensure the game window title contains "Eden" or "FFT".

3. **Ingest Knowledge (Optional)**
   The repo comes with pre-trained knowledge (`knowledge_db/`), but you can scrape fresh guides:
   ```bash
   python wiki_scraper.py --all
   ```

## 🚀 Usage

Run the agent:
```bash
python main.py
```

## 📁 Architecture
- `main.py`: Core game loop and LLM decision making.
- `llm_client.py`: Handles vision API requests.
- `feedback_learner.py`: Visual learning system.
- `knowledge_store.py`: Vector DB (ChromaDB) for RAG.
- `action_parser.py`: Translates LLM thoughts to controller inputs.
