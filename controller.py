"""Software to monitor and control garage doors via a raspberry pi."""

import time, syslog, uuid
import smtplib
import RPi.GPIO as gpio
import json
import httplib
import urllib
import subprocess

from twisted.internet import task
from twisted.internet import reactor
from twisted.web import server
from twisted.web.static import File
from twisted.web.resource import Resource, IResource
from zope.interface import implements

from twisted.cred import checkers, portal
from twisted.web.guard import HTTPAuthSessionWrapper, BasicCredentialFactory



class HttpPasswordRealm(object):
    implements(portal.IRealm)

    def __init__(self, myresource):
        self.myresource = myresource

    def requestAvatar(self, user, mind, *interfaces):
        if IResource in interfaces:
            return (IResource, self.myresource, lambda: None)
        raise NotImplementedError()

class Door(object):
    last_action = None
    last_action_time = None
    msg_sent = False
    pb_iden = None

    def __init__(self, doorId, config):
        self.id = doorId
        self.name = config['name']
        self.relay_pin = config['relay_pin']
        self.state_pin = config['state_pin']
        self.state_pin_closed_value = config.get('state_pin_closed_value', 0)
        self.time_to_close = config.get('time_to_close', 10)
        self.time_to_open = config.get('time_to_open', 10)
        self.openhab_name = config.get('openhab_name')
        self.open_time = time.time()
        gpio.setup(self.relay_pin, gpio.OUT)
        gpio.setup(self.state_pin, gpio.IN, pull_up_down=gpio.PUD_UP)
        gpio.output(self.relay_pin, True)

    def get_state(self):
        if gpio.input(self.state_pin) == self.state_pin_closed_value:
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

class Controller(object):
    def __init__(self, config):
        gpio.setwarnings(False)
        gpio.cleanup()
        gpio.setmode(gpio.BCM)
        self.config = config
        self.doors = [Door(n, c) for (n, c) in config['doors'].items()]
        self.updateHandler = UpdateHandler(self)
        for door in self.doors:
            door.last_state = 'unknown'
            door.last_state_time = time.time()

        self.use_alerts = config['config']['use_alerts']
        self.alert_type = config['alerts']['alert_type']
        self.ttw = config['alerts']['time_to_wait']
        if self.alert_type == 'smtp':
            self.use_smtp = False
            smtp_params = ("smtphost", "smtpport", "smtp_tls", "username", "password", "to_email")
            self.use_smtp = ('smtp' in config['alerts']) and set(smtp_params) <= set(config['alerts']['smtp'])
            syslog.syslog("we are using SMTP")
        elif self.alert_type == 'pushbullet':
            self.pushbullet_access_token = config['alerts']['pushbullet']['access_token']
            syslog.syslog("we are using Pushbullet")
        elif self.alert_type == 'pushover':
            self.pushover_user_key = config['alerts']['pushover']['user_key']
            syslog.syslog("we are using Pushover")
        else:
            self.alert_type = None
            syslog.syslog("No alerts configured")

    def status_check(self):
        for door in self.doors:
            new_state = door.get_state()
            if (door.last_state != new_state):
                syslog.syslog('%s: %s => %s' % (door.name, door.last_state, new_state))
                door.last_state = new_state
                door.last_state_time = time.time()
                self.updateHandler.handle_updates()
                if self.config['config']['use_openhab'] and (new_state == "open" or new_state == "closed"):
                    self.update_openhab(door.openhab_name, new_state)
            if new_state == 'open' and not door.msg_sent and time.time() - door.open_time >= self.ttw:
                if self.use_alerts:
                    title = "%s's garage door open" % door.name
                    etime = elapsed_time(int(time.time() - door.open_time))
                    message = "%s's garage door has been open for %s" % (door.name, etime)
                    if self.alert_type == 'smtp':
                        self.send_email(title, message)
                    elif self.alert_type == 'pushbullet':
                        self.send_pushbullet(door, title, message)
                    elif self.alert_type == 'pushover':
                        self.send_pushover(door, title, message)
                    door.msg_sent = True

            if new_state == 'closed':
                if self.use_alerts:
                    if door.msg_sent == True:
                        title = "%s's garage doors closed" % door.name
                        etime = elapsed_time(int(time.time() - door.open_time))
                        message = "%s's garage door is now closed after %s "% (door.name, etime)
                        if self.alert_type == 'smtp':
                            self.send_email(title, message)
                        elif self.alert_type == 'pushbullet':
                            self.send_pushbullet(door, title, message)
                        elif self.alert_type == 'pushover':
                            self.send_pushover(door, title, message)
                door.open_time = time.time()
                door.msg_sent = False

    def send_email(self, title, message):
        if self.use_smtp:
            syslog.syslog("Sending email message")
            config = self.config['alerts']['smtp']
            server = smtplib.SMTP(config["smtphost"], config["smtpport"])
            if (config["smtp_tls"] == "True") :
                server.starttls()
            server.login(config["username"], config["password"])
            server.sendmail(config["username"], config["to_email"], message)
            server.close()

    def send_pushbullet(self, door, title, message):
        syslog.syslog("Sending pushbutton message")
        config = self.config['alerts']['pushbullet']

        if door.pb_iden != None:
            conn = httplib.HTTPSConnection("api.pushbullet.com:443")
            conn.request("DELETE", '/v2/pushes/' + door.pb_iden, "",
                         {'Authorization': 'Bearer ' + config['access_token'], 'Content-Type': 'application/json'})
            conn.getresponse()
            door.pb_iden = None

        conn = httplib.HTTPSConnection("api.pushbullet.com:443")
        conn.request("POST", "/v2/pushes",
             json.dumps({
                 "type": "note",
                 "title": title,
                 "body": message,
             }), {'Authorization': 'Bearer ' + config['access_token'], 'Content-Type': 'application/json'})
        response = conn.getresponse().read()
        print(response)
        door.pb_iden = json.loads(response)['iden']
    def send_pushover(self, door, title, message):
        syslog.syslog("Sending Pushover message")
        config = self.config['alerts']['pushover']
        conn = httplib.HTTPSConnection("api.pushover.net:443")
        conn.request("POST", "/1/messages.json",
                urllib.urlencode({
                    "token": config['api_key'],
                    "user": config['user_key'],
                    "title": title,
                    "message": message,
                }), { "Content-type": "application/x-www-form-urlencoded" })
        conn.getresponse()

    def update_openhab(self, item, state):
        syslog.syslog("Updating openhab")
        config = self.config['openhab']
        conn = httplib.HTTPConnection("%s:%s" % (config['server'], config['port']))
        conn.request("PUT", "/rest/items/%s/state" % item, state)
        conn.getresponse()

    def toggle(self, doorId):
        for d in self.doors:
            if d.id == doorId:
                syslog.syslog('%s: toggled' % d.name)
                d.toggle_relay()
                return

    def get_updates(self, lastupdate):
        updates = []
        for d in self.doors:
            if d.last_state_time >= lastupdate:
                updates.append((d.id, d.last_state, d.last_state_time))
        return updates

    def run(self):
        task.LoopingCall(self.status_check).start(0.5)
        root = File('www')
        root.putChild('st', StatusHandler(self))
        root.putChild('upd', self.updateHandler)
        root.putChild('cfg', ConfigHandler(self))
        root.putChild('upt', UptimeHandler(self))
        
        if self.config['config']['use_auth']:
            clk = ClickHandler(self)
            args={self.config['site']['username']:self.config['site']['password']}
            checker = checkers.InMemoryUsernamePasswordDatabaseDontUse(**args)
            realm = HttpPasswordRealm(clk)
            p = portal.Portal(realm, [checker])
            credentialFactory = BasicCredentialFactory("Garage Door Controller")
            protected_resource = HTTPAuthSessionWrapper(p, [credentialFactory])
            root.putChild('clk', protected_resource)
        else:
            root.putChild('clk', ClickHandler(self))
        site = server.Site(root)
        reactor.listenTCP(self.config['site']['port'], site)  # @UndefinedVariable
        reactor.run()  # @UndefinedVariable

class ClickHandler(Resource):
    isLeaf = True

    def __init__ (self, controller):
        Resource.__init__(self)
        self.controller = controller

    def render(self, request):
        door = request.args['id'][0]
        self.controller.toggle(door)
        return 'OK'

class StatusHandler(Resource):
    isLeaf = True

    def __init__ (self, controller):
        Resource.__init__(self)
        self.controller = controller

    def render(self, request):
        door = request.args['id'][0]
        for d in self.controller.doors:
            if (d.id == door):
                return d.last_state
        return ''

class ConfigHandler(Resource):
    isLeaf = True
    def __init__ (self, controller):
        Resource.__init__(self)
        self.controller = controller

    def render(self, request):
        request.setHeader('Content-Type', 'application/json')

        return json.dumps([(d.id, d.name, d.last_state, d.last_state_time)
                            for d in self.controller.doors])


class UptimeHandler(Resource):
    isLeaf = True
    def __init__ (self, controller):
        Resource.__init__(self)

    def render(self,request):
        request.setHeader('Content-Type', 'application/json')
        uptime = subprocess.check_output(['uptime', '-p']).strip()
        uptime = uptime.replace("up ", "")
        uptime = uptime.split(",")[0].replace(",","").strip()
        if (uptime == "up"):
            uptime = "0 mins"
        return json.dumps("Uptime: " + uptime)
    
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
                self.delayed_requests.remove(request)

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
            request.lastupdate = float(args['lastupdate'][0])
        else:
            request.lastupdate = 0

            #print "request received " + str(request.lastupdate)

        # Can we accommodate this request now?
        updates = self.controller.get_updates(request.lastupdate)
        if updates != []:
            return self.format_updates(request, updates)


        request.notifyFinish().addErrback(lambda x: self.delayed_requests.remove(request))
        self.delayed_requests.append(request)

        # tell the client we're not done yet
        return server.NOT_DONE_YET

def elapsed_time(seconds, suffixes=['y','w','d','h','m','s'], add_s=False, separator=' '):
    """
    Takes an amount of seconds and turns it into a human-readable amount of time.
    """
    # the formatted time string to be returned
    time = []

    # the pieces of time to iterate over (days, hours, minutes, etc)
    # - the first piece in each tuple is the suffix (d, h, w)
    # - the second piece is the length in seconds (a day is 60s * 60m * 24h)
    parts = [(suffixes[0], 60 * 60 * 24 * 7 * 52),
             (suffixes[1], 60 * 60 * 24 * 7),
             (suffixes[2], 60 * 60 * 24),
             (suffixes[3], 60 * 60),
             (suffixes[4], 60),
             (suffixes[5], 1)]

    # for each time piece, grab the value and remaining seconds, and add it to
    # the time string
    for suffix, length in parts:
        value = seconds / length
        if value > 0:
            seconds = seconds % length
            time.append('%s%s' % (str(value),
                                  (suffix, (suffix, suffix + 's')[value > 1])[add_s]))
        if seconds < 1:
            break

    return separator.join(time)

if __name__ == '__main__':
    syslog.openlog('garage_controller')
    config_file = open('config.json')
    controller = Controller(json.load(config_file))
    config_file.close()
    controller.run()
