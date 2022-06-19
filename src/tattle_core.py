# tattle_core.py
#
# Sits in the middle and keeps everything running

import RPi.GPIO as GPIO
from hook_monitor import HookMonitor, HookState
from play_dial_tone import DialTone
from dial_monitor import DialMonitor
import argparse
from queue import Queue
from threading import Event
import logging
import time

_HOOK_TIMEOUT_SEC = 0.1
_JOIN_TIMEOUT_SEC = 10

# Values that we'll use for 

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hook_pin", help="GPIO pin where the hook circuit is connected", type=int, default=12)
    args = parser.parse_args()

    # Setup GPIO
    hook_pin = 12
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(args.hook_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Setup logging
    logging.basicConfig(level=logging.DEBUG)

    # Instantiate the hook monitor
    hook_input_queue = Queue()
    hook_output_queue = Queue()
    hook_monitor = HookMonitor(hook_pin, hook_input_queue, hook_output_queue)
    hook_monitor.start()
    time.sleep(1)

    # Dial tone Player
    dial_tone_player = None
    dial_tone_end = None

    hook_state = hook_monitor.hook_state()
    logging.debug("Initial hookstate = {}".format(hook_state))
    # Simple test to monitor hook changes
    while( 1 ):

        if( hook_state == HookState.HOOK_OFF ):
            logging.debug( "Off the hook!" )

        # See if there's been a change to the hook
        if( not hook_output_queue.empty()):
            hook_change = hook_output_queue.get()
            if( hook_change != hook_state ):
                logging.debug( "Received a hook change, new value is {}".format(HookMonitor.hook_state_to_str(hook_change)))
                hook_state = hook_change

                # The current state machine is just hook on, hook off. When we 
                # change to hook off, start playing the dialtone. When we change
                # to hook on, stop laying the dial tone
                if( hook_state == HookState.HOOK_OFF ):
                    logging.debug("Starting Dialtone")
                    dial_tone_end = Event()
                    dial_tone_player = DialTone(dial_tone_end)
                    dial_tone_player.start()
                else:
                    dial_tone_end.set()
                    logging.debug("Killing Dial Tone")
                    dial_tone_player.join(_JOIN_TIMEOUT_SEC)
                    logging.debug("Dial tone joined")

        
        # Short sleep for this cycle
        time.sleep(0.1)

    # Cleanup
    hook_input_queue.put("KILL")
    hook_monitor.join(_JOIN_TIMEOUT_SEC)
    GPIO.cleanup()

if __name__ == "__main__":
    main()