import sys

subnet = sys.argv

if subnet == 23:
    print("255.255.254.0")

if subnet == 24:
    print("255.255.255.0")
