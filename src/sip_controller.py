# sip_controller.py
#
# Module whose job it is to make and receive phone calls.

import subprocess
from threading import Thread, Event
from queue import Queue
from enum import StrEnum, Enum
import select
from argparse import ArgumentParser
import logging
import io
from time import sleep

class SipCommand(StrEnum):
    Dial="d"
    Hangup="b"
    Accept="a"
    Quit="q"

class SipInterrupts(Enum):
    IncomingCall=1
    CallHangup=2

class SipListener(Thread):
    """Thread to listen to the stdout from the sip client
    """
    def __init__(self, output_queue:Queue, sip_stdout):
        super().__init__("SipListener")
        self._output_queue = output_queue
        self._sip_buffer = io.BufferedReader(sip_stdout)
        self._keep_going = True
        self._kill_event = Event()
    
    def run(self):
        while(self._keep_going):
            
            
            readable, writable, exceptional = select.select([self._kill_event, self._sip_buffer], [], [])
            for input in readable:
                
                # time to kill the thread
                if(input == self._kill_event):
                    self._keep_going = False
                    self._sip_buffer.close()
                
                elif(input == self._sip_buffer):
                    print(input.readline())
    
    def kill(self):
        self._keep_going
        

class SipController(Thread):
    def __init__(self, output_queue:Queue):
        super().__init__()
        self._command_queue = Queue()
        self._output_queue = output_queue
        self._sip_client = None
        self._sip_output = None
        self._sip_input = None
        self._kill_event = Event()
        self.name = "SipController"
    
    def run(self):
        self._sip_client = subprocess.Popen(["baresip"],
                                            stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE,
                                            bufsize=128)
        self._sip_output = self._sip_client.stdout
        self._sip_error = self._sip_client.stderr
        self._sip_input = self._sip_client.stdin
        
        while(not self._kill_event.set()):
            
            readable, writeable, exceptional = select.select([self._sip_output, self._sip_error], [], [], 0.5)
            
            # Deal with our readable stuff
            for input in readable:
                if( input == self._kill_event ):
                    logging.debug("SipController received kill command. Killing the applicaiton")
                    self._sip_input.write(f"{SipCommand.Quit.value}".encode())
                    self._sip_output.close()
                    break
                
                elif( input == self._sip_output ):
                    for line in iter(self._sip_output.readline, b''):
                        print(f"stdout: {line}")
                
                elif( input == self._sip_error ):
                    for line in iter(self._sip_error.readline, b''):
                        print(f"stderr: {line.decode('utf-8')}")
                        
                    
            # Deal with writable stuff
            for output in writeable:
                print("Not really sure what's going on here")
            
            print("going back around")
        
        print("Looks like we're dead")
        
    def kill(self):
        """Kill this thread and the associated process
        """
        self._kill_event.set()
    
    def dial(self, number:str):
        self._command_queue.put((SipCommand.Dial, number))

def main():
    parser = ArgumentParser()
    parser.add_argument("test_number", type=str, help="10-digit number to call for a test.")
    args = parser.parse_args()
    
    queue = Queue()
    controller = SipController(queue)
    controller.start()
    
    sleep(5.0)
    controller.kill()
    return
    
    source,item = queue.get()
    if( source != "SIP" or item != "ready" ):
        logging.error(f"Expected (SIP,ready) got ({source},{item})")
        controller.kill()
        controller.join()
        return

if( __name__ == "__main__" ):
    main()