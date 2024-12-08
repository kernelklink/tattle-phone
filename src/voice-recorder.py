# voice-recorder.py
#
# A class that will cheat and use arecord to record voice messages to a file

import subprocess
from threading import Event
import shutil
import logging
import time
from datetime import datetime

class VoiceRecorder():
    """VoiceRecorder class is very direct, basically just records to a file.
    """
    def __init__(self, filename: str):
        self.name = "VoiceRecorder"
        self._filename = filename
        self._executable = 'arecord'
        self._kill_event = Event()
    
    def run(self):
        """Uses arecorord to record to the given wavefile
        """
        # Figure out the location of the executable
        self._executable = shutil.which(self._executable)
        args = [self._executable, self._filename]

        # Start recording to file
        proc = subprocess.Popen(args)

        # Wait until someone tells us to die
        self._kill_event.wait(timeout=120)        

        # Die
        proc.kill()
    
    def kill(self):
        """Kill the subprocess we started
        """
        self._kill_event.set()

if (__name__ == "__main__"):
    """Run a quick test of voice recorder by recording to the given file.
    """
    print("This test will record a wave file for 8 seconds and then die.")
    recorder = VoiceRecorder("hudson_test.wav")
    
    recorder.run()
    time.sleep(8)
    recorder.kill()