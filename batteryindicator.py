# This code is an example for a tutorial on Ubuntu Unity/Gnome AppIndicators:
# http://candidtim.github.io/appindicator/2014/09/13/ubuntu-appindicator-step-by-step.html

import os
import signal
import json

from urllib.request import Request, urlopen, URLError

from gi.repository import Gtk as gtk
from gi.repository import AppIndicator3 as appindicator
from gi.repository import Notify as notify
from pprint import pprint

APPINDICATOR_ID = 'surface-battery'
APPINDICATOR_ID1 = 'surface-battery1'

def main():
    

    with open('/home/adi/Downloads/battery/battery_stats.txt') as f:
        text = f.read()
        json_text=text.replace("'", '"')
        data=json.loads(json_text)
    

    #pprint(data['Percentage'])
 
    indicator = appindicator.Indicator.new(APPINDICATOR_ID, os.path.abspath('/home/adi/Downloads/battery/nothing.png'), appindicator.IndicatorCategory.SYSTEM_SERVICES)
    indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
    indicator.set_label("T: "+data['Remaining'],"")
    indicator.set_menu(build_menu())
    notify.init(APPINDICATOR_ID)

    indicator1 = appindicator.Indicator.new(APPINDICATOR_ID1, os.path.abspath('/home/adi/Downloads/battery/nothing.png'), appindicator.IndicatorCategory.SYSTEM_SERVICES)
    indicator1.set_status(appindicator.IndicatorStatus.ACTIVE)
    indicator1.set_label("B: "+data['Percentage'],"")
    indicator1.set_menu(build_menu())
    notify.init(APPINDICATOR_ID1)
    
    gtk.main()

def build_menu():
    menu = gtk.Menu()
    item_quit = gtk.MenuItem('Quit')
    item_quit.connect('activate', quit)
    menu.append(item_quit)
    menu.show_all()
    return menu

def quit(_):
    notify.uninit()
    gtk.main_quit()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    main()