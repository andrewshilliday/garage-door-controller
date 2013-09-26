import time
# import RPi.GPIO as gpio

from twisted.internet import task
from twisted.internet import reactor
# from twisted.protocols.basic import LineReceiver
# from twisted.internet.protocol import Factory
from twisted.web import server, resource, http, static
# import webserver
from twisted.web.static import File
from twisted.python import log
from twisted.web.resource import Resource
import json

class Door(object):
    last_action = None
    last_action_time = None
    

    def __init__(self, name, config):
        self.name = name
        self.relay_pin = config['relay_pin']
        self.state_pin = config['state_pin']
        self.time_to_close = config.get('time_to_close', 10)
        self.time_to_open = config.get('time_to_open', 10)
#         gpio.setup(self.relay_pin, gpio.OUT)
#         gpio.setup(self.state_pin, gpio.IN, pull_up_down=gpio.PUD_UP)        
#         gpio.output(self.relay_pin, True)
        
    def get_state(self):
        if False: # gpio.input(self.state_pin) == 0:
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
        
#         gpio.output(self.relay_pin, False)
        time.sleep(0.2)
#         gpio.output(self.relay_pin, True)

class Controller():
    def __init__(self, config):
#         gpio.setwarnings(False)
#         gpio.cleanup()
#         gpio.setmode(gpio.BCM)
        self.config = config
        self.doors = [Door(n,c) for (n,c) in config.items()]
        self.updateHandler = UpdateHandler(self)
        for door in self.doors:
            door.last_state = 'unknown'
            door.last_state_time = time.time()
            
    def status_check(self):
        for door in self.doors:
            new_state = door.get_state()
            if (door.last_state != new_state):
                print '%s: %s => %s' % (door.name, door.last_state, new_state)
                door.last_state = new_state
                door.last_state_time = time.time()
                self.updateHandler.handle_updates()

    def toggle(self, name):
        for d in self.doors:
            if d.name == name:
                d.toggle_relay()
                return
        
    def get_updates(self, lastupdate):
        return [(d.name, d.last_state) 
                for d in self.doors 
                if d.last_state_time >= lastupdate]

    def run(self):
        task.LoopingCall(self.status_check).start(0.5)
        root = File('www')
        root.putChild('update', self.updateHandler)
        site = server.Site(root)
                
        reactor.listenTCP(8080, site)  # @UndefinedVariable
        reactor.run()  # @UndefinedVariable

class UpdateHandler(Resource):
    isLeaf = True
    def __init__(self, controller):
        Resource.__init__(self)
        self.delayed_requests = []
        self.controller = controller
    
    def handle_updates(self):
        for request in self.delayed_requests:
            updates = self.controller.get_updates(request.lastupdate)
            if updates != []:
                self.send_updates(request, updates)
                self.delayed_requests.remove(request);
    
    def format_updates(self, request, update):
        response = json.dumps({'timestamp': int(time.time()), 'update':update})
        if hasattr(request, 'jsonpcallback'):
            return request.jsonpcallback +'('+response+')'
        else:
            return response
            
    def send_updates(self, request, updates):
        request.write(self.format_updates(request, updates))
        request.finish()
    
    def render(self, request):
        # set the request content type
        request.setHeader('Content-Type', 'application/json')
        
        # set args
        args = request.args
       
        # set jsonp callback handler name if it exists
        if 'callback' in args:
            request.jsonpcallback =  args['callback'][0]
           
        # set lastupdate if it exists
        if 'lastupdate' in args:
            request.lastupdate =  args['lastupdate'][0]
        else:
            request.lastupdate = 0
            
        # Can we accommodate this request now?
        updates = controller.get_updates(request.lastupdate)
        if updates != []:
            return self.format_updates(request, updates)
             
        self.requests.append(request)
        
        # tell the client we're not done yet
        return server.NOT_DONE_YET
       
if __name__ == '__main__':
    config = {'Left Door' : 
              {'relay_pin': 17,
               'state_pin': 23,
               'approx_time_to_close' : 10,
               'approx_time_to_open': 10}}

    controller = Controller(config)
    controller.run()
              
    
