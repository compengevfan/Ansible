import sys

Info = sys.argv

Split1 = Info[3].split('_')
ExtractedPort = Split1[0].replace('port','')

if ('/' in ExtractedPort):
    Split3 = ExtractedPort.split('/')
    NameReturn = "slot" + Split3[0] + " port" + Split3[1]
else:
    NameReturn = "port" + ExtractedPort

print(ExtractedPort)
print(NameReturn)