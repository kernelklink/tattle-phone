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
        self.timeout = timeout
        self.output_queue = output_queue
        self.event = Event()
        self.digit = 0
        self.name="PulseCollector"
    
    def run(self):
        while True:
            # Wait for first pulse
            self.event.wait()

            # Wait for subsequent pulses
            while self.event.is_set():
                self.digit += 1
                self.event.clear()
                self.event.wait(self.timeout)

            # Output the digit to the customer
            logging.debug( "Collected a digit: {} ".format(self.digit))
            self.output_queue.put( self.digit )
            self.digit = 0
    
    def pulse(self):
        logging.debug("Setting the event")
        self.event.set()

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

    def __init__(self, dial_pin, input_queue, output_queue, kill_timeout=5, pulse_timeout=0.15) -> None:
        super().__init__()

        # Config items
        self.dial_pin = dial_pin
        self.kill_timeout = kill_timeout
        self.pulse_timeout = pulse_timeout
        self.name = "DialMonitor"

        # inter-thread comms
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.hook_state = Event()

        # initialize State
        self.digit = 0

        # Create our pulse collector
        self.pulse_collector = PulseCollector(pulse_timeout, self.output_queue)

        # Created our Button Handler
        self.button_handler = ButtonHandler(dial_pin, self.collect_pulses, edge='rising', bouncetime=10)
    
    def collect_pulses(self, pin):
        """Check ths hook position before forwarding off to the pulse collector

        Args:
            pin (int): the GPIO pin that generated the pulse
        """
        if( not self.hook_state.is_set() ):
            logging.debug("Got a pulse, sending to pulse collector.")
            self.pulse_collector.pulse()
        else:
            logging.debug("Ignoring pulses as we're on the hook")
    
    def set_hook_state(self, state):
        if( state ):
            self.hook_state.set()
        else:
            self.hook_state.clear()
    
    def run(self):
        self.running = True
        GPIO.add_event_detect( self.dial_pin, GPIO.BOTH, callback=self.button_handler )

        # Start the pulse collector
        self.pulse_collector.start()
        
        # Wait for someone to kill me
        while self.running:
            item = self.input_queue.get()
            logging.debug("Received message {}".format(item))
            if( item == "KILL" ):
                self.running = False
            else:
                logging.info("Received an unknown message from input_queue: '{}'".format(item))
        
        self.pulse_collector.join()
        logging.info('Exiting...')

if __name__ == "__main__":
    # Setup GPIO
    dial_pin = 16
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(dial_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Run a test to see if we can monitor the hook

    logging.basicConfig(level=logging.INFO)

    dial_input_queue = Queue()
    dial_output_queue = Queue()
    dial_monitor = DialMonitor(dial_pin, dial_input_queue, dial_output_queue, "HOOK_ON")
    dial_monitor.start()

    dial_digits = 0
    logging.info("Metaphorical phone will be on hook for 5 seconds...")
    time.sleep(5)
    logging.info("Picking phone off hook")
    dial_monitor.set_hook_state(False)

    # Collect 5 digits and die
    while( dial_digits < 5 ):
        change = dial_output_queue.get(30)
        dial_digits += 1
        logging.info( "Digit: {}".format(change))
    # dial_input_queue.put("KILL")
    dial_monitor.join()
    GPIO.cleanup()
