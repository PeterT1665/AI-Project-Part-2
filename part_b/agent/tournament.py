"""
Tournament: v8_new (agent) vs all opponents.
Each matchup plays 20 games — 10 with v8 as RED, 10 with v8 as BLUE.
Run: python tournament.py
"""
import sys
from subprocess import run

PYTHON  = sys.executable
AGENT   = "v8_new"
GAMES   = 10  # per colour side

OPPONENTS = [
    ("random_agent",    "Random"),
    ("greedy",          "Greedy"),
    ("adversarial_easy","Adversarial Easy"),
    ("adversarial_med", "Adversarial Med"),
    ("adversarial_hard","Adversarial Hard"),
]


def play(red, blue):
    out = run([PYTHON, "-m", "referee", red, blue], capture_output=True, text=True)
    if "winner is RED"  in out.stdout: return "RED"
    if "winner is BLUE" in out.stdout: return "BLUE"
    return "DRAW"


def pct(wins, total):
    return f"{100 * wins / total:.0f}%" if total else "N/A"


print(f"\n{'='*64}")
print(f"  TOURNAMENT: {AGENT} vs all opponents ({GAMES*2} games each)")
print(f"{'='*64}\n")

grand_w = grand_d = grand_l = 0

for opp, label in OPPONENTS:
    print(f"  {AGENT} vs {label} ({opp})")
    print(f"  {'-'*52}")

    red_w = red_d = red_l = 0
    for i in range(1, GAMES + 1):
        r = play(AGENT, opp)
        if   r == "RED":  red_w += 1
        elif r == "DRAW": red_d += 1
        else:             red_l += 1
        print(f"    [RED  game {i:2d}] {r}", flush=True)

    blue_w = blue_d = blue_l = 0
    for i in range(1, GAMES + 1):
        r = play(opp, AGENT)
        if   r == "BLUE": blue_w += 1
        elif r == "DRAW": blue_d += 1
        else:             blue_l += 1
        print(f"    [BLUE game {i:2d}] {r}", flush=True)

    total_w = red_w + blue_w
    total_d = red_d + blue_d
    total_l = red_l + blue_l
    total   = GAMES * 2

    grand_w += total_w
    grand_d += total_d
    grand_l += total_l

    print()
    print(f"  RESULT vs {label}:")
    print(f"    As RED:   W={red_w}  D={red_d}  L={red_l} / {GAMES}"
          f"  →  win {pct(red_w, GAMES)}  draw {pct(red_d, GAMES)}  loss {pct(red_l, GAMES)}")
    print(f"    As BLUE:  W={blue_w}  D={blue_d}  L={blue_l} / {GAMES}"
          f"  →  win {pct(blue_w, GAMES)}  draw {pct(blue_d, GAMES)}  loss {pct(blue_l, GAMES)}")
    print(f"    Overall:  W={total_w}  D={total_d}  L={total_l} / {total}"
          f"  →  win {pct(total_w, total)}  draw {pct(total_d, total)}  loss {pct(total_l, total)}")
    print()

grand_total = grand_w + grand_d + grand_l
print(f"{'='*64}")
print(f"  GRAND TOTAL  W={grand_w}  D={grand_d}  L={grand_l} / {grand_total}"
      f"  →  win {pct(grand_w, grand_total)}  draw {pct(grand_d, grand_total)}"
      f"  loss {pct(grand_l, grand_total)}")
print(f"{'='*64}\n")
