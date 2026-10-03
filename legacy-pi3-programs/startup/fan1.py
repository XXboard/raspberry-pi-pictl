
from gpiozero import Button
import gpiozero
from gpiozero import LED
from time import sleep
fan=LED(13)
while True:
　  temp=open('/sys/class/thermal/thermal_zone0/temp')//读取温度
    temp1=temp.read()
    temp.close()
    temp1=int(temp1)/1000
    if(temp1>45):
       fan.on()
    if(temp1<39):
       fan.off()
    sleep(3)
