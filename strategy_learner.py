"""
Strategy Learner Module.

Tracks battle outcomes and learns which strategies work best.
This data can be used to:
1. Fine-tune the LLM's prompts with successful examples
2. Build a RAG knowledge base of "what worked"
3. Avoid repeating failed strategies
"""
import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Any

try:
    from knowledge_store import KnowledgeStore
    HAS_KNOWLEDGE_STORE = True
except ImportError:
    HAS_KNOWLEDGE_STORE = False


@dataclass
class BattleRecord:
    """Record of a single battle attempt."""
    battle_id: str  # e.g., "dorter_trade_city_1"
    map_name: str
    timestamp: float
    
    # Party state at start
    party_composition: List[Dict[str, Any]]  # [{job, level, hp, mp}, ...]
    
    # Actions taken (simplified log)
    actions_taken: List[str] = field(default_factory=list)
    
    # Outcome
    victory: bool = False
    turns_taken: int = 0
    units_lost: int = 0
    
    # Strategy notes (from StrategyAdvisor)
    strategy_mode: str = ""  # OFFENSIVE, DEFENSIVE, EMERGENCY
    key_decisions: List[str] = field(default_factory=list)


@dataclass
class StrategyInsight:
    """A learned insight about what works."""
    context: str  # e.g., "dorter_trade_city with 3 archers"
    strategy: str  # e.g., "Focus fire on enemy mages first"
    success_rate: float  # 0.0 to 1.0
    sample_size: int
    last_updated: float


