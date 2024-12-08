# voice-recorder.py
#
# A class that will cheat and use arecord to record voice messages to a file

import subprocess
from queue import Queue
from threading import Lock, Timer, Event
import shutil
import logging
import time

class VoiceRecorder():
    def __init__(self, filename: str, input_queue: Queue):
        self.input_queue = input_queue
        self.filename = filename
        self.name = "VoiceRecorder"
        self.executable = 'arecord'
    
    def run(self):
        
        # Figure out the location of the executable
        self.executable = shutil.which(self.executable)
        args = [self.executable, self.filename]

        # Start recording to file
        proc = subprocess.Popen(
            args
        )
        time.sleep(8)
        
        proc.kill()
            
            


if (__name__ == "__main__"):
    recorder_queue = Queue()
    recorder = VoiceRecorder("hudson_test.wav", recorder_queue)

    recorder.run()