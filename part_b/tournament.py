from subprocess import PIPE,run

"""
    Python program that conducts a tournament between a number of agents against each other for a
    specefied number of times

"""

cmdLine=["python3","-m", "referee", "greedyAgent","randomAgent"]
countRed = 0
countBlue = 0
for i in range(30):
    gameOutput = run(cmdLine,capture_output=True,text=True)
    countRed += gameOutput.stdout.count('winner is RED')
    countBlue += gameOutput.stdout.count('winner is BLUE')

print(countRed,countBlue,30-(countRed+countBlue))
