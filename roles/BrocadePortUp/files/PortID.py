import sys

Info = sys.argv

if (Info[2] == "-1"):
    PortReturn = Info[1]
else:
    PortReturn = Info[2] + "/" + Info[1]

print(PortReturn)