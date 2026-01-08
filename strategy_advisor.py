"""
Strategy Advisor Module.

This module provides high-level strategic analysis based on the raw game memory state.
It interprets the numerical data (HP, MP, stats) into tactical advice for the LLM.
"""
from typing import List, Dict, Optional
from memory_reader import GameMemoryState, UnitStats

class StrategyAdvisor:
    """
    Analyzes game state to provide strategic advice.
    """

    def analyze_party_status(self, state: GameMemoryState) -> str:
        """
        Analyze the overall health and status of the party.
        Returns a summary string for the LLM.
        """
        if not state.connected or not state.units:
            return "Status: Unknown (No memory connection)"

        advice = []
        active_units = [u for u in state.units if u.max_hp > 0]
        
        if not active_units:
             return "Status: No active units found."

        # 1. Health Assessment
        total_hp = sum(u.hp for u in active_units)
        total_max_hp = sum(u.max_hp for u in active_units)
        avg_hp_percent = (total_hp / total_max_hp) * 100 if total_max_hp > 0 else 0
        
        critical_units = [u for u in active_units if u.hp > 0 and (u.hp / u.max_hp) < 0.3]
        dead_units = [u for u in active_units if u.hp == 0]

        if dead_units:
            names = [f"Unit {u.unit_id}" for u in dead_units]
            advice.append(f"CRITICAL: {len(dead_units)} unit(s) are DOWN ({', '.join(names)})! Prioritize reviving (Phoenix Down/Raise).")
        
        if critical_units:
            names = [f"Unit {u.unit_id}" for u in critical_units]
            advice.append(f"WARNING: {len(critical_units)} unit(s) in CRITICAL health ({', '.join(names)}). Heal immediately.")
        
        if not dead_units and not critical_units:
            advice.append("Party Status: Healthy. Focus on offense.")

        # 2. MP Resource Management
        low_mp_casters = [u for u in active_units if u.max_mp > 50 and (u.mp / u.max_mp) < 0.2]
        if low_mp_casters:
             advice.append("Resource Alert: Some casters are low on MP. Consider using Ether or Chakra.")

        # 3. Ramza Specific Advice
        ramza = next((u for u in active_units if u.unit_id == 1), None)
        if ramza:
            if ramza.magic_ready:
                advice.append("Tactical Opportunity: Ramza has a spell CHARGED and ready to cast!")
            
            # Advice based on Job (basic mapping)
            # Job IDs are defined in memory_reader.py, but we can infer role
            if ramza.attack > ramza.max_mp: # Physical leaning
                advice.append(f"Ramza Role: Physical Attacker (ATK {ramza.attack}). Look for flanking opportunities.")
            else:
                advice.append(f"Ramza Role: Magic/Support (MP {ramza.max_mp}). Keep distance.")

        return "\n".join(advice)

    def get_tactical_plan(self, state: GameMemoryState) -> str:
        """
        Generates a specific tactical plan for the next turn.
        """
        plan = ["## Advisor Strategy"]
        
        status_analysis = self.analyze_party_status(state)
        plan.append(status_analysis)
        
        # Determine strictness/mode
        # If any unit is critical, shift mode to DEFENSIVE
        active_units = [u for u in state.units if u.max_hp > 0]
        any_critical = any(u.hp > 0 and (u.hp / u.max_hp) < 0.3 for u in active_units)
        any_dead = any(u.hp == 0 for u in active_units)
        
        if any_dead:
            plan.append("Mode: **EMERGENCY RECOVERY**")
            plan.append("- Objective: Revive fallen allies immediately.")
            plan.append("- Tactic: Use Items (Phoenix Down) or White Magic (Raise). Do not attack unless necessary.")
        elif any_critical:
            plan.append("Mode: **DEFENSIVE / HEALING**")
            plan.append("- Objective: Stabilize the party.")
            plan.append("- Tactic: Cast Cure/Cura or use Potions. Tank units should move to block enemies.")
        else:
            plan.append("Mode: **OFFENSIVE**")
            plan.append("- Objective: Eliminate enemy units.")
            plan.append("- Tactic: Focus fire on the nearest or weakest enemy. Utilize high ground.")
            
        return "\n".join(plan)
