import subprocess

def speakAudio(message):
    command = ['espeak', '-v', 'ro', '-s', '150', '-g', '1', '-a', '1000', message]
    
    subprocess.run(command)
