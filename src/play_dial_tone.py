# play_dial_tone.py
#
# Plays a dial tone on a loop

from pathlib import Path
import sounddevice as sd
import soundfile as sf
import wave
from threading import Thread, Event
import time
import logging
import argparse

_DIAL_TONE_FILE = Path( "../sounds/dial_tone_generated_5s.wav" )
_JOIN_WAIT_TIME = 10

class DialTone(Thread):

    def __init__(self, stay_alive:Event, device:int ) -> None:
        """Initialize the dialtone class 

        Args:
            stay_alive (Event): An event to monitor for when to stop playing and die
        """
        super().__init__()
        self.stay_alive = stay_alive
        self.device = device
    
    def run(self) -> None:
        """Play a dial tone in a continuous loop until we die
        """
        logging.debug("DialTone: Reading file")
        try:
            data, fs = sf.read(_DIAL_TONE_FILE, always_2d=True)

            current_frame = 0

            def callback(outdata, frames, time, status):
                nonlocal current_frame
                if( status ):
                    print(status)
                chunksize = min(len(data) - current_frame, frames)
                outdata[:chunksize] = data[current_frame:current_frame + chunksize]
                if chunksize < frames:
                    outdata[chunksize:] = 0
                    raise sd.CallbackStop()
                current_frame += chunksize
                # if( len(data) - current_frame < 2000 ):
                #     logging.debug( "Only {} bytes left, let's go back to thebeginning ".format(len(data)-current_frame))
                #     current_frame = 0
                #     #raise sd.CallbackStop()
                # else:
                #     current_frame += chunksize

            logging.debug("DialTone: creating stream using device {}".format(self.device))
            logging.debug("Data.shape: {}".format(data.shape))
            stream = sd.OutputStream(
                samplerate=fs,
                channels=data.shape[1],
                device=self.device,
                callback=callback,
                finished_callback=self.stay_alive.set)
            
            logging.debug("DialTone: opening stream")
            with stream:
                self.stay_alive.wait()
        except Exception as e:
            logging.debug( type(e).__name__ + ":" + str(e) )
            self.join()

def int_or_str(text):
    try:
        return int(text)
    except ValueError:
        return text

# Test this capability
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--device",type=int_or_str,help="Audio device to use", default=1)
    parser.add_argument("--play_time",type=float,help="how long to play the dial tone",default=10.0)
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.DEBUG)

    kill_dial_tone = Event()
    print( "Instantiating DialTone" )
    dial_tone = DialTone(kill_dial_tone, args.device)
    print( "Starting DialTone" )
    dial_tone.start()

    print("Sleepign {} seconds".format(args.play_time))
    time.sleep(args.play_time)

    print("Setting kill event")
    kill_dial_tone.set()
    print("Joining DialTone")
    dial_tone.join(_JOIN_WAIT_TIME)
