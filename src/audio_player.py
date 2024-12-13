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

        # Get rid of anything in the queue
        while(not self._input_queue.empty()):
            _ = self._input_queue.get()
    
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
            logging.info("AudioPlayer: Waiting for a request")
            job_type, item = self._input_queue.get()

            args = []
            if( job_type == PlayType.PLAYER_TEXT ):
                logging.info("AudioPlayer: I've been asked to play this text '{}'".format(item))
                # formulate my arguments and start the process
                args = [
                    self._speech_util,
                    "-ven-us+f2",
                    item]
                
            elif( job_type == PlayType.PLAYER_FILE ):
                logging.info("AudioPlayer: I've been asked to play this file '{}'".format(item))
                # Formulate my rguments and start the process
                args = [
                    self._playback_util,
                    item
                ]

            # Let's stop this crazy ride!
            elif( job_type == PlayType.PLAYER_KILL ):
                logging.info("AudioPlayer: It seems I've been told to die")
                if( self.proc is not None ):
                    self.proc.kill()
                break
            
            else:
                logging.error(f"AudioPlayer: Unrecognized job type {job_type}:{item}")
            
            # Open a process to play somethign
            if( len(args) > 0 ):
                self.proc = subprocess.Popen(args)

                # Wait for it to die.
                while(self.proc.poll() is None):
                    if( self._play_interrupt.wait(timeout=0.2) ):
                        break
                self.proc.kill()
                self.proc = None
                if( self._play_interrupt.is_set() ):
                    logging.debug("AudioPlayer: Looks like someone called STOP. Clearing the event")
                    self._play_interrupt.clear()
                else:
                    logging.debug("AudioPlayer: It seems I've died of my own accord, continue!")

                if( self._input_queue.empty() ):
                    logging.debug("AudioPlayer: Queue is empty! Telling the caller that I'm ready for more")
                    self._output_queue.put(("AUDIO", None))

if __name__ == "__main__":
    signal_queue = Queue()
    audio_player = AudioPlayer(signal_queue)
    audio_player.start()

    audio_player.play_text("now is the time for all good men to come to the aid of their country.")
    time.sleep(2)
    audio_player.stop()
    audio_player.play_file("../sounds/beep.wav")

    source,item = signal_queue.get()
    print(f"{source}:{item}")
    
    audio_player.kill()
    audio_player.join()