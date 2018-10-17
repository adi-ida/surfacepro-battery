# Battery stats for Surface Pro 2017

![](https://raw.githubusercontent.com/adi-ida/surfacepro-battery/master/battery_stats.png)

Been using [jakeday's](https://github.com/jakeday/linux-surface) excellent kernel for my Surface Pro 2017.

Only 1 thing was stopping me from using my Surface as my daily driver and that was battery stats. It was frsutrating to have it turn off without any warning. I noticed a proof of concept [here](https://gist.github.com/qzed/01a93568efb863f1b7887f0f375c03fc) and decided to help myself to it and put some stats on the wingpanel. 

How to use it 

Download the files
Add these 2 lines to your /etc/crontab (change the user and location accordingly) 
```
*/10 * * * * root /usr/bin/python3 /home/adi/battery-stats/batterydump.py bat1.pretty
* * * * * adi export DISPLAY=:0; /usr/bin/python3 /home/adi/battery-stats/batteryindicator.py
```

And that is pretty much it.

You should have battery stats running on your wingpanel. It currently refreshes every 10 minutes. That can be changed by editing the cron( setting it to a very high frequency like every minute causes issues) 
