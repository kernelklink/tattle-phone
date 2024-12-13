#!/usr/bin/env python3

# voice-recorder.py
#
# A class that will cheat and use arecord to record voice messages to a file

import subprocess
from threading import Event, Thread
import shutil
import logging
import time
from datetime import datetime
from pathlib import Path

_RECORD_EXECUTABLE = 'arecord'

class VoiceRecorder(Thread):
    """VoiceRecorder class is very direct, basically just records to a file.
    """
    def __init__(self, filename: str):
        super().__init__()
        self.name = "VoiceRecorder"
        self._filename = Path(filename)
        self._executable = shutil.which(_RECORD_EXECUTABLE)
        self._kill_event = Event()
    
    def run(self):
        """Uses arecorord to record to the given wavefile
        """
        # Figure out the location of the executable
        args = [self._executable, self._filename]

        # Start recording to file
        logging.debug(f"Starting recording to {self._filename.name}")
        proc = subprocess.Popen(args)

        # Wait until someone tells us to die
        self._kill_event.wait(timeout=120)        

        # Die
        proc.kill()
        logging.debug(f"Completed recording to {self._filename.name}")
    
    def kill(self):
        """Kill the subprocess we started
        """
        self._kill_event.set()

if (__name__ == "__main__"):
    """Run a quick test of voice recorder by recording to the given file.
    """
    print("This test will record a wave file for 8 seconds and then die.")
    recorder = VoiceRecorder("hudson_test.wav")
    recorder.start()
    time.sleep(8)
    recorder.kill()
    recorder.join()