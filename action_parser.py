"""
Action Parser for FFT LLM Agent.
Converts LLM text responses to game inputs.
"""
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class ParsedAction:
    """Parsed action from LLM response."""
    action: str
    target: Optional[str] = None
    target_coords: Optional[Tuple[int, int]] = None
    reason: Optional[str] = None


def parse_llm_response(response: str) -> ParsedAction:
    """
    Parse LLM response in format:
    ACTION: Move
    TARGET: 5,3
    REASON: Moving to high ground
    """
    action = None
    target = None
    target_coords = None
    reason = None
    
    # Extract ACTION
    action_match = re.search(r'ACTION:\s*(\w+)', response, re.IGNORECASE)
    if action_match:
        action = action_match.group(1).lower()
    
    # Extract TARGET (can be coords or name)
    target_match = re.search(r'TARGET:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
    if target_match:
        target = target_match.group(1).strip().lower()
        
        # Try to parse as coordinates
        coord_match = re.search(r'\(?(\d+)\s*,\s*(\d+)\)?', target)
        if coord_match:
            target_coords = (int(coord_match.group(1)), int(coord_match.group(2)))
        else:
            # Try to parse relative directions: "right 2", "up", etc.
            dx, dy = 0, 0
            if "left" in target: dx -= 1
            if "right" in target: dx += 1
            if "up" in target: dy -= 1
            if "down" in target: dy += 1
            
            # Check for amount (e.g. "right 2")
            amount_match = re.search(r'(\d+)', target)
            if amount_match:
                mult = int(amount_match.group(1))
                dx *= mult
                dy *= mult
            
            if dx != 0 or dy != 0:
                # Store as relative coords
                target_coords = (dx, dy)
                # Hack: Indicate it's relative
                # Ideally ParsedAction should have is_relative flag
                # For now, we'll handle this in action_to_inputs by checking current_pos
    
    # Extract REASON
    reason_match = re.search(r'REASON:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
    if reason_match:
        reason = reason_match.group(1).strip()
    
    return ParsedAction(
        action=action or "wait",
        target=target,
        target_coords=target_coords,
        reason=reason
    )


def action_to_inputs(parsed: ParsedAction, current_pos: Tuple[int, int]) -> List[str]:
    """
    Convert parsed action to sequence of button inputs.
    Returns list of input commands like ['move_to:5,3', 'press:a'].
    """
    inputs = []
    
    if parsed.action == "move" and parsed.target_coords:
        tx, ty = parsed.target_coords
        cx, cy = current_pos
        # Calculate movement direction
        dx = tx - cx
        dy = ty - cy
        
        # Navigate to "Move" in menu (handled by executor with OCR)
        inputs.append("select:move")
        inputs.append("wait:0.5")
        
        # Confirm selection
        inputs.append("press:a")
        inputs.append("wait:1.0")  # Wait for grid animation
        
        # Move cursor to target tile
        if dx != 0 or dy != 0:
            inputs.append(f"move_cursor:{dx},{dy}")
        
        # Confirm move
        inputs.append("press:a")
        
    elif parsed.action == "attack" and parsed.target_coords:
        inputs.append("press:a")  # Open action menu
        inputs.append("select:attack")
        tx, ty = parsed.target_coords
        cx, cy = current_pos
        inputs.append(f"move_cursor:{tx-cx},{ty-cy}")
        inputs.append("press:a")  # Confirm
        
    elif parsed.action == "wait":
        inputs.append("select:wait")
        inputs.append("press:a")
    
    else:
        # Generic action selection
        inputs.append("press:a")
        inputs.append(f"select:{parsed.action}")
        if parsed.target_coords:
            inputs.append(f"move_cursor_to:{parsed.target_coords[0]},{parsed.target_coords[1]}")
        inputs.append("press:a")
    
    return inputs


class InputExecutor:
    """Execute parsed inputs via CemuhookUDP with LLM-driven menu navigation."""
    
    # Known menu structures as HINTS for context (not mandatory)
    # The LLM sees the screen and can override these
    KNOWN_MENUS = {
        "battle_command": ["Move", "Act", "Wait", "Status"],
        "act_menu": ["Attack", "Abilities", "Item"],
    }
    
    def __init__(self, controller, ocr_engine=None, capture_engine=None):
        self.controller = controller
        self.ocr = ocr_engine
        self.capture = capture_engine
        self.feedback_learner = None  # Set by FFTAgent if learning enabled
        self._current_game_phase = "unknown"
    
    def set_game_phase(self, phase: str):
        """Set current game phase for learning context."""
        self._current_game_phase = phase
    
    def get_menu_hint(self, menu_type: str) -> str:
        """Get menu structure hint for LLM context (not for navigation)."""
        if menu_type in self.KNOWN_MENUS:
            items = ", ".join(self.KNOWN_MENUS[menu_type])
            return f"Menu options (top to bottom): {items}"
        return ""
    
    def execute(self, inputs: List[str]):
        """Execute list of input commands with optional visual feedback learning."""
        for inp in inputs:
            print(f"[Input] Executing: {inp}")
            
            # Capture BEFORE state if learning enabled and this is a press command
            should_learn = self.feedback_learner and inp.startswith("press:")
            if should_learn:
                self.feedback_learner.capture_before(self._current_game_phase)
            
            if inp.startswith("press:"):
                button = inp.split(":")[1]
                if button == "a":
                    self.controller.press_a()
                elif button == "b":
                    self.controller.press_b()
                elif button == "x":
                    self.controller.press_x()
                elif button == "y":
                    self.controller.press_y()
                elif button == "up":
                    self.controller.press_dpad('up')
                elif button == "down":
                    self.controller.press_dpad('down')
                elif button == "left":
                    self.controller.press_dpad('left')
                elif button == "right":
                    self.controller.press_dpad('right')
                elif button == "start":
                    self.controller.press_start()
                elif button == "select":
                    self.controller.press_select()
                
                # Capture AFTER state and learn
                if should_learn:
                    import time
                    time.sleep(0.3)  # Wait for visual update
                    self.feedback_learner.capture_after_and_learn(button)
                    
            elif inp.startswith("move_cursor:"):
                coords = inp.split(":")[1]
                dx, dy = map(int, coords.split(","))
                self.controller.move_cursor(dx, dy)
                
            elif inp.startswith("select:"):
                # Hybrid Menu Navigation
                # 1. Try to find target in known menus
                target = inp.split(":")[1].lower()
                menu_order = [x.lower() for x in self.KNOWN_MENUS["battle_command"]]
                
                if target in menu_order:
                    # Robust navigation: Reset to top, then move down
                    target_idx = menu_order.index(target)
                    print(f"  [Menu] Navigating to '{target}' (Index {target_idx})")
                    
                    # Reset to top (Press Up 4 times)
                    for _ in range(4):
                        self.controller.press_dpad('up')
                        import time
                        time.sleep(0.15)
                    
                    # Move down to target
                    for _ in range(target_idx):
                        self.controller.press_dpad('down')
                        import time
                        time.sleep(0.2)
                        
                    # Confirm
                    self.controller.press_a()
                else:
                    print(f"  [Menu] Unknown target '{target}', assuming current selection")
                    self.controller.press_a()
            
            elif inp.startswith("wait:"):
                duration = float(inp.split(":")[1])
                import time
                time.sleep(duration)
            
            # Small delay between inputs
            import time
            time.sleep(0.3)




if __name__ == "__main__":
    # Test parsing
    response = """
    Based on the tactical situation, I recommend:
    
    ACTION: Move
    TARGET: 5,3
    REASON: Moving to high ground gives attack bonus and stays out of archer range.
    """
    
    parsed = parse_llm_response(response)
    print(f"Parsed Action: {parsed}")
    
    inputs = action_to_inputs(parsed, current_pos=(3, 4))
    print(f"Inputs: {inputs}")
