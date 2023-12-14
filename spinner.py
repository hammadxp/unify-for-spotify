from itertools import cycle
from shutil import get_terminal_size
from threading import Thread
from time import sleep


class Spinner:
    def __init__(self, msg="Loading...", end='', timeout=0.1, variant='spotify'):
        self.msg = msg
        self.end = end
        self.timeout = timeout

        if variant == 'spotify':
            self.steps = ["[∙∙∙]","[●∙∙]","[∙●∙]","[∙∙●]","[∙∙∙]"]
        elif variant == 'tetris':
            self.steps = ["⢿", "⣻", "⣽", "⣾", "⣷", "⣯", "⣟", "⡿"]
        elif variant == 'circle':
            self.steps = ["◜","◝","◞","◟"]
        elif variant == 'emoji':
            self.steps = ["😐 ","😐 ","😮 ","😮 ","😦 ","😦 ","😧 ","😧 ","🤯 ","💥 ","✨ ","\u3000 ","\u3000 ","\u3000 "]
        
        
        self._thread = Thread(target=self._animate, daemon=True)

        self.done = False

    def start(self):
        self._thread.start()
        return self
    
    def stop(self):
        self.done = True
        cols = get_terminal_size((80, 20)).columns
        print("\r" + " " * cols, flush=True, end="\033[A")

        if self.end != "":
            print(f"\r{self.end}", flush=True, end="")

    def _animate(self):
        for c in cycle(self.steps):
            if self.done:
                break
            print(f"\r\t{c} {self.msg} ", flush=True, end="")
            sleep(self.timeout)

    def __enter__(self):
        self.start()


    def __exit__(self, exc_type, exc_value, tb):
        self.stop()