class StrategyLearner:
    """
    Learns from battle outcomes to improve future decisions.
    """
    
    def __init__(self, data_dir: str = "./learning_data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        self.battles_file = self.data_dir / "battle_history.json"
        self.insights_file = self.data_dir / "strategy_insights.json"
        
        self.battle_history: List[BattleRecord] = []
        self.insights: List[StrategyInsight] = []
        
        self._load_data()
        
        # Knowledge store for RAG integration
        self.knowledge_store = None
        if HAS_KNOWLEDGE_STORE:
            try:
                self.knowledge_store = KnowledgeStore()
            except Exception as e:
                print(f"[StrategyLearner] KnowledgeStore unavailable: {e}")
        
        print(f"[StrategyLearner] Loaded {len(self.battle_history)} battles, {len(self.insights)} insights")
    
    def _load_data(self):
        """Load existing battle history and insights."""
        if self.battles_file.exists():
            try:
                with open(self.battles_file, 'r') as f:
                    data = json.load(f)
                    self.battle_history = [BattleRecord(**b) for b in data]
            except Exception as e:
                print(f"[StrategyLearner] Error loading battles: {e}")
        
        if self.insights_file.exists():
            try:
                with open(self.insights_file, 'r') as f:
                    data = json.load(f)
                    self.insights = [StrategyInsight(**i) for i in data]
            except Exception as e:
                print(f"[StrategyLearner] Error loading insights: {e}")
    
    def _save_data(self):
        """Save battle history and insights to disk."""
        with open(self.battles_file, 'w') as f:
            json.dump([asdict(b) for b in self.battle_history], f, indent=2)
        
        with open(self.insights_file, 'w') as f:
            json.dump([asdict(i) for i in self.insights], f, indent=2)
    
    def start_battle(self, map_name: str, party_composition: List[Dict]) -> BattleRecord:
        """
        Start tracking a new battle.
        
        Args:
            map_name: Name of the battle map
            party_composition: List of unit stats at battle start
        
        Returns:
            BattleRecord to update during battle
        """
        battle_id = f"{map_name.lower().replace(' ', '_')}_{int(time.time())}"
        
        record = BattleRecord(
            battle_id=battle_id,
            map_name=map_name,
            timestamp=time.time(),
            party_composition=party_composition
        )
        
        print(f"[StrategyLearner] Tracking battle: {battle_id}")
        return record
    
    def log_action(self, record: BattleRecord, action: str):
        """Log an action taken during battle."""
        record.actions_taken.append(action)
    
    def log_decision(self, record: BattleRecord, decision: str):
        """Log a key strategic decision."""
        record.key_decisions.append(decision)
    
    def end_battle(self, record: BattleRecord, victory: bool, turns: int, units_lost: int):
        """
        End battle tracking and learn from outcome.
        
        Args:
            record: The battle record
            victory: Did we win?
            turns: How many turns it took
            units_lost: How many party members were KO'd
        """
        record.victory = victory
        record.turns_taken = turns
        record.units_lost = units_lost
        
        self.battle_history.append(record)
        self._save_data()
        
        outcome = "VICTORY" if victory else "DEFEAT"
        print(f"[StrategyLearner] Battle ended: {outcome} in {turns} turns, {units_lost} units lost")
        
        # Learn from this battle
        self._extract_insights(record)
        
        # Store successful strategies in RAG
        if victory and self.knowledge_store:
            self._store_successful_strategy(record)
    
    def _extract_insights(self, record: BattleRecord):
        """Extract learnable insights from a battle."""
        # Simple insight: track success rate per map
        map_battles = [b for b in self.battle_history if b.map_name == record.map_name]
        wins = sum(1 for b in map_battles if b.victory)
        
        success_rate = wins / len(map_battles) if map_battles else 0
        
        # Update or create insight for this map
        existing = next((i for i in self.insights if record.map_name in i.context), None)
        
        if existing:
            existing.success_rate = success_rate
            existing.sample_size = len(map_battles)
            existing.last_updated = time.time()
        else:
            self.insights.append(StrategyInsight(
                context=record.map_name,
                strategy=f"Historical success rate on {record.map_name}",
                success_rate=success_rate,
                sample_size=len(map_battles),
                last_updated=time.time()
            ))
        
        self._save_data()
    
    def _store_successful_strategy(self, record: BattleRecord):
        """Store a successful battle strategy in the knowledge base."""
        if not self.knowledge_store:
            return
        
        # Format as a strategy guide
        content = f"""
Battle: {record.map_name}
Result: VICTORY in {record.turns_taken} turns
Units Lost: {record.units_lost}
Strategy Mode: {record.strategy_mode}

Key Decisions:
{chr(10).join('- ' + d for d in record.key_decisions)}

Actions Summary:
{chr(10).join('- ' + a for a in record.actions_taken[-10:])}
"""
        
        self.knowledge_store.store_strategy_guide(
            title=f"Victory at {record.map_name}",
            content=content,
            tags=["battle", "victory", record.map_name]
        )
    
    def get_advice_for_map(self, map_name: str) -> str:
        """
        Get learned advice for a specific map.
        
        Returns formatted advice for the LLM prompt.
        """
        # Check historical performance
        map_battles = [b for b in self.battle_history if b.map_name == map_name]
        
        if not map_battles:
            return ""
        
        wins = sum(1 for b in map_battles if b.victory)
        losses = len(map_battles) - wins
        
        advice_lines = [f"## Historical Data for {map_name}"]
        advice_lines.append(f"- Previous attempts: {len(map_battles)} ({wins}W / {losses}L)")
        
        if losses > wins:
            # Analyze what went wrong in losses
            lost_battles = [b for b in map_battles if not b.victory]
            avg_units_lost = sum(b.units_lost for b in lost_battles) / len(lost_battles)
            advice_lines.append(f"- Average units lost in defeats: {avg_units_lost:.1f}")
            advice_lines.append("- CAUTION: This is a difficult battle. Play defensively.")
        elif wins > 0:
            # Share what worked
            won_battles = [b for b in map_battles if b.victory]
            best_win = min(won_battles, key=lambda b: b.turns_taken)
            advice_lines.append(f"- Best clear: {best_win.turns_taken} turns, {best_win.units_lost} units lost")
        
        return "\n".join(advice_lines)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get overall learning statistics."""
        total = len(self.battle_history)
        wins = sum(1 for b in self.battle_history if b.victory)
        
        return {
            "total_battles": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": wins / total if total > 0 else 0,
            "insights_learned": len(self.insights)
        }
