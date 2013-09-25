import time
import RPi.GPIO as gpio

from twisted.internet import task
from twisted.internet import reactor
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import Factory

class Door(object):
    last_action = None
    last_action_time = None

    def __init__(self, name, config):
        self.name = name
        self.relay_pin = config['relay_pin']
        self.state_pin = config['state_pin']
        self.time_to_close = config.get('time_to_close', 10)
        self.time_to_open = config.get('time_to_open', 10)
        gpio.setup(self.relay_pin, gpio.OUT)
        gpio.setup(self.state_pin, gpio.IN, pull_up_down=gpio.PUD_UP)        
        gpio.output(self.relay_pin, True)
        
    def get_state(self):
        if gpio.input(self.state_pin) == 0:
            return 'closed'
        elif self.last_action == 'open':
            if time.time() - self.last_action_time >= self.time_to_open:
                return 'open'
            else:
                return 'opening'
        elif self.last_action ==  'close':
            if time.time() - self.last_action_time >= self.time_to_close:
                return 'open' # This state indicates a problem
            else:
                return 'closing'
        else:
            return 'open'

    def toggle_relay(self):
        state = self.get_state()
        if (state == 'open'):
            self.last_action = 'close'
            self.last_action_time = time.time()
        elif state == 'closed':
            self.last_action = 'open'
            self.last_action_time = time.time()
        else:
            self.last_action = None
            self.last_action_time = None
        
        gpio.output(self.relay_pin, False)
        time.sleep(0.2)
        gpio.output(self.relay_pin, True)

class Controller():
    def __init__(self, config):
        gpio.setwarnings(False)
        gpio.cleanup()
        gpio.setmode(gpio.BCM)
        self.servers = set()
        self.config = config
        self.doors = [Door(n,c) for (n,c) in config.items()]
        self.last_states = ['unknown' for d in self.doors]
    
    def status_check(self):
        new_states = [d.get_state() for d in self.doors]
        for (d,os,ns) in zip(self.doors, self.last_states, new_states):
            if os != ns:
                print '%s: %s => %s' % (d.name,os,ns)
                for s in self.servers:
                    s.sendLine('%s: %s => %s' % (d.name,os,ns))
        self.last_states = new_states

    def toggle(self, name):
        for d in self.doors:
            if d.name == name:
                d.toggle_relay()
                return

    def run(self):
        lc = task.LoopingCall(self.status_check).start(0.5)
        reactor.listenTCP(8123, ServerFactory(self))
        reactor.run()

class ServerProtocol(LineReceiver):
    def __init__ (self, controller):
        self.controller = controller

    def connectionMade(self):
        self.controller.servers.add(self)

    def connectionLost(self, reason):
        self.controller.servers.remove(self)

    def lineReceived(self, line):
        self.controller.toggle(line)

class ServerFactory(Factory):
    def __init__ (self, controller):
        self.controller = controller

    def buildProtocol(self, addr):
        return ServerProtocol(controller)    
        
    
if __name__ == '__main__':
    config = {'Left Door' : 
              {'relay_pin': 17,
               'state_pin': 23,
               'approx_time_to_close' : 10,
               'approx_time_to_open': 10}}

    controller = Controller(config)
    controller.run()
              
    
