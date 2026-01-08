"""
Visual Feedback Learner for FFT Agent.
Captures before/after screenshots of button presses and uses LLM to analyze effects.
"""
import os
import time
from typing import Optional, Tuple
from dataclasses import dataclass
import base64
import io

try:
    from PIL import Image
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from knowledge_store import KnowledgeStore, ActionLearning


@dataclass
class CapturedAction:
    """A captured action with before/after states."""
    button: str
    game_phase: str
    before_frame: "np.ndarray"
    after_frame: "np.ndarray"
    timestamp: float


class FeedbackLearner:
    """
    Captures visual feedback from button presses and learns effects.
    Uses LLM vision to analyze before/after screenshots.
    """
    
    def __init__(
        self,
        llm_client,
        capture_engine,
        knowledge_store: Optional[KnowledgeStore] = None,
        save_frames: bool = True,
        frames_dir: str = "./captured_frames"
    ):
        if not HAS_PIL:
            raise ImportError("Pillow required: pip install pillow")
        
        self.llm = llm_client
        self.capture = capture_engine
        self.knowledge = knowledge_store or KnowledgeStore()
        self.save_frames = save_frames
        self.frames_dir = frames_dir
        
        if save_frames:
            os.makedirs(frames_dir, exist_ok=True)
        
        # Current capture state
        self._before_frame: Optional["np.ndarray"] = None
        self._before_phase: str = "unknown"
        self._action_start: float = 0.0
    
    def capture_before(self, game_phase: str = "unknown"):
        """Capture the screen state BEFORE a button press."""
        self._before_frame = self.capture.capture()
        self._before_phase = game_phase
        self._action_start = time.time()
    
    def capture_after_and_learn(self, button: str) -> Optional[ActionLearning]:
        """
        Capture the screen state AFTER a button press and learn the effect.
        Returns the learning or None if before wasn't captured.
        """
        if self._before_frame is None:
            print("[FeedbackLearner] Warning: No before frame captured")
            return None
        
        after_frame = self.capture.capture()
        
        # Analyze the difference using LLM vision
        learning = self._analyze_and_learn(
            button=button,
            game_phase=self._before_phase,
            before_frame=self._before_frame,
            after_frame=after_frame
        )
        
        # Reset state
        self._before_frame = None
        self._before_phase = "unknown"
        
        return learning
    
    def _frame_to_base64(self, frame: "np.ndarray", max_size: int = 512) -> str:
        """Convert numpy frame to base64 JPEG string."""
        img = Image.fromarray(frame)
        
        # Resize if too large
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    
    def _save_frame(self, frame: "np.ndarray", prefix: str) -> str:
        """Save frame to disk and return path."""
        timestamp = int(time.time() * 1000)
        filename = f"{prefix}_{timestamp}.jpg"
        path = os.path.join(self.frames_dir, filename)
        
        img = Image.fromarray(frame)
        img.save(path, quality=90)
        
        return path
    
    def _analyze_and_learn(
        self,
        button: str,
        game_phase: str,
        before_frame: "np.ndarray",
        after_frame: "np.ndarray"
    ) -> ActionLearning:
        """Use LLM to analyze before/after frames and create learning."""
        
        # Save frames if enabled
        before_path = None
        after_path = None
        if self.save_frames:
            before_path = self._save_frame(before_frame, f"before_{button}")
            after_path = self._save_frame(after_frame, f"after_{button}")
        
        # Convert to base64 for LLM
        before_b64 = self._frame_to_base64(before_frame)
        after_b64 = self._frame_to_base64(after_frame)
        
        # Ask LLM to analyze the difference
        prompt = f"""Analyze these two game screenshots. The first is BEFORE pressing the '{button}' button, the second is AFTER.

BEFORE pressing '{button}':
[First image attached]

AFTER pressing '{button}':
[Second image attached]

Describe:
1. CONTEXT: What was shown before? (menu state, cursor position, etc.)
2. EFFECT: What changed after pressing '{button}'? Be specific about visual changes.
3. LEARNING: What does this teach about what the '{button}' button does in this situation?

Format your response as:
CONTEXT: <description of before state>
EFFECT: <what changed>
LEARNING: <what this button does>"""
        
        try:
            response = self.llm.chat_with_images(
                prompt=prompt,
                images=[before_b64, after_b64]
            )
        except AttributeError:
            # Fallback: send single combined description request if chat_with_images missing
            # Only send the "after" image and ask what happened
            fallback_prompt = f"""Analyze this game screenshot which shows the state AFTER pressing '{button}'.
Describe what you see and tell me what this button likely did to reach this state.

Format your response exactly as:
CONTEXT: Unknown (Single image mode)
EFFECT: <describe visible state>
LEARNING: <hypothesis on what button did>"""
            
            response = self.llm.chat(
                prompt=fallback_prompt,
                image_data=after_b64
            )
        
        # Parse response
        context = ""
        effect = ""
        learning_text = ""
        
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("CONTEXT:"):
                context = line[8:].strip()
            elif line.startswith("EFFECT:"):
                effect = line[7:].strip()
            elif line.startswith("LEARNING:"):
                learning_text = line[9:].strip()
        
        # Create learning object
        learning = ActionLearning(
            button=button,
            game_phase=game_phase,
            context_description=context or "Unknown context",
            effect_description=effect or learning_text or "Unknown effect",
            before_frame_path=before_path,
            after_frame_path=after_path,
            timestamp=time.time()
        )
        
        # Store in knowledge base
        self.knowledge.store_learning(learning)
        
        print(f"[FeedbackLearner] Learned: '{button}' in {game_phase} -> {learning.effect_description[:60]}...")
        
        return learning
    
    def get_relevant_knowledge(self, button: str, game_phase: str, context: str) -> str:
        """Query past experiences for a given situation and format for prompt."""
        results = self.knowledge.query_similar(
            button=button,
            game_phase=game_phase,
            context_description=context,
            n_results=3
        )
        
        if not results:
            return ""
        
        lines = ["## Past Experience (from visual learning):"]
        for r in results:
            lines.append(f"- When I pressed '{r['button']}' in {r['game_phase']}: {r['effect']}")
        
        return "\n".join(lines)


# Test
if __name__ == "__main__":
    print("FeedbackLearner module loaded.")
    print("Use with: learner = FeedbackLearner(llm_client, capture_engine)")
