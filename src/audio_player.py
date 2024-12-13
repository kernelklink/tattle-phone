#!/usr/bin/env python3

# audio_player.py
#
# Class which exists to play audio, and which is made as a Thread so it
# can be easily interrupted.

from threading import Thread, Event
import logging
import subprocess
import shutil
import enum
import time
from queue import Queue

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

class PlayType(enum.Enum):
    PLAYER_KILL=0
    PLAYER_TEXT=1
    PLAYER_FILE=2
    PLAYER_DIRECTORY=3

_SPEECH_UTIL = 'espeak-ng'
_PLAYBACK_UTIL = 'aplay'

class AudioPlayer(Thread):
    def __init__(self, output_queue:Queue):
        super().__init__()
        self.name = "AudioPlayer"
        self._play_interrupt = Event()
        self._input_queue = Queue()
        self._output_queue = output_queue
        self._proc = None

        self._speech_util = shutil.which(_SPEECH_UTIL)
        self._playback_util = shutil.which(_PLAYBACK_UTIL)
    
    def is_busy(self) -> bool:
        """Let someone know if we're busy. Allows us to block while playing.

        Returns:
            bool: True if we're currently playing something, false otherwise.
        """
        return self.proc is not None
    
    def kill(self):
        self._input_queue.put((PlayType.PLAYER_KILL,0))
        pass

    def stop(self):
        """Stop any ongoing playing happening right now
        """
        self._play_interrupt.set()
    
    def play_text(self, text:str):
        """Render the given text as audio.

        Args:
            text (str): Text you would like converted to speech
        """
        self._input_queue.put((PlayType.PLAYER_TEXT, text))
    
    def play_file(self, file:str):
        """Play the given file

        Args:
            file (str): file you would like converted to speech
        """
        self._input_queue.put((PlayType.PLAYER_FILE, file))

    def run(self):
        while(1):
            logging.info("Waiting for a request")
            job_type, item = self._input_queue.get()

            args = []

            args = []
            if( job_type == PlayType.PLAYER_TEXT ):
                logging.info("I've been asked to play this text {}".format(item))
                # formulate my arguments and start the process
                args = [
                    self._speech_util,
                    "-ven-us+f2",
                    item]
                
            elif( job_type == PlayType.PLAYER_FILE ):
                logging.info("I've been asked to play this file {}".format(item))
                # Formulate my rguments and start the process
                args = [
                    self._playback_util,
                    item
                ]

            elif( job_type == PlayType.PLAYER_DIRECTORY ):
                pass

            # Let's stop this crazy ride!
            elif( job_type == PlayType.PLAYER_KILL ):
                if( self.proc is not None ):
                    self.proc.kill()
                break

            else:
                logging.warning("Audio Player started without anything to do")
                return
            
            # Open a process to play somethign
            if( len(args) > 0 ):
                self.proc = subprocess.Popen(args)

                # Wait for it to die.
                while(self.proc.poll() is None):
                    if( self._play_interrupt.wait(timeout=0.2) ):
                        break
                self.proc.kill()
                self.proc = None
                if( not self._play_interrupt.is_set() ):
                    self._output_queue.put(("AUDIO", "DONE"))
                self._play_interrupt.clear()

if __name__ == "__main__":
    text_player = AudioPlayer(text="Play some text for me please!")
    file_player = AudioPlayer(audio_file="../sounds/beep.wav")

    text_player.start()

    while(text_player.is_alive()):
        time.sleep(1)
    
    file_player.start()
    while( file_player.is_alive() ):
        time.sleep(1)
    
    text_player.join()
    file_player.join()