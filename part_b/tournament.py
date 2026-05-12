from subprocess import run

"""
    Python program that conducts a tournament between a number of agents against each other for a
    specefied number of times

"""

matches = 20
RED_AGENT = "v5_cascade_eval"
BLUE_AGENT = "v5b_cascade_eval"
cmdLine=["/opt/anaconda3/bin/python","-m", "referee", RED_AGENT, BLUE_AGENT]
countRed = 0
countBlue = 0
for i in range(matches):
    gameOutput = run(cmdLine,capture_output=True,text=True)
    countRed += gameOutput.stdout.count('winner is RED')
    countBlue += gameOutput.stdout.count('winner is BLUE')
    print(f"Game {i+1}: RED={countRed} BLUE={countBlue}", flush=True)

print(f"\n{RED_AGENT} vs {BLUE_AGENT}: RED={countRed} BLUE={countBlue} DRAW={matches-(countRed+countBlue)}")
