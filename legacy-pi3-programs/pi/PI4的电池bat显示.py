#!/usr/bin/env python

import time
import sys
import i2c
import os
iic = i2c.IICADD(1,0x66)
if(iic.read_01()<100):
    bat_value=iic.read_01()
a=0
b=0
bat_min=100
bat_max=0
bat_temp=0


while True:
   # print ("test iic=\t\t%s"% iic.read_01())
    bat_value=iic.read_01()
    if(bat_value<101):
        
        b=b+1
        if(b<11):
            bat_temp=bat_value+bat_temp
            if(bat_value>bat_max):
                bat_max=bat_value
            if(bat_value<bat_min):
                bat_min=bat_value
        else:
            bat_temp=bat_temp-bat_max
            bat_temp=bat_temp-bat_min
            bat_temp=bat_temp/8
            b=0
            bat_max=0
            bat_min=101


            if(bat_temp<100):
                if(bat_temp>10):
                    a=a-1
                    print ("bat_value=",bat_temp,"%")
                else:
                    print("low battery")
                    print("Waitting 60s.......,then poweroff ")
                    a=a+1
                    # if(a>20):
                    #     os.system("poweroff")
    time.sleep(3)