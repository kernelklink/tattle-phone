# tattle_core.py
#
# Sits in the middle and keeps everything running

import RPi.GPIO as GPIO
from hook_monitor import HookMonitor, HookState
from dial_monitor import DialMonitor
from voice_recorder import VoiceRecorder
from audio_player import AudioPlayer
import argparse
from queue import Queue, Empty
from threading import Event
import logging
import time
import subprocess
import shutil
import enum
from os import scandir
import re
from datetime import datetime
from pathlib import Path

_RECORDING_DIR = "../tattles"
_RECORDING_RE = re.compile( r"(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)_(?P<hour>\d\d)(?P<minute>\d\d)(?P<second>\d\d)\.wav")

_PLAYBACK_TEXT = "Tattled on {month} {day} at {hour} {minute} {am_pm}"

# Audio files
_BEEP_WAV = "../sounds/beep.wav"

class TattleState(enum.Enum):
    TATTLE_IDLE=1
    TATTLE_MENU_ROOT=2
    TATTLE_RECORD=3
    TATTLE_PLAYBACK=4

class TattleRootMenu(enum.Enum):
    ROOT_MENU_RECORD=1
    ROOT_MENU_PLAYBACK=2


_HOOK_TIMEOUT_SEC = 0.1
_JOIN_TIMEOUT_SEC = 10

_SPEECH_UTIL = shutil.which('espeak-ng')

def play_text(text_to_speak:str):
    """Plays the specified text from the speaker

    Args:
        text_to_speak (str): String to convert to speech
    """
    args = [_SPEECH_UTIL, 
            "-ven-us+f2",
            text_to_speak]
    subprocess.run(args)

def play_recordings():
    files = list(scandir(_RECORDING_DIR))
    files = sorted( files, key=lambda x: x.stat().st_mtime, reverse=True)

    for f in files:
        match = _RECORDING_RE.match(f.name)
        if( not match ):
            continue

        hour = match.group('hour')
        am_pm = "A.M."
        if( int(hour) > 12 ):
            hour = str(int(hour) - 12)
            am_pm = "P.M."

        # Construct intro
        text = _PLAYBACK_TEXT.format(
            month=match.group('month'),
            day=match.group('day'),
            hour=hour,
            minute=match.group('minute'),
            am_pm=am_pm
        )
        # Play intro and message
        play_text(text)
        time.sleep(0.1)
        
