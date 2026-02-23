#!/usr/bin/env python3

# hook_monitor
# 
# Monitors the hook

import RPi.GPIO as GPIO
from queue import Queue
from threading import Thread, Lock
import logging
import time
from enum import IntEnum

class HookState(IntEnum):
    HOOK_ON=0
    HOOK_OFF=1

class HookMonitor(Thread):
    """Monitor the hook switch and signal when the phone is off/on the hook
    """
    __KILL_CODE = -1

    def __init__(self, hook_pin:int, output_queue:Queue, timeout=5) -> None:
        """Constructor for HookMonitor object, assumes that the caller 
        has already setup the GPIO pin, but we still need to setup the 
        interrupts.

        Args:
            hook_pin (int): the GPIO pin number to monitor for the hook switch
            output_queue (Queue): Queue to send output that we receive
        """
        super().__init__()

        # Save some state
        self._hook_pin = hook_pin
        self._input_queue = Queue()
        self._output_queue = output_queue
        self._hook_state = HookState.HOOK_ON
        self._lock = Lock()
        self._timeout = timeout
        self.name="HookMonitor"
    
    def kill(self):
        """Tell this guy to terminate.
        """
        self._input_queue.put(HookMonitor.__KILL_CODE)
    
    def hook_state(self) -> HookState:
        """Return the current hook state.

        Returns:
            bool: True if we're 
        """
        with self._lock:
            return self._hook_state
    
    @staticmethod
    def hook_state_to_str(state:HookState)->str:
        """Convert the given state to a string

        Args:
            state (HookState): The state of the hoook we're interested in

        Returns:
            str: Name of the state, e.g. HOOK_OFF
        """
        if( state == HookState.HOOK_OFF ):
            return "HOOK_OFF"
        elif( state == HookState.HOOK_ON ):
            return "HOOK_ON"
    
    def hook_change(self, pin):
        """Monitor the hook for changes, when it changes report that 
        through the output queue

        Args:
            pin (int): GPIO pin associated with this change in current
        """
        if( self.running ):
            with self._lock:
                self._hook_state = HookState(GPIO.input(pin))
            self._output_queue.put( ("HOOK", self._hook_state) )
            logging.debug("Something changed on the hook, current value is {}".format(self._hook_state))
        else:
            logging.debug("Looks like I'm not running, but I'm getting interrupts")

    
    def run(self):
        """Setup the interrupt for the hook GPIO pin and monitor it, 
        communicating state back to the caller
        """
        self.running = True
        with self._lock:
            self._hook_state = HookState(GPIO.input(self._hook_pin))
        GPIO.add_event_detect( self._hook_pin, GPIO.BOTH, self.hook_change )
        
        # Wait for someone to kill me
        while self.running:
            item = self._input_queue.get()
            if( item == HookMonitor.__KILL_CODE ):
                self.running = False
            else:
                logging.info("Received an unknown message from input_queue: '{}'".format(item))
            
            # sleep for a while
            time.sleep(self._timeout)
            
        logging.info('Exiting...')

if __name__ == "__main__":
    # Setup GPIO
    hook_pin = 12
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(hook_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Run a test to see if we can monitor the hook

    logging.basicConfig(level=logging.DEBUG)

    hook_output_queue = Queue()
    hook_monitor = HookMonitor(hook_pin, hook_output_queue)
    hook_monitor.start()

    hook_changes = 0
    while( hook_changes < 5 ):
        source,change = hook_output_queue.get(30)
        hook_changes += 1
        logging.info( "{} change: {}".format(source,change))
    hook_monitor.kill()
    hook_monitor.join()
    GPIO.cleanup()
