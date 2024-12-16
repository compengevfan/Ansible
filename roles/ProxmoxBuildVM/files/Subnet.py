import sys

subnet = sys.argv

# print(subnet[0])
# print(subnet[1])

if subnet[1] == "23":
    print("255.255.254.0")

if subnet[1] == "24":
    print("255.255.255.0")
