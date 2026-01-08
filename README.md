# Eden LLM Agent for Final Fantasy Tactics: The Ivalice Chronicles

<div align="center">

**A Vision-Language Autonomous Agent for Nintendo Switch**
*Plays Final Fantasy Tactics using Multimodal AI + Direct Memory Access*

</div>

## 📖 Overview

This agent is an autonomous player for *Final Fantasy Tactics: The Ivalice Chronicles* (Nintendo Switch), running on the **Eden Emulator**. It combines state-of-the-art **Vision LLMs** (like GLM-4V) to "see" the game screen with **direct memory reading** (via GDB) to understand precise game states (HP, MP, Stats).

Unlike traditional bots that rely 100% on hard-coded logic or 100% on visual approximations, Eden Agent uses a hybrid approach:
1.  **Vision**: Understands menus, map geometry, and complex situational context.
2.  **Memory**: Reads exact unit stats, job IDs, and active effects for tactical precision.
3.  **RAG Knowledge**: Consults a database of 50+ wiki guides for battle strategies and builds.

## ✨ Key Features

-   **🧠 Multimodal Perception**: Uses Vision-Language Models to parse the game screen (menus, battle maps, dialogue).
-   **💾 GDB Memory Integration**: Connects to Eden's GDB stub to read live stats (HP/MP, Brave/Faith, Speed) without "cheating" (read-only by default).
-   **📚 Tactical Knowledge Base**: Retrieval-Augmented Generation (RAG) system containing comprehensive game knowledge.
-   **🎮 Platform Agnostic**: Optimised for Eden (Yuzu fork) but compatible with any emulator supporting Cemuhook UDP and GDB protocols.
-   **🔧 Highly Configurable**: Customize Difficulty, Model parameters, and Capture settings via `config.toml`.

## 🛠️ System Requirements

-   **OS**: macOS (optimized for Apple Silicon) or Linux/Windows (with Python environment).
-   **Emulator**: **Eden Emulator** (or compatible Yuzu/Ryujinx fork).
-   **ROM**: *Final Fantasy Tactics: The Ivalice Chronicles* (Switch).
-   **Python**: 3.10+.

## 🚀 Setup Guide

### 1. Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/bizkut/eden-fft-agent.git
cd eden-fft-agent

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 2. Emulator Configuration

1.  Open **Eden Emulator**.
2.  Go to **Configuration > Network**.
3.  Enable **Cemuhook UDP Server** (Default Port: `26760`).
4.  Enable **GDB Debug Stub** (Default Port: `6543`).

### 3. Agent Configuration

Edit `config.toml` to match your setup:

```toml
[capture]
window_title = "Eden"  # Matches your emulator window title

[gdb]
enabled = true
host = "127.0.0.1"
port = 6543

[llm]
model = "zai-org/glm-4.6v-flash"  # Your Vision LLM
base_url = "http://localhost:1234/v1" 
```

## 🎮 Usage

1.  **Launch the Game** in Eden Emulator.
2.  **Start the Agent**:
    ```bash
    python main.py
    ```
3.  **Monitor Progress**: The agent will print its "thoughts" and actions to the console.

> **Note**: To inspect the memory reader separately:
> ```bash
> python memory_reader.py
> ```
> This will print the current party stats directly from memory.

## 🏗️ Architecture

```mermaid
graph TD
    Game[FFT (Eden Emulator)] -->|Screen Capture| Vision[Frame Capture]
    Game -->|GDB Protocol| Memory[Memory Reader]
    
    Vision --> Agent
    Memory --> Agent
    
    RAG[Knowledge DB] --> Agent
    
    Agent -->|Prompt + Image| LLM[Vision LLM]
    LLM -->|Decision| Agent
    
    Agent -->|Controller Input| UDP[Cemuhook Client]
    UDP --> Game
```

-   **`main.py`**: The central brain. Orchestrates the game loop, combines inputs, and executes actions.
-   **`memory_reader.py`**: Implements the GDB Remote Serial Protocol to parse unit structs from RAM.
-   **`frame_capture.py`**: High-performance window capture using macOS Quartz (or fallback).
-   **`knowledge_store.py`**: Vector database for retrieving strategy guides.

## 🧠 Strategic Intelligence

The agent now includes a sophisticated strategic layer:

### 🛡️ Strategy Advisor
An intelligent module (`strategy_advisor.py`) that:
- **Analyzes Party Health**: Detects critical units and resource shortages.
- **Identifies Roles**: Determines if units are Physical or Magic/Support.
- **Sets Battle Modes**: Switches between **OFFENSIVE**, **DEFENSIVE**, and **EMERGENCY RECOVERY** based on battle state.

### 📚 Learning System
A self-improving system (`strategy_learner.py`) that:
- **Tracks History**: Records every battle outcome (Victory/Defeat, Turns, Units Lost).
- **Learns Patterns**: Identifies difficult maps based on win rates.
- **Adapts Tactics**: Provides historical advice (e.g., *"We lost here twice, play defensively"*).

### ⚡ Power-Up System (Optional)
An optional helper (`power_manager.py`) enabled via `cheats_enabled = true` in config:
- Can **Heal** or **Revive** units in emergencies.
- Can **Buff** Brave/Faith stats via memory writes.

## 🤝 Contributing

Contributions are welcome! We are currently working on:
-   **Video Streaming**: Native HTTP streaming from Eden (C++ mod).
-   **Auto-Save/State Management**: Robust handling of save states.

## 📄 License

MIT License. See `LICENSE` for details.
