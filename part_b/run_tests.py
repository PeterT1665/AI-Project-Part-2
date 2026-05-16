from subprocess import run
import sys

"""
Benchmark v8_new against agents in all 3 Gradescope categories:
  - Random      (5 marks): v0_random
  - Greedy      (3 marks): v2b_greedy_depth1
  - Adversarial (3 marks): v2_alphabeta (easy), v5-2_alphabeta_killer (med), v7_iddfs (hard)

Each matchup runs 1 game with v8 as RED and 1 game with v8 as BLUE (2 total per opponent).
"""

PYTHON = sys.executable
AGENT  = "v8_new"

matchups = [
    # (label, opponent, category)
    ("random_agent",    "random_agent",    "Random       (5 marks)"),
    ("greedy",          "greedy",          "Greedy       (3 marks) — easy"),
    ("adversarial_easy","adversarial_easy","Adversarial  (3 marks) — easy"),
    ("adversarial_med", "adversarial_med", "Adversarial  (3 marks) — med"),
    ("adversarial_hard","adversarial_hard","Adversarial  (3 marks) — hard"),
]


def run_game(red, blue):
    out = run([PYTHON, "-m", "referee", red, blue], capture_output=True, text=True)
    if "winner is RED"  in out.stdout: return "RED"
    if "winner is BLUE" in out.stdout: return "BLUE"
    return "DRAW"


total_wins = total_draws = total_loss = 0

for label, opp, category in matchups:
    print(f"\n{'='*60}")
    print(f"  {AGENT} vs {label}  [{category}]")
    print(f"{'='*60}")

    # game 1: v8 as RED
    r1 = run_game(AGENT, opp)
    print(f"  {AGENT}(RED)  vs {opp}(BLUE): {r1}")

    # game 2: v8 as BLUE
    r2 = run_game(opp, AGENT)
    print(f"  {opp}(RED)  vs {AGENT}(BLUE): {r2}")

    wins  = (1 if r1 == "RED"  else 0) + (1 if r2 == "BLUE" else 0)
    draws = (1 if r1 == "DRAW" else 0) + (1 if r2 == "DRAW" else 0)
    loss  = (1 if r1 == "BLUE" else 0) + (1 if r2 == "RED"  else 0)

    total_wins  += wins
    total_draws += draws
    total_loss  += loss

    print(f"\n  RESULT  {AGENT} W={wins}  D={draws}  L={loss}  (out of 2 games)")

print(f"\n{'='*60}")
print(f"  OVERALL  W={total_wins}  D={total_draws}  L={total_loss}  "
      f"(out of {total_wins + total_draws + total_loss} games)")
print(f"{'='*60}\n")
