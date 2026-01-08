"""
FFT LLM Agent - Main Game Loop
Complete the entire game from start to finish.
"""
import time
import sys
import os
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum, auto

from llm_client import LLMClient, LLMConfig
import cemuhook_server
from cemuhook_server import CemuhookServer
from frame_capture import FrameCapture
# Note: OCR removed - using Vision LLM for all text understanding
from prompt_builder import GameState, Unit, build_prompt, SYSTEM_PROMPT
from action_parser import parse_llm_response, action_to_inputs, InputExecutor

# Vision dependencies
import base64
import io
from PIL import Image

# Visual Feedback Learning (optional, requires chromadb)
try:
    from feedback_learner import FeedbackLearner
    from knowledge_store import KnowledgeStore
    HAS_FEEDBACK_LEARNING = True
except ImportError:
    HAS_FEEDBACK_LEARNING = False
    FeedbackLearner = None

# Knowledge Retrieval (RAG + Web Search)
try:
    from web_search import SmartKnowledgeRetriever
    from wiki_scraper import WikiKnowledgeStore
    HAS_KNOWLEDGE_RETRIEVAL = True
except ImportError:
    HAS_KNOWLEDGE_RETRIEVAL = False
    SmartKnowledgeRetriever = None

# Memory Reading (GDB Stub)
try:
    from memory_reader import GDBMemoryReader, GameMemoryState
    HAS_MEMORY_READER = True
except ImportError:
    HAS_MEMORY_READER = False
    GDBMemoryReader, GameMemoryState = None, None
    HAS_MEMORY_READER = False

# Strategy Advisor module
try:
    from strategy_advisor import StrategyAdvisor
    HAS_STRATEGY_ADVISOR = True
except ImportError:
    HAS_STRATEGY_ADVISOR = False
    StrategyAdvisor = None

# Strategy Learner module (tracks battle outcomes)
try:
    from strategy_learner import StrategyLearner
    HAS_STRATEGY_LEARNER = True
except ImportError:
    HAS_STRATEGY_LEARNER = False
    StrategyLearner = None


class GamePhase(Enum):
    """Current phase of the game."""
    TITLE_SCREEN = auto()
    MAIN_MENU = auto()
    WORLD_MAP = auto()
    CUTSCENE = auto()
    BATTLE_PREP = auto()
    BATTLE = auto()
    BATTLE_RESULT = auto()
    SHOP = auto()
    PARTY_MENU = auto()
    SAVE_MENU = auto()
    UNKNOWN = auto()


@dataclass
class AgentConfig:
    """Configuration for the LLM Agent."""
    # LLM settings (Gemini defaults)
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    llm_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_model: str = "gemini-2.0-flash"
    
    # Game settings
    difficulty: str = "hard"  # Easy, Normal, Hard
    auto_save: bool = True
    save_interval: int = 5  # Save every N battles
    
    # Timing
    action_delay: float = 0.2  # Delay between actions
    think_time: float = 3.0   # Min time to "think" per turn
    
    # Debug
    verbose: bool = True
    log_prompts: bool = True
    use_vision: bool = True  # Multimodal support
    
    # Capture
    window_title: str = "Eden"
    
    # GDB Memory Reading
    gdb_enabled: bool = True
    gdb_host: str = "127.0.0.1"
    gdb_port: int = 6543


def load_config_from_file() -> AgentConfig:
    """Load configuration from config.toml if available."""
    import os
    try:
        import tomli
        config_path = os.path.join(os.path.dirname(__file__), "config.toml")
        if os.path.exists(config_path):
            with open(config_path, "rb") as f:
                data = tomli.load(f)
            llm = data.get("llm", {})
            game = data.get("game", {})
            capture = data.get("capture", {})
            gdb = data.get("gdb", {})
            return AgentConfig(
                llm_base_url=llm.get("base_url", AgentConfig.llm_base_url),
                llm_api_key=llm.get("api_key", AgentConfig.llm_api_key),
                llm_model=llm.get("model", AgentConfig.llm_model),
                difficulty=game.get("difficulty", "hard"),
                window_title=capture.get("window_title", "Eden"),
                gdb_enabled=gdb.get("enabled", True),
                gdb_host=gdb.get("host", "127.0.0.1"),
                gdb_port=gdb.get("port", 6543),
            )
    except ImportError:
        pass
    return AgentConfig()


