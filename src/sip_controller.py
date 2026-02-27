# sip_controller.py
#
# Module whose job it is to make and receive phone calls.

import pexpect
from threading import Thread, Event
from queue import Queue, Empty
from enum import StrEnum, Enum
from argparse import ArgumentParser
import logging
from time import sleep
import sys
from datetime import datetime

_FAIL_PATTERN = '.*terminate call'
_TERMINATE_PATTERN = '.*Call with .* terminated'
_REGISTERED_PATTERN = 'registered successfully'
_ESTABLISHED_PATTERN = '.*Call established'
_CALL_TIMEOUT_SEC = 60.0

class SipCommand(StrEnum):
    Dial="d"
    Hangup="b"
    Accept="a"
    Quit="q"

class SipState(Enum):
    STARTUP=0
    READY=1
    DIALING=2
    ON_CALL=3
    

class SipInterrupts(Enum):
    IncomingCall=1
    CallHangup=2
        

class SipController(Thread):
    def __init__(self, output_queue:Queue):
        super().__init__()
        self._command_queue = Queue()
        self._output_queue = output_queue
        self._sip_client = None
        self._kill_event = Event()
        self.name = "SipController"
        self._state = SipState.STARTUP
    
    def send_item(self, item:str):
        """Sends an item to the output queue

        Args:
            item (str): Thing you want sent to the controller
        """
        self._output_queue.put(('SIP', item))
    
    def run(self):
        self._sip_client = pexpect.spawn('baresip', encoding='utf-8')
        self._sip_client.logfile = sys.stdout
        dial_start = datetime.now()
        
        while(not self._kill_event.is_set()):
            
            # Waiting for ready signal
            if( self._state == SipState.STARTUP ):
                try:
                    self._sip_client.expect(_REGISTERED_PATTERN, timeout=10)
                except pexpect.TIMEOUT as e:
                    logging.warning("sip client failed to register. Sorry")
                    self._kill_event.set()
                    continue
                
                self._state = SipState.READY
                self.send_item(self._state.name)
                continue
            
            # Listen for a command before entering the state machine
            try:
                cmd,arg = self._command_queue.get_nowait()
            except Empty as e:
                pass
            else:
                if( cmd == SipCommand.Dial ):
                    # Only valid in READY state
                    if( self._state in [SipState.READY]):
                        logging.info(f"Sending dial command {arg}")
                        cmd_str = f"{cmd} {arg}"
                        print(f"Sending str '{cmd_str}'")
                        self._sip_client.sendline(cmd_str)
                        self._state = SipState.DIALING
                        dial_start = datetime.now()
                        
                elif( cmd == SipCommand.Hangup ):
                    # only has meaning for DIALING and ON_CALL
                    if( self._state in [SipState.DIALING, SipState.ON_CALL] ):
                        self._do_hangup()
                    else:
                        logging.warning(f"Received {cmd} in {self._state}")
                else:
                    logging.debug(f"Receivd {cmd}, {arg} from command queue")
            
            if( self._state == SipState.READY ):
                # wait for a call
                sleep(1.0)
            
            # Waiting to connect
            elif( self._state == SipState.DIALING ):
                try:
                    response = self._sip_client.expect([_ESTABLISHED_PATTERN, _FAIL_PATTERN], timeout=1.0)
                except pexpect.TIMEOUT as e:
                    if( (datetime.now() - dial_start).total_seconds() > _CALL_TIMEOUT_SEC ):
                        logging.info("Call failed, hanging up")
                        self._command_queue.put((SipCommand.Hangup, None))
                    else:
                        logging.debug(f"Waiting {_CALL_TIMEOUT_SEC - (datetime.now() - dial_start).total_seconds()} more seconds")
                else:
                    if( response == 0 ):
                        self._state = SipState.ON_CALL
                    elif( response == 1 ):
                        logging.warning("Call failed")
                        self._state = SipState.READY
            
            # Connected waiting for terminate
            elif( self._state == SipState.ON_CALL ):
                try:
                    self._sip_client.expect(_TERMINATE_PATTERN, timeout=1.0)
                except pexpect.TIMEOUT as e:
                    logging.debug("Still on the call")
                else:
                    logging.debug("Call terminated.")
                    self._state = SipState.READY
            
        logging.debug("Looks like we're dead")
        self._sip_client.sendline(SipCommand.Quit.value)
        self._sip_client.expect('Quit')
        sleep(2)
        
    def kill(self):
        """Kill this thread and the associated process
        """
        self._kill_event.set()
    
    def hangup(self):
        """Public hangup function
        """
        self._command_queue.put((SipCommand.Hangup, None))
    
    def _do_hangup(self):
        """Private hangup function which does the hanging up
        """
        logging.debug("Hanging up")
        self._sip_client.sendline(SipCommand.Hangup.value)
        self._sip_client.expect(_TERMINATE_PATTERN)
        self._state = SipState.READY
        
    def dial(self, number:str):
        """Dial the given number

        Args:
            number (str): Number to dial
        """
        self._command_queue.put((SipCommand.Dial, number))

def main():
    parser = ArgumentParser()
    parser.add_argument("test_number", type=str, help="10-digit number to call for a test.")
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(level=logging.DEBUG)
    
    queue = Queue()
    controller = SipController(queue)
    controller.start()
    
    source,item = queue.get()
    if( source != "SIP" or item != "READY" ):
        logging.error(f"Expected (SIP,ready) got ({source},{item})")
        controller.kill()
        controller.join()
        return
    else:
        logging.info(f"SIP ready, dialing {args.test_number}")
        sleep(2.0)
        controller.dial(args.test_number)
    
    logging.info("Sleeping 20 seconds and hanging up")
    sleep(20)
    controller.hangup()
    controller.kill()
    controller.join()
    
    # try:
    #     source,item = queue.get(timeout=30.0)
    # except Empty:
    #     logging.info("Received nothing in return")
    # finally:
    #     controller.kill()
    #     controller.join()

if( __name__ == "__main__" ):
    main()