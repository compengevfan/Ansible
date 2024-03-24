import sys

Info = sys.argv

Zone1 = Info[1]
Zone2 = Info[3]

Port1 = Zone1.split('_')[4].replace('\t','')
Port2 = Zone2.split('_')[4].replace('\t','')

print(Port1)
print(Port2)