class FFTAgent:
    """
    LLM-powered agent that plays FFT from start to finish.
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        
        # Initialize components
        self.llm = LLMClient(LLMConfig(
            base_url=self.config.llm_base_url,
            api_key=self.config.llm_api_key,
            model=self.config.llm_model,
        ))
        
        # Try to start controller, or connect to existing one
        self.controller = None
        self._owns_controller = False
        try:
            self.controller = CemuhookServer()
            self._owns_controller = True
        except OSError as e:
            if "Address already in use" in str(e):
                print("\n[ERROR] Port 26760 is already in use!")
                print("Checks:")
                print("1. Is an old main.py instance running? (Kill it)")
                print("2. Is test_inputs.py running?")
                print("3. Try: lsof -i :26760 | grep Python | awk '{print $2}' | xargs kill -9")
                sys.exit(1)
            else:
                raise
        
        # Capture setup
        target_window = getattr(self.config, "window_title", "Eden")
        self.capture = FrameCapture(window_name=target_window)
        
        # No OCR - using Vision LLM for all text/phase detection
        self.executor = InputExecutor(self.controller, None, self.capture)
        
        # Visual Feedback Learning (optional)
        self.feedback_learner = None
        if HAS_FEEDBACK_LEARNING:
            try:
                self.feedback_learner = FeedbackLearner(
                    llm_client=self.llm,
                    capture_engine=self.capture
                )
                self.executor.feedback_learner = self.feedback_learner
                print(f"[Agent] Visual Feedback Learning enabled")
            except Exception as e:
                print(f"[Agent] Visual Feedback Learning disabled: {e}")
        
        # Knowledge Retrieval (RAG + Web Search)
        self.knowledge_retriever = None
        if HAS_KNOWLEDGE_RETRIEVAL:
            try:
                wiki_store = WikiKnowledgeStore()
                self.knowledge_retriever = SmartKnowledgeRetriever(knowledge_store=wiki_store)
                print(f"[Agent] Knowledge Retrieval enabled (RAG + Web Search)")
            except Exception as e:
                print(f"[Agent] Knowledge Retrieval disabled: {e}")
        
        # Memory Reader (GDB Stub)
        self.memory_reader = None
        if HAS_MEMORY_READER and self.config.gdb_enabled:
            try:
                self.memory_reader = GDBMemoryReader(
                    host=self.config.gdb_host,
                    port=self.config.gdb_port
                )
                if self.memory_reader.connect():
                    print(f"[Agent] Memory Reader enabled (GDB @ {self.config.gdb_host}:{self.config.gdb_port})")
                else:
                    print(f"[Agent] Memory Reader: Could not connect to GDB stub (will retry)")
            except Exception as e:
                print(f"[Agent] Memory Reader error: {e}")
        
        # Strategy Advisor
        self.strategy_advisor = None
        if HAS_STRATEGY_ADVISOR:
            self.strategy_advisor = StrategyAdvisor()
            print(f"[Agent] Strategy Advisor enabled")
        
        # Strategy Learner (tracks battle outcomes)
        self.strategy_learner = None
        if HAS_STRATEGY_LEARNER:
            self.strategy_learner = StrategyLearner()
            print(f"[Agent] Strategy Learner enabled")
        
        # State
        self.current_phase = GamePhase.UNKNOWN
        self.battle_count = 0
        self.running = False
        self.current_battle_record = None  # Active battle being tracked
    
    def start(self):
        """Start the agent."""
        print("Starting FFT LLM Agent...")
        print(f"LLM: {self.config.llm_model} @ {self.config.llm_base_url}")
        print(f"Difficulty: {self.config.difficulty}")
        
        if self._owns_controller:
            self.controller.start()
        self.running = True
        
        try:
            self.main_loop()
        except KeyboardInterrupt:
            print("\nStopping agent...")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the agent."""
        self.running = False
        self.controller.stop()
        self.llm.close()
    
    def main_loop(self):
        """Main game loop."""
        while self.running:
            # 1. Capture screen
            frame = self.capture.capture()
            
            # 2. Detect game phase
            self.current_phase = self.detect_phase(frame)
            
            # 3. Handle based on phase
            if self.current_phase == GamePhase.TITLE_SCREEN:
                self.handle_title_screen()
            elif self.current_phase == GamePhase.CUTSCENE:
                self.handle_cutscene()
            elif self.current_phase == GamePhase.WORLD_MAP:
                self.handle_world_map(frame)
            elif self.current_phase == GamePhase.BATTLE:
                self.handle_battle(frame)
            elif self.current_phase == GamePhase.BATTLE_RESULT:
                self.handle_battle_result()
            elif self.current_phase == GamePhase.PARTY_MENU:
                self.handle_party_menu(frame)
            elif self.current_phase == GamePhase.SHOP:
                self.handle_shop(frame)
            else:
                # Unknown state - try pressing A to advance
                self.controller.press_a()
            
            time.sleep(self.config.action_delay)
    
    def detect_phase(self, frame) -> GamePhase:
        """Detect current game phase using Vision LLM."""
        # Encode frame for vision
        
        pil_img = Image.fromarray(frame)
        if pil_img.width > 512:
            pil_img.thumbnail((512, 512))
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=70)
        img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        # Ask LLM to identify the current game phase
        prompt = """Look at this Final Fantasy Tactics screenshot and identify the current game phase.

Respond with ONLY ONE of these phases:
- TITLE_SCREEN (title menu, new game, continue, difficulty selection)
- BATTLE (combat, tactical view, turn-based battle with HP/MP visible)
- BATTLE_RESULT (victory, defeat, level up, exp gained)
- CUTSCENE (dialogue, story scenes, character talking)
- PARTY_MENU (formation, jobs, equipment, abilities menu)
- SHOP (buying or selling items)
- WORLD_MAP (ivalice map, location selection)
- UNKNOWN (cannot determine)

Just respond with the phase name, nothing else."""

        try:
            response = self.llm.chat(prompt, image_data=img_b64)
            phase_str = response.strip().upper().replace(" ", "_")
            
            if self.config.verbose:
                print(f"[Vision] Detected phase: {phase_str}")
            
            # Map to GamePhase enum
            phase_map = {
                "TITLE_SCREEN": GamePhase.TITLE_SCREEN,
                "BATTLE": GamePhase.BATTLE,
                "BATTLE_RESULT": GamePhase.BATTLE_RESULT,
                "CUTSCENE": GamePhase.CUTSCENE,
                "PARTY_MENU": GamePhase.PARTY_MENU,
                "SHOP": GamePhase.SHOP,
                "WORLD_MAP": GamePhase.WORLD_MAP,
            }
            return phase_map.get(phase_str, GamePhase.UNKNOWN)
            
        except Exception as e:
            print(f"[Vision] Phase detection error: {e}")
            return GamePhase.UNKNOWN
    
    def handle_title_screen(self):
        """Handle title screen - start new game or continue."""
        print("At title screen - starting new game...")
        # Navigate to New Game and select highest difficulty
        self.controller.press_a()  # Select New Game
        time.sleep(0.5)
        
        # Difficulty selection (The Ivalice Chronicles)
        # 1. Squire (Easy)
        # 2. Knight (Normal)
        # 3. Tactician (Hard)
        
        diff = self.config.difficulty.lower()
        if diff in ["hard", "tactician"]:
            self.controller.press_dpad('down')
            self.controller.press_dpad('down')
        elif diff in ["normal", "knight"]:
            self.controller.press_dpad('down')
            
        self.controller.press_a()
    
    def handle_cutscene(self):
        """Handle cutscenes - skip or advance dialogue."""
        print("In cutscene - advancing...")
        self.controller.press_a()
        time.sleep(0.3)
    
    def handle_world_map(self, frame):
        """Handle world map navigation."""
        print("On world map - asking LLM for destination...")
        
        prompt = """
        You are on the FFT world map. 
        What should we do next?
        
        Options:
        - Move to next story location
        - Visit shop to upgrade equipment
        - Train at random battle location
        
        Respond with:
        ACTION: <move_to_story | shop | train>
        TARGET: <location_name if known>
        REASON: <your reasoning>
        """
        
        response = self.llm.chat(prompt, SYSTEM_PROMPT)
        parsed = parse_llm_response(response)
        
        if self.config.verbose:
            print(f"LLM decision: {parsed.action} - {parsed.reason}")
        
        # Execute navigation
        # For now, just press A to enter the next available location
        self.controller.press_a()
    
    def handle_battle(self, frame):
        """Handle active battle - main tactical decision making."""
        print(f"In battle (#{self.battle_count + 1})")
        
        # Start tracking this battle if not already
        if self.strategy_learner and self.current_battle_record is None:
            # Get party composition from memory if available
            party_comp = []
            if self.memory_reader:
                mem_state = self.memory_reader.read_game_state()
                party_comp = [{"unit_id": u.unit_id, "hp": u.hp, "max_hp": u.max_hp} 
                              for u in mem_state.units if u.max_hp > 0]
            
            self.current_battle_record = self.strategy_learner.start_battle(
                map_name=f"Battle_{self.battle_count + 1}",  # Would get from screen
                party_composition=party_comp
            )
        
        # Extract game state from screen
        state = self.extract_battle_state(frame)
        
        if state.current_unit is None:
            # Not our turn, wait
            time.sleep(0.5)
            return
        
        # Pre-Visualization: Enter Move Mode to show Grid for Screenshot
        if self.config.use_vision:
            # 1. Enter Move Mode (Press A shows grid directly)
            # Assumption: Cursor is on "Move" (default)
            print("Action: Pre-visualizing movement grid...")
            viz_inputs = [
                "press:a", "wait:1.0"   # Select Move, Wait for grid
            ]
            self.executor.execute(viz_inputs)
            
            # 2. Capture new frame with Grid visible
            frame = self.capture.capture()
            
            # 3. Reset state (Back to Menu)
            # Press B (Cancel) to back out of Move mode
            cancel_inputs = ["press:b", "wait:0.5"]
            self.executor.execute(cancel_inputs)

        # Build prompt and ask LLM
        prompt = build_prompt(state)
        
        # Query knowledge base for relevant strategies (wiki + web)
        knowledge_context = ""
        if self.knowledge_retriever:
            battle_query = f"battle strategy {state.map_name}"
            knowledge_context = self.knowledge_retriever.get_knowledge_for_prompt(battle_query)
            if knowledge_context:
                prompt = knowledge_context + "\n\n" + prompt
        
        # Add self-learned button knowledge (from visual feedback)
        if self.feedback_learner:
            # Get learnings relevant to current phase
            phase_name = "battle_menu"  # or detect from OCR
            learned_context = self.feedback_learner.get_relevant_knowledge(
                button="a", game_phase=phase_name, context="selecting action in battle"
            )
            if learned_context:
                prompt = prompt + "\n\n" + learned_context
        
        # Add live memory state (HP, MP, stats from GDB)
        if self.memory_reader:
            try:
                mem_state = self.memory_reader.read_game_state()
                memory_context = self.memory_reader.format_for_llm(mem_state)
                if memory_context:
                    prompt = prompt + "\n\n" + memory_context
            except Exception as e:
                print(f"[Agent] Memory read failed: {e}")
        
        # Add Strategic Advice (using memory/RAG data)
        if self.strategy_advisor and self.memory_reader and mem_state:
             tactical_advice = self.strategy_advisor.get_tactical_plan(mem_state)
             if tactical_advice:
                 prompt = prompt + "\n\n" + tactical_advice
        
        if self.config.log_prompts:
            print(f"=== Prompt ===\n{prompt}")
        
        # Encode frame for Multimodal LLM if enabled
        img_b64 = None
        if self.config.use_vision:
            import base64
            import io
            from PIL import Image
            
            # Convert numpy to PIL
            pil_img = Image.fromarray(frame)
            if pil_img.width > 1024:
                pil_img.thumbnail((1024, 1024))
                
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=80)
            img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        response = self.llm.chat(prompt, SYSTEM_PROMPT, image_data=img_b64)
        
        if self.config.log_prompts:
            print(f"=== LLM Response ===\n{response}")
        
        # Parse and execute action
        parsed = parse_llm_response(response)
        current_pos = (state.current_unit.x, state.current_unit.y)
        inputs = action_to_inputs(parsed, current_pos)
        
        print(f"Executing: {parsed.action} -> {parsed.target}")
        self.executor.execute(inputs)
        
        # Log action for learning
        if self.strategy_learner and self.current_battle_record:
            action_str = f"{parsed.action} -> {parsed.target}"
            self.strategy_learner.log_action(self.current_battle_record, action_str)
        
        time.sleep(self.config.think_time)
    
    def extract_battle_state(self, frame) -> GameState:
        """Extract battle state using Vision LLM."""
        # The LLM sees the full screen in handle_battle(), so we just need
        # to determine if it's our turn (command menu visible)
        
        # For efficiency, we do a quick LLM check for turn status
        
        pil_img = Image.fromarray(frame)
        if pil_img.width > 512:
            pil_img.thumbnail((512, 512))
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=70)
        img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        prompt = """Is this a player's turn in FFT? Look for:
- Command menu visible (Move, Act, Wait, Status)
- HP/MP display for active unit
- Cursor/hand indicator

Respond with ONLY: YES or NO"""

        try:
            response = self.llm.chat(prompt, image_data=img_b64)
            is_our_turn = "YES" in response.upper()
            
            if not is_our_turn:
                return GameState(current_unit=None, valid_actions=[])
            
            # It's our turn - create basic state
            # The detailed analysis is done in handle_battle() with full LLM
            return GameState(
                current_unit=Unit(
                    name="Active Unit", 
                    job="Unknown",
                    x=0, y=0,
                    hp=100, max_hp=100,
                    mp=50, max_mp=50,
                ),
                valid_actions=["Move", "Act", "Wait", "Status"]
            )
            
        except Exception as e:
            print(f"[Vision] Turn detection error: {e}")
            return GameState(current_unit=None, valid_actions=[])
    
    def handle_battle_result(self):
        """Handle battle victory/defeat screen."""
        print("Battle ended!")
        self.battle_count += 1
        
        # Record battle outcome if learning is enabled
        if self.strategy_learner and self.current_battle_record:
            # TODO: Detect victory/defeat from screen (for now assume victory if we got here)
            # In a real implementation, use OCR or LLM vision to detect "Victory" vs "Defeat"
            victory = True  # Placeholder - would detect from screen
            turns = len(self.current_battle_record.actions_taken)
            units_lost = 0  # Would count from memory state
            
            self.strategy_learner.end_battle(
                self.current_battle_record, 
                victory=victory, 
                turns=turns, 
                units_lost=units_lost
            )
            self.current_battle_record = None
        
        # Press A to advance through results
        for _ in range(5):
            self.controller.press_a()
            time.sleep(0.3)
        
        # Auto-save if enabled
        if self.config.auto_save and self.battle_count % self.config.save_interval == 0:
            print(f"Auto-saving after {self.battle_count} battles...")
    
    def handle_party_menu(self, frame):
        """Handle party management - jobs, abilities, equipment."""
        print("In party menu - asking LLM for advice...")
        
        prompt = """
        You are in the FFT party menu. 
        Should we change any jobs, learn abilities, or adjust equipment?
        
        Respond with:
        ACTION: <change_job | learn_ability | equip | exit>
        TARGET: <unit_name>
        DETAIL: <what to change>
        REASON: <why>
        """
        
        response = self.llm.chat(prompt, SYSTEM_PROMPT)
        parsed = parse_llm_response(response)
        
        if self.config.verbose:
            print(f"Party decision: {parsed.action}")
        
        # For now, just exit the menu
        self.controller.press_b()
    
    def handle_shop(self, frame):
        """Handle shop - buy equipment."""
        print("In shop - asking LLM what to buy...")
        
        prompt = """
        You are in a shop in FFT.
        What should we buy/sell?
        
        Priorities:
        1. Upgrade weapons for main damage dealers
        2. Better armor for front-line units
        3. Accessories that boost speed/evasion
        
        Respond with:
        ACTION: <buy | sell | exit>
        TARGET: <item_name>
        REASON: <why>
        """
        
        response = self.llm.chat(prompt, SYSTEM_PROMPT)
        parsed = parse_llm_response(response)
        
        if parsed.action == "exit":
            self.controller.press_b()
        else:
            # Execute purchase
            self.controller.press_a()


def main():
    """Entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="FFT LLM Agent")
    parser.add_argument("--llm-url", help="Override LLM API URL")
    parser.add_argument("--llm-model", help="Override LLM model name")
    parser.add_argument("--difficulty", choices=["easy", "normal", "hard"])
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--no-vision", action="store_true", help="Disable multimodal vision")
    
    args = parser.parse_args()
    
    # Load from config.toml first, then override with CLI args
    config = load_config_from_file()
    
    if args.llm_url:
        config.llm_base_url = args.llm_url
    if args.llm_model:
        config.llm_model = args.llm_model
    if args.difficulty:
        config.difficulty = args.difficulty
    if args.verbose:
        config.verbose = True
    if args.no_vision:
        config.use_vision = False
    
    agent = FFTAgent(config)
    agent.start()


if __name__ == "__main__":
    main()
