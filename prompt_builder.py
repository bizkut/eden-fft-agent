"""
Prompt Builder for FFT LLM Agent.
Converts game state to text prompts for LLM.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class Unit:
    name: str
    job: str
    x: int
    y: int
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    ct: int = 0  # Charge Time
    is_ally: bool = True
    
    def __str__(self):
        team = "Ally" if self.is_ally else "Enemy"
        return f"- {self.name} ({self.job}) at ({self.x},{self.y}): HP {self.hp}/{self.max_hp}, MP {self.mp}/{self.max_mp}"


@dataclass
class GameState:
    """Current battle state."""
    map_name: str = "Battle Map"
    width: int = 12
    height: int = 10
    turn_number: int = 1
    current_unit: Optional[Unit] = None
    allies: List[Unit] = field(default_factory=list)
    enemies: List[Unit] = field(default_factory=list)
    valid_actions: List[str] = field(default_factory=lambda: ["Move", "Attack", "Wait"])
    phase: str = "action"  # 'move', 'action', 'direction', 'wait'


SYSTEM_PROMPT = """You are an expert Final Fantasy Tactics player. You make optimal tactical decisions.

CRITICAL: You are currently playing in "BLIND MODE". 
- You do NOT know exact unit positions or stats.
- You MUST make a best-guess decision.
- DO NOT REFUSE TO ACT.
- Moving blindly (e.g., "Right 2") is better than doing nothing.
- Assume enemies are forward/up.

Rules:
1. Prioritize keeping your units alive
2. Focus fire on weakened enemies
3. Use terrain height advantage when possible
4. Protect your healer and mages
5. Consider enemy turn order when positioning

Always respond in this exact format:
ACTION: <action_name>
TARGET: <x,y coordinates OR relative direction>
REASON: <brief tactical explanation>
"""


def build_prompt(state: GameState) -> str:
    """Convert game state to LLM prompt."""
    lines = [
        f"## Battle: {state.map_name}",
        f"Map Size: {state.width}x{state.height}",
        f"Turn: {state.turn_number}",
        "",
        "**VISUAL INPUT:** A screenshot of the current battle is attached.",
        "- Use the image to identify unit positions, terrain, and the highlighted cursor.",
        "- **LEGEND:** BLUE tiles = Movement range, YELLOW tiles = Attack range.",
        "- Combine visual cues with the stats below.",
        ""
    ]
    
    if state.current_unit:
        u = state.current_unit
        lines.extend([
            f"## Current Unit (Your Turn)",
            f"- {u.name} ({u.job}) at ({u.x if u.x else '?'},{u.y if u.y else '?'}) (Relative Position Only)",
            f"  HP: {u.hp}/{u.max_hp}, MP: {u.mp}/{u.max_mp}, CT: {u.ct}",
            "",
            "NOTE: Exact X/Y coordinates are unavailable. You MUST use relative directions.",
            "EXAMPLE: 'ACTION: Move', 'TARGET: Right 2'",
            ""
        ])
    
    if state.allies:
        lines.append("## Your Units")
        for u in state.allies:
            lines.append(str(u))
        lines.append("")
    
    if state.enemies:
        lines.append("## Enemies")
        for u in state.enemies:
            lines.append(str(u))
        lines.append("")
    
    lines.extend([
        f"## Available Actions",
        ", ".join(state.valid_actions),
        "",
        "What action should be taken?"
    ])
    
    return "\n".join(lines)


def build_move_prompt(state: GameState, reachable_tiles: List[tuple]) -> str:
    """Build prompt specifically for movement decision."""
    base = build_prompt(state)
    tiles_str = ", ".join([f"({x},{y})" for x, y in reachable_tiles[:20]])
    return base + f"\n\nReachable tiles: {tiles_str}\n\nChoose where to move."


if __name__ == "__main__":
    # Test prompt generation
    state = GameState(
        current_unit=Unit("Ramza", "Squire", 3, 4, 150, 150, 50, 50, is_ally=True),
        allies=[
            Unit("Agrias", "Holy Knight", 5, 2, 120, 120, 80, 80, is_ally=True),
        ],
        enemies=[
            Unit("Goblin", "Monster", 7, 5, 45, 80, 0, 0, is_ally=False),
            Unit("Archer", "Archer", 9, 3, 60, 60, 20, 20, is_ally=False),
        ],
        valid_actions=["Move", "Attack", "Stone", "Item", "Wait"]
    )
    
    prompt = build_prompt(state)
    print("=== SYSTEM PROMPT ===")
    print(SYSTEM_PROMPT)
    print("\n=== USER PROMPT ===")
    print(prompt)