def get_filename() -> str:
    """Get a filename with the current time embedded

    Returns:
        str: Filanme of the format YYYY-MM-DD_HHMMSS.wav
    """
    dt = datetime.now()
    return dt.strftime("%Y-%m-%d_%H%M%S") + ".wav"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hook_pin", help="GPIO pin where the hook circuit is connected", type=int, default=12)
    parser.add_argument("--dial_pin", help="GPIO pin where the dial circuit is connected", type=int, default=16)
    args = parser.parse_args()

    # Setup GPIO
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(args.hook_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(args.dial_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Setup logging
    logging.basicConfig(level=logging.DEBUG)

    # Setup inputs
    my_input_queue = Queue()

    # Instantiate the hook monitor
    hook_monitor = HookMonitor(args.hook_pin, my_input_queue)
    hook_input_queue = hook_monitor.input_queue()
    hook_monitor.start()
    
    # Instantiate the dial monitor
    dial_monitor = DialMonitor(args.dial_pin, my_input_queue)
    dial_input_queue = dial_monitor.input_queue()
    dial_monitor.start()

    # Instantiate the audio player
    audio_player = AudioPlayer(my_input_queue)
    audio_player.start()

    # Give our threads a moment to start
    time.sleep(1)

    # Make a reference to the recorder
    voice_recorder = None

    # Start the state machine
    state = TattleState.TATTLE_IDLE

    hook_state = hook_monitor.hook_state()
    logging.debug("Initial hookstate = {}".format(hook_state))
    if( hook_state == HookState.HOOK_OFF):
        state = TattleState.TATTLE_MENU_ROOT

    while( 1 ):
        logging.debug(f"Currently in {state.name}")

        if( state == TattleState.TATTLE_IDLE ):
            # Wait for a hook change
            source,item = my_input_queue.get()
            if( source == "HOOK" and item != hook_state ):
                hook_state = item
                logging.debug(f"Changing from {state.name} to {TattleState.TATTLE_MENU_ROOT.name}")
                state = TattleState.TATTLE_MENU_ROOT
                
        elif( state == TattleState.TATTLE_MENU_ROOT ):
            # Playback menu selection
            audio_player.play_text(
                    "To tattle on someone, please dial {record}. To listen to the tattling of others, please dial {playback}" \
                    .format(record=TattleRootMenu.ROOT_MENU_RECORD.value, 
                            playback=TattleRootMenu.ROOT_MENU_PLAYBACK.value) )
            
            # Wait for a number input or hook change
            source,item = my_input_queue.get()
            if( source == "AUDIO" and item == "DONE" ):
                logging.debug("No selection was made, coming back around.")
            else:
                # No matter the input, we want to kill the audio
                audio_player.stop()

            # Phone has been hung up
            if( source == "HOOK" and item != hook_state ):
                # Change state
                hook_state = item
                logging.debug(f"Changing from {state.name} to {TattleState.TATTLE_IDLE.name}")
                state = TattleState.TATTLE_IDLE
            
            # Someone made a selection
            elif( source == "DIAL" ):
                if( item == TattleRootMenu.ROOT_MENU_RECORD.value ):
                    logging.debug(f"Changing from {state.name} to {TattleState.TATTLE_RECORD.name}")
                    state = TattleState.TATTLE_RECORD
                elif( item == TattleRootMenu.ROOT_MENU_PLAYBACK.value ):
                    logging.debug(f"Changing from {state.name} to {TattleState.TATTLE_PLAYBACK.name}")
                    state = TattleState.TATTLE_PLAYBACK
            
        elif( state == TattleState.TATTLE_RECORD ):
            # Create a voice recording
            if( voice_recorder is None ):
                # Play the beep
                audio_player.play_file(_BEEP_WAV)

                filename = Path(_RECORDING_DIR,get_filename())
                logging.debug(f"Creating recording {filename}")
                voice_recorder = VoiceRecorder(filename)
                voice_recorder.start()

            # Wait for a hook change
            while(hook_state != HookState.HOOK_ON ):
                source,item = my_input_queue.get()
                if( source == "HOOK" and item != hook_state ):
                    hook_state = item
                    logging.debug(f"Changing from {state.name} to {TattleState.TATTLE_IDLE.name}")
                    state = TattleState.TATTLE_IDLE
            
            # Kill our recording
            voice_recorder.kill()
            voice_recorder.join()
            voice_recorder = None

        elif( state == TattleState.TATTLE_PLAYBACK ):
            # Start playback thread
            audio_player.play_text(
                "I'm sorry, playback has not yet been enabled on this device. Please tattle on me.")
            

            logging.debug(f"Changing from {state.name} to {TattleState.TATTLE_MENU_ROOT.name}")
            state = TattleState.TATTLE_MENU_ROOT
            # # Wait for a hook change
            # source,item = my_input_queue.get()
            # if( source == "HOOK" and item != hook_state ):
            #     hook_state = item
            #     logging.debug(f"Changing from {state.name} to {TattleState.TATTLE_IDLE.name}")
            #     state = TattleState.TATTLE_IDLE

    # Cleanup
    hook_input_queue.put("KILL")
    hook_monitor.join(_JOIN_TIMEOUT_SEC)
    dial_input_queue.put("KILL")
    dial_monitor.join(_JOIN_TIMEOUT_SEC)
    audio_player.kill()
    audio_player.join()
    GPIO.cleanup()

if __name__ == "__main__":
    main()