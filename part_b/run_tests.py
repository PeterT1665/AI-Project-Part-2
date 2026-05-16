from subprocess import run
import sys

"""
Test v7_iddfs against agents in all 3 benchmark categories:
  - Random (5 marks):           v0_random
  - Greedy (3 marks):           v2b_greedy_depth1
  - Adversarial search (3 marks): v1_minimax, v2_alphabeta, v5_alphabeta_killer, v6_cascade_eval

Each matchup runs GAMES games with v7 as RED, then GAMES games with v7 as BLUE.
"""

PYTHON  = sys.executable
GAMES   = 5   # per side (10 total per matchup)
V7      = "v7_iddfs"

matchups = [
    # (label, opponent, category)
    ("v0_random",          "v0_random",          "Random       (5 marks)"),
    ("v2b_greedy_depth1",  "v2b_greedy_depth1",  "Greedy       (3 marks)"),
    ("v1_minimax",         "v1_minimax",          "Adversarial  (3 marks)"),
    ("v2_alphabeta",       "v2_alphabeta",        "Adversarial  (3 marks)"),
    ("v5-2_alphabeta_killer","v5-2_alphabeta_killer", "Adversarial  (3 marks)"),
    ("v6_cascade_eval",    "v6_cascade_eval",     "Adversarial  (3 marks)"),
]

def run_games(red, blue, n):
    wins_red = wins_blue = 0
    for i in range(n):
        out = run([PYTHON, "-m", "referee", red, blue],
                  capture_output=True, text=True)
        wins_red  += out.stdout.count("winner is RED")
        wins_blue += out.stdout.count("winner is BLUE")
        draws = (i + 1) - wins_red - wins_blue
        print(f"  game {i+1}/{n}: RED={wins_red} BLUE={wins_blue} DRAW={draws}", flush=True)
    draws = n - wins_red - wins_blue
    return wins_red, wins_blue, draws

total_wins = total_played = 0

for label, opp, category in matchups:
    print(f"\n{'='*60}")
    print(f"  {V7} vs {label}  [{category}]")
    print(f"{'='*60}")

    print(f"\n  v7 as RED vs {opp} as BLUE ({GAMES} games):")
    wr, wb, wd = run_games(V7, opp, GAMES)
    v7_as_red = wr

    print(f"\n  v7 as BLUE vs {opp} as RED ({GAMES} games):")
    wr, wb, wd2 = run_games(opp, V7, GAMES)
    v7_as_blue = wb

    v7_wins  = v7_as_red + v7_as_blue
    v7_draws = wd + wd2
    v7_loss  = GAMES * 2 - v7_wins - v7_draws
    total_wins   += v7_wins
    total_played += GAMES * 2

    print(f"\n  RESULT  v7 W={v7_wins}  D={v7_draws}  L={v7_loss}  "
          f"(out of {GAMES*2} games)")

print(f"\n{'='*60}")
print(f"  OVERALL  v7 wins {total_wins}/{total_played} games across all matchups")
print(f"{'='*60}\n")
