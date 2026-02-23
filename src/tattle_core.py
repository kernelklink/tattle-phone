#!/usr/bin/env python3

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
import json

_MONTH_MAP = {
    1:  "January",
    2:  "February",
    3:  "March",
    4:  "April",
    5:  "May",
    6:  "June",
    7:  "July",
    8:  "August",
    9:  "September",
    10: "October",
    11: "November",
    12: "December"
}
_RECORDING_DIR = "/var/lib/tattles"
_RECORDING_RE = re.compile( r"(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)_(?P<hour>\d\d)(?P<minute>\d\d)(?P<second>\d\d)\.wav")

_PLAYBACK_TEXT = "Tattled on {month} {day} at {hour} {minute} {am_pm}"

# Audio files
_BEEP_WAV = "../sounds/beep.wav"

class TattleState(enum.Enum):
    TATTLE_IDLE=1
    TATTLE_MENU_ROOT=2
    TATTLE_RECORD=3
    TATTLE_PLAYBACK=4
    TATTLE_MAKE_CALL=5

class TattleRootMenu(enum.Enum):
    ROOT_MENU_RECORD=1
    ROOT_MENU_PLAYBACK=2
    ROOT_MENU_MAKE_CALL=3

_CONTACTS_FILE = "contacts.json"

_HOOK_TIMEOUT_SEC = 0.1
_JOIN_TIMEOUT_SEC = 10

_SPEECH_UTIL = shutil.which('espeak-ng')

