#!/usr/bin/env python3

# dial_monitor.py
#
# A class to monitor the dial as it turns and report new digits back to the owner

import RPi.GPIO as GPIO
from queue import Queue
from threading import Thread, Lock, Timer, Event
import logging
import time

class PulseCollector(Thread):
    def __init__(self, timeout, output_queue):
        super().__init__(daemon=True)
        self._timeout = timeout
        self._output_queue = output_queue
        self._event = Event()
        self._digit = 0
        self._keep_going = True
        self.name="PulseCollector"
    
    def run(self):
        while self._keep_going:
            # Wait for first pulse
            if( self._event.wait(timeout=2) ):

                # Wait for subsequent pulses
                while self._event.is_set():
                    self._digit += 1
                    self._event.clear()
                    self._event.wait(self._timeout)

                # Output the digit to the customer
                logging.debug( "Collected a digit: {} ".format(self._digit))
                if( self._digit >= 10 ):
                    logging.debug( f"Correcting {self._digit} to 0")
                    self._digit = 0

                self._output_queue.put( ("DIAL", self._digit) )
                self._digit = 0
    
    def kill(self):
        """Kill this thread
        """
        self._keep_going = False
    
    def pulse(self):
        logging.debug("Setting the event")
        self._event.set()

class ButtonHandler(Thread):
    """Class to act as a software debouncer for the rotary dial.
    """
    def __init__(self, pin, func, edge='both', bouncetime=10):
        super().__init__(daemon=True)
        self.edge = edge
        self.func = func
        self.pin = pin
        self.bouncetime = float(bouncetime)/1000
        self.lastpinval = GPIO.input(self.pin)
        self.lock = Lock()
        self.name="ButtonHandler"

    def __call__(self, *args):
        if not self.lock.acquire(blocking=False):
            return
        t = Timer(self.bouncetime, self.read, args=args)
        t.start()

    def read(self, *args):
        pinval = GPIO.input(self.pin)
        if (
                ((pinval == 0 and self.lastpinval == 1) and
                 (self.edge in ['falling', 'both'])) or
                ((pinval == 1 and self.lastpinval == 0) and
                 (self.edge in ['rising', 'both']))
        ):
            self.func(*args)
        self.lastpinval = pinval
        self.lock.release()


class DialMonitor(Thread):
    """A class to monitor the phone dial and report back new digits as they arrive
    """
    
    __KILL_CODE = -1

    def __init__(self, dial_pin:int, output_queue:Queue, kill_timeout=5, pulse_timeout=0.15) -> None:
        super().__init__()

        # Config items
        self.dial_pin = dial_pin
        self.kill_timeout = kill_timeout
        self.pulse_timeout = pulse_timeout
        self.name = "DialMonitor"

        # inter-thread comms
        self._input_queue = Queue()
        self._output_queue = output_queue

        # initialize State
        self.digit = 0

        # Create our pulse collector
        self.pulse_collector = PulseCollector(pulse_timeout, self._output_queue)

        # Created our Button Handler
        self.button_handler = ButtonHandler(dial_pin, self._collect_pulses, edge='rising', bouncetime=10)
    
    def kill(self):
        """Tell this guy to terminate.
        """
        self._input_queue.put(DialMonitor.__KILL_CODE)

    def _collect_pulses(self, pin):
        """Forwarding off to the pulse collector

        Args:
            pin (int): the GPIO pin that generated the pulse
        """
        logging.debug("Got a pulse, sending to pulse collector.")
        self.pulse_collector.pulse()
    
    def run(self):
        self.running = True
        GPIO.add_event_detect( self.dial_pin, GPIO.BOTH, callback=self.button_handler )

        # Start the pulse collector
        self.pulse_collector.start()
        
        # Wait for someone to kill me
        while self.running:
            item = self._input_queue.get()
            logging.debug("Received message {}".format(item))
            if( item == DialMonitor.__KILL_CODE ):
                self.running = False
            else:
                logging.info("Received an unknown message from input_queue: '{}'".format(item))
        
        # Clean up our 2 threads
        self.pulse_collector.kill()
        self.pulse_collector.join()
        logging.info('Exiting...')

if __name__ == "__main__":
    # Setup GPIO
    dial_pin = 16
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(dial_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Run a test to see if we can monitor the hook
    logging.basicConfig(level=logging.INFO)

    dial_output_queue = Queue()
    dial_monitor = DialMonitor(dial_pin, dial_output_queue)
    dial_monitor.start()

    # Collect 5 digits and die
    logging.info("Capturing 5 digits and then shutting down")
    dial_digits = 0
    while( dial_digits < 5 ):
        source,change = dial_output_queue.get(30)
        dial_digits += 1
        logging.info( "{} Digit: {}".format(source,change))
    dial_monitor.kill()
    dial_monitor.join()
    GPIO.cleanup()
