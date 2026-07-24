import subprocess

raw_command = 'espeak -v ro -s 150 -g 1 -a 1000 "InfoEducatie este Tare!"'

subprocess.run(raw_command, shell=True
