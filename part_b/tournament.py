from subprocess import PIPE,run

"""
    Python program that conducts a tournament between a number of agents against each other for a
    specefied number of times

"""

matches = 1000
cmdLine=["python3","-m", "referee", "greedyAgent2","greedyAgent3"]
countRed = 0
countBlue = 0
for i in range(matches):
    gameOutput = run(cmdLine,capture_output=True,text=True)
    countRed += gameOutput.stdout.count('winner is RED')
    countBlue += gameOutput.stdout.count('winner is BLUE')

print("GreedyAgent2 vs GreedyAgent3",countRed,countBlue,matches-(countRed+countBlue))