class TattlePhone():

    def change_state(self, new_state:TattleState) -> TattleState:
        logging.debug(f"Changing from {self._state.name} to {new_state.name}")
        self._state = new_state

    @staticmethod
    def get_intro_text(file_name:str) -> str:
        match = _RECORDING_RE.match(file_name)
        if( match is None ):
            return None
        
        # Figure out AM / PM
        hour = match.group('hour')
        am_pm = "A.M."
        if( int(hour) > 12 ):
            hour = str(int(hour) - 12)
            am_pm = "P.M."
        
        # Figure out minute
        minute = int(match.group('minute'))
        minute_str = match.group('minute')
        if(minute == 0):
            minute_str = "o'clock"
        elif(minute < 10 ):
            minute_str = f"O {minute}"
        
        # Construct intro
        intro_text = _PLAYBACK_TEXT.format(
            month=_MONTH_MAP[int(match.group('month'))],
            day=int(match.group('day')),
            hour=hour,
            minute=minute_str,
            am_pm=am_pm
        )
        return intro_text
    
    @staticmethod
    def get_filename() -> str:
        """Get a filename with the current time embedded

        Returns:
            str: Filanme of the format YYYY-MM-DD_HHMMSS.wav
        """
        dt = datetime.now()
        return dt.strftime("%Y-%m-%d_%H%M%S") + ".wav"

    def __init__(self):
        self._my_input_queue = Queue()
        self._state = TattleState.TATTLE_IDLE
        
        # Instantiate the audio player
        self.audio_player = AudioPlayer(self._my_input_queue)
        self.audio_player.start()

        # Instantiate the hook monitor
        self.hook_monitor = HookMonitor(args.hook_pin, self._my_input_queue)
        self.hook_monitor.start()
        
        # Instantiate the dial monitor
        self.dial_monitor = DialMonitor(args.dial_pin, self._my_input_queue)
        self.dial_monitor.start()
        
        # Get contacts
        self.contacts = []
        config_folder = Path(args.config_dir)
        if( config_folder.exists() ):
            contacts_file_path = config_folder.joinpath(_CONTACTS_FILE)
            if( contacts_file_path.exists() ):
                with open( contacts_file_path, "r" ) as contacts_file:
                    try:
                        self.contacts = json.load(contacts_file)
                    except:
                        logging.warning(f"Error importing data from contacts file {contacts_file_path}")
            else:
                logging.warning(f"Contacts file {contacts_file_path} does not exist")
        else:
            logging.warning(f"Config folder {args.config_dir} does not exist")

        # Give our threads a moment to start
        time.sleep(1)

    def run(self):
        # Make a reference to the recorder
        self.voice_recorder = None

        # Start the state machine
        self._state = TattleState.TATTLE_IDLE
        self.hook_state = self.hook_monitor.hook_state()
        logging.debug("Initial hookstate = {}".format(self.hook_state))
        if( self.hook_state == HookState.HOOK_OFF):
            self.change_state(TattleState.TATTLE_MENU_ROOT)
        
        # Let the user know we're ready.
        self.audio_player.play_text("I'm all ears")
        self.audio_player.play_file("../sounds/ready.wav")

        while( 1 ):
            logging.debug(f"Currently in {self._state.name}")

            if( self._state == TattleState.TATTLE_IDLE ):
                # Wait for a hook change
                source,item = self._my_input_queue.get()
                if( source == "HOOK" and HookState(item) != self.hook_state ):
                    self.hook_state = item
                    self.change_state(TattleState.TATTLE_MENU_ROOT)
                else:
                    logging.debug(f"Received Unhandled Event: {source}:{item}")
                    
            elif( self._state == TattleState.TATTLE_MENU_ROOT ):
                # Playback menu selection
                self.audio_player.play_text(
                        "To tattle on someone, please dial {record}. " \
                        "To listen to the tattling of others, please dial {playback}. " \
                        "To make a call, please dial {make_call}. " \
                        .format(record=TattleRootMenu.ROOT_MENU_RECORD.value, 
                                playback=TattleRootMenu.ROOT_MENU_PLAYBACK.value,
                                make_call=TattleRootMenu.ROOT_MENU_MAKE_CALL.value))
                
                # Wait for audio to finish
                source,item = self._my_input_queue.get()
                if( source == "AUDIO" ):
                    logging.debug("No selection was made, coming back around.")
                
                # Phone has been hung up
                elif( source == "HOOK" and HookState(item) != self.hook_state ):
                    logging.debug("Hung up while playing menu, return to idle")
                    self.audio_player.stop()

                    # Change state
                    self.hook_state = item
                    self.change_state(TattleState.TATTLE_IDLE)
                
                # Someone made a selection
                elif( source == "DIAL" ):
                    logging.debug("A number has been dialed.")
                    self.audio_player.stop()

                    # Selected record
                    if( item == TattleRootMenu.ROOT_MENU_RECORD.value ):
                        self.change_state(TattleState.TATTLE_RECORD)
                    
                    # Selected playback
                    elif( item == TattleRootMenu.ROOT_MENU_PLAYBACK.value ):
                        self.change_state(TattleState.TATTLE_PLAYBACK)
                    
                    elif( item == TattleRootMenu.ROOT_MENU_MAKE_CALL.value ):
                        self.change_state(TattleState.TATTLE_MAKE_CALL)
                    
                    else:
                        logging.debug(f"Someone dialed {item}, not valid.")
                else:
                    logging.debug(f"Received Unhandled Event: {source}:{item}")
                
            elif( self._state == TattleState.TATTLE_RECORD ):
                # Create a voice recording
                if( self.voice_recorder is None ):
                    # Play the beep
                    self.audio_player.play_file(_BEEP_WAV)

                    filename = Path(_RECORDING_DIR,self.get_filename())
                    logging.debug(f"Creating recording {filename}")
                    self.voice_recorder = VoiceRecorder(filename)
                    self.voice_recorder.start()

                # Wait for a hook change
                while(self.hook_state != HookState.HOOK_ON ):
                    source,item = self._my_input_queue.get()
                    if( source == "HOOK" and HookState(item) != self.hook_state ):
                        self.hook_state = item
                        self.change_state(TattleState.TATTLE_IDLE)
                    else:
                        logging.debug(f"Received Unhandled Event: {source}:{item}")
                
                # Kill our recording
                self.voice_recorder.kill()
                self.voice_recorder.join()
                self.voice_recorder = None

            elif( self._state == TattleState.TATTLE_PLAYBACK ):
                destination_state = self.playback()
                self.change_state(destination_state)
        
            elif( self._state == TattleState.TATTLE_MAKE_CALL ):
                # create call menu and playback
                menu = ""
                for i,contact in enumerate(self.contacts):
                    menu += f"To call {contact['name']}, please dial {i+1}. "
                self.audio_player.play_text(menu)
                
                # Wait for input
                source,item = self._my_input_queue.get()
                if( source == "HOOK" and HookState(item) != self.hook_state ):
                    self.hook_state = item
                    self.change_state(TattleState.TATTLE_IDLE)
                    self.audio_player.stop()
                elif( source == "DIAL" ):
                    self.audio_player.stop()
                    
                    # Check value
                    contact_index = item - 1
                    if( contact_index < 0 or contact_index >= len(self.contacts) ):
                        logging.debug(f"Received unexpected value {item} which is not between 0 and {len(self.contacts)}")
                        self.audio_player.play_text(f"{item} is not a valid selection")
                    else:
                        self.audio_player.play_text(f"I would have called {self.contacts[contact_index]['name']}")
                        self.change_state(TattleState.TATTLE_MENU_ROOT)
                        
                else:
                    logging.debug(f"Received Unhandled Event: {source}:{item}")

        # Cleanup all of our threads
        self.hook_monitor.kill()
        self.hook_monitor.join(_JOIN_TIMEOUT_SEC)
        
        self.dial_monitor.kill()
        self.dial_monitor.join(_JOIN_TIMEOUT_SEC)
        
        self.audio_player.kill()
        self.audio_player.join()
        GPIO.cleanup()
    
    def playback(self) -> TattleState:
        files = list(scandir(_RECORDING_DIR))
        files = sorted( files, key=lambda x: x.name, reverse=True)
        for file in files:
            intro_text = self.get_intro_text(file.name)
            if( intro_text is None ):
                continue
            
            logging.debug("Queuing up text and file to play")
            self.audio_player.play_text(intro_text)
            self.audio_player.play_file(file)
            still_playing = True
            while( still_playing ):
                source,item = self._my_input_queue.get()
                if( source == "HOOK" and HookState(item) != self.hook_state ):
                    logging.debug("Phone was hung up, stopping audio")
                    self.audio_player.stop()
                    self.hook_state = item
                    return TattleState.TATTLE_IDLE
                elif( source == "AUDIO" ):
                    logging.debug("Looks like the audio player is free, let's move on!")
                    still_playing = False
                elif( source == "DIAL" and item == 1 ):
                    logging.debug("Skipping!")
                    self.audio_player.stop()
                    still_playing = False
                else:
                    logging.debug(f"Received Unhandled Event: {source}:{item}")
        
        return TattleState.TATTLE_MENU_ROOT

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hook_pin", help="GPIO pin where the hook circuit is connected", type=int, default=12)
    parser.add_argument("--dial_pin", help="GPIO pin where the dial circuit is connected", type=int, default=16)
    parser.add_argument("--config_dir", help="Directory where configuration files can be found. Defaults to /etc/opt/tattle", type=str, default="/etc/opt/tattle")
    args = parser.parse_args()

    # Setup GPIO
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(args.hook_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(args.dial_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Setup logging
    logging.basicConfig(level=logging.DEBUG)

    # Start the phone
    tattle_phone = TattlePhone()
    tattle_phone.run()