[Garage Door Controller](https://github.com/andrewshilliday/garage-door-controller)
======================

Monitor and control your garage doors from the web via a Raspberry Pi.

![Screenshot from the controller app][1] &nbsp; ![Screenshot from the controller app][3]

Overview:
---------

This project provides software and hardware installation istructions for monitoring and controlling your garage doors remotely (via the web or a smart phone). The software is designed to run on a [Raspberry Pi](www.raspberrypi.org), which is an inexpensive ARM-based computer, and supports:
* Monitoring of the state of the garage doors (indicating whether they are open, closed, opening, or closing)
* Remote control of the garage doors
* Timestamp of last state change for each door
* Logging of all garage door activity

Requirements:
-----

**Hardware**
* [Raspberry Pi](www.raspberrypi.org)
* Micro USB charger (1.5A preferable)
* [USB WiFi dongle](http://amzn.com/B003MTTJOY) (If connecting wirelessly)
* 8 GB SD Card
* Relay Module, 1 channel per garage door (I used [SainSmart](http://amzn.com/B0057OC6D8 ), but there are [other options](http://amzn.com/B00DIMGFHY) as well)
* [Magnetic Contact Switch](http://amzn.com/B006VK6YLC) (one per garage door)
* [Female-to-Female jumper wires](http://amzn.com/B007XPSVMY) (you'll need around 10)

**Software**
* [Raspian](http://www.raspbian.org/) 
* Python Twisted web module

Hardware Setup:
------

*Step 1: Install the magnetic contact switches:*

The contact switches are the sensors that the raspberry pi will use to recognize whether the garage doors are open or shut.  You need to install one on each door so that the switch is *closed* when the garage doors are closed.  Attach the end without wire hookups to the door itself, and the other end (the one that wires get attached to) to the frame of the door in such a way that they are next to each other when the garage door is shut.  There can be some space between them, but they should be close and aligned properly, like this:

![Sample closed contact switch][2]

*Step 2: Install the relays:*

The relays are used to mimic a push button being pressed which will in turn cause your garage doors to open and shut.  Each relay channel is wired to the garage door opener identically to and in parallel with the existing push button wiring.  You'll want to consult your model's manual, or experiment with paper clips, but it should be wired somewhere around here:

![Wiring the garage door opener]
    
You'll now have two wires coming out of the garage door opener, which you'll need to connect to a relay (one relay for each channel). 

Software Installation:
-----

1. **Install [Raspian](http://www.raspbian.org/) onto your Raspberry Pi**
    1. [Tutorial](http://www.raspberrypi.org/wp-content/uploads/2012/12/quick-start-guide-v1.1.pdf)
    2. [Another tutorial](http://www.andrewmunsell.com/blog/getting-started-raspberry-pi-install-raspbian)
    3.  [And a video](http://www.youtube.com/watch?v=aTQjuDfEGWc)!
2. **Configure your WiFi adapter** (if necessary).
    
    - [Follow this tutorial](http://www.frodebang.com/post/how-to-install-the-edimax-ew-7811un-wifi-adapter-on-the-raspberry-pi)
    - [or this one](http://www.youtube.com/watch?v=oGbDawnqbP4)

    *From here, you'll need to be logged into your RPi (e.g., via SSH).*

3. **Install the python twisted module** (used to stand up the web server):

    `sudo apt-get install python-twisted`
    
4. **Install the controller application**
        
    I just install it to ~/pi/garage-door-controller.  You can install it anywhere you want but make sure to adapt these instructions accordingly. You can obtain the code via SVN by executing the following:
    
    `sudo apt-get install subversion`

    `svn checkout https://github.com/andrewshilliday/garage-door-controller ~pi/garage-door-controller`
    
    That's it; you don't need to build anything.

5.  **Edit `config.json`**
    
    You'll need one configuration entry for each garage door.  The settings are fairly obvious, but are defined as follows:
    - **name**: The name for the garage door as it will appear on the controller app.
    - **relay_pin**: The GPIO pin connecting the RPi to the relay for that door.
    - **state_pin**: The GPIO pin conneting to the contact switch.
    - **approx_time_to_close**: How long the garage door typically takes to close.
    - **approx_time_to_open**: How long the garage door typically takes to open.
    
6.  **Set to launch at startup**

    Simply add the following line to your /etc/rc.local file, just above the call to `exit 0`:
    
    `(cd ~pi/garage-door-controller; python controller.py)&`
    
    
  [1]: http://i.imgur.com/rDx9YIt.png
  [2]: http://i.imgur.com/vPHx7kF.png
  [3]: http://i.imgur.com/bfjx9oy.png
