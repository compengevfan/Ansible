import sys

PortInfo = sys.argv

for i in range(len(PortInfo)):
    if "u\\t" in PortInfo[i]:
        print(PortInfo[i])