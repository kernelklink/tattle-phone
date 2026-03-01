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
    DEAD=-1
    STARTUP=0
    READY=1
    DIALING=2
    ON_CALL=3
    

class SipInterrupts(Enum):
    IncomingCall=1
    CallHangup=2
        

class SipController(Thread):
    def __init__(self, output_queue:Queue, conf_path:str="/etc/opt/baresip/"):
        super().__init__()
        self._command_queue = Queue()
        self._output_queue = output_queue
        self._conf_path = conf_path
        self._sip_client = None
        self._kill_event = Event()
        self.name = "SipController"
        self._state = SipState.STARTUP
    
    def send_item(self, item:any):
        """Sends an item to the output queue

        Args:
            item (str): Thing you want sent to the controller
        """
        self._output_queue.put(('SIP', item))
    
    def change_state(self, target_state:SipState):
        """Change the SipController state to something different

        Args:
            target_state (SipState): State we'd like to change to
        """
        logging.debug(f"Changing from {self._state} to {target_state}")
        self._state = target_state
        self.send_item(target_state)
    
    def run(self):
        self._sip_client = pexpect.spawn(f'baresip -f {self._conf_path}', encoding='utf-8')
        self._sip_client.logfile = sys.stdout
        dial_start = datetime.now()
        
        while(not self._kill_event.is_set()):
            
            # Waiting for ready signal
            if( self._state == SipState.STARTUP ):
                try:
                    self._sip_client.expect(_REGISTERED_PATTERN, timeout=10)
                except pexpect.TIMEOUT as e:
                    logging.warning(f"TIMEOUT: sip client failed to register. Sorry")
                    self._kill_event.set()
                    continue
                except pexpect.EOF as e:
                    logging.warning(f"EOF: SIP client failed to open correctly.")
                    self._kill_event.set()
                    continue
                
                self.change_state(SipState.READY)
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
                        self.change_state(SipState.DIALING)
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
                        logging.info(f"Call failed, hanging up")
                        self._command_queue.put((SipCommand.Hangup, None))
                    else:
                        logging.debug(f"Waiting {_CALL_TIMEOUT_SEC - (datetime.now() - dial_start).total_seconds()} more seconds")
                else:
                    if( response == 0 ):
                        logging.info(f"Call connected")
                        self.change_state(SipState.ON_CALL)
                    elif( response == 1 ):
                        logging.warning(f"Call failed")
                        self.change_state(SipState.READY)
            
            # Connected waiting for terminate
            elif( self._state == SipState.ON_CALL ):
                try:
                    self._sip_client.expect(_TERMINATE_PATTERN, timeout=1.0)
                except pexpect.TIMEOUT as e:
                    # Call continues, no change
                    pass
                else:
                    logging.debug(f"Call terminated.")
                    self.change_state(SipState.READY)
        
        # Move to the DEAD state and attempt to kill the client
        self.change_state(SipState.DEAD)
        logging.debug(f"Looks like we're dead")
        self._sip_client.send(SipCommand.Quit.value)
        try:
            self._sip_client.expect('Quit')
        except pexpect.TIMEOUT as e:
            logging.warning(f"TIMEOUT: while waiting for quit response")
        except pexpect.EOF as e:
            logging.warning(f"EOF: while waiting for quit response.")
        sleep(2)
    
    def ready(self) -> bool:
        """Check if SipController is ready to be used

        Returns:
            bool: True if we're in the READY state
        """
        return (self._state in [SipState.READY])
        
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
        logging.debug(f"Hanging up")
        self._sip_client.send(SipCommand.Hangup.value)
        try:
            self._sip_client.expect(_TERMINATE_PATTERN)
        except pexpect.TIMEOUT:
            logging.warning("Timed out while hanging up.")
        except pexpect.EOF:
            logging.warning("Unexpected EOF while trying to hang up.")
        self.change_state(SipState.READY)
        
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
    
    # Stay on here until a call is received.
    while(1):
        try:
            source,item = queue.get(timeout=30.0)
        except Empty:
            logging.info("Received nothing in return")
        else:
            logging.info(f"Received: {source}:{item}")
            if( item == 'ON_CALL' ):
                logging.info("Sleeping 20 seconds and hanging up")
                sleep(20)
                logging.info("Hanging up")
                controller.hangup()
                break
    
    controller.kill()
    controller.join()
    
    

if( __name__ == "__main__" ):
    main()