import network
import time
import machine
from sh1107 import OLED_1inch3 
from umqtt.simple import MQTTClient

WIFI_SSID = "Human 4.0"
WIFI_PASS = "farid021204"
MQTT_BROKER = "172.20.10.3" 
CLIENT_ID = "NudgeLoop_Bracelet"
TOPIC_SUB = b"nudgeloop/routine"

# --- HARDWARE SETUP ---
led = machine.Pin("LED", machine.Pin.OUT)

buzzer = machine.PWM(machine.Pin(14))
buzzer.duty_u16(0) 


OLED = OLED_1inch3()

# --- TASK & EARCON ---
tasks = [
    {"name": "Make Bed",      "on": 50,  "off": 50,  "freq": 880},  
    {"name": "Stretch",    "on": 800, "off": 200, "freq": 587},  
    {"name": "Brush Teeth",     "on": 300, "off": 300, "freq": 659},  
    {"name": "Drink Water",       "on": 50,  "off": 200, "freq": 988},  
    {"name": "Take Meds",     "on": 250, "off": 250, "freq": 1047} 
]

idx = 0
active_audio = False  
is_beeping = False    
last_toggle_time = time.ticks_ms()

# --- FUNCTIONS ---

def refresh_display(i):
    OLED.fill(0x0000)
    OLED.rect(0, 0, 128, 64, OLED.white)
    OLED.text("MORNING QUEST", 12, 5, OLED.white)
    OLED.line(0, 15, 128, 15, OLED.white)
    if active_audio:
        OLED.text("QUEST:", 5, 25, OLED.white)
        OLED.text(tasks[i]["name"], 5, 40, OLED.white)
    else:
        OLED.text("WAITING FOR", 20, 25, OLED.white)
        OLED.text("HUB SCAN...", 25, 40, OLED.white)
    OLED.show()

def update_buzzer():
    global last_toggle_time, is_beeping
    
    if not active_audio:
        buzzer.duty_u16(0)
        return

    current_task = tasks[idx]
    now = time.ticks_ms()
    wait_time = current_task["on"] if is_beeping else current_task["off"]
    
    if time.ticks_diff(now, last_toggle_time) > wait_time:
        is_beeping = not is_beeping 
        last_toggle_time = now
        
        if is_beeping:
            buzzer.freq(current_task["freq"])
            buzzer.duty_u16(2000) 
        else:
            buzzer.duty_u16(0) 

def sub_cb(topic, msg):
    global idx, active_audio
    print(f"Hub Message: {msg}")
    
    if msg == b"START":
        active_audio = True
        idx = 0
        refresh_display(idx)
        
    elif msg == b"NEXT":
        if active_audio:
            idx = (idx + 1) % len(tasks)
            print(f"Moving to: {tasks[idx]['name']}")
            refresh_display(idx)
            
    elif msg == b"STOP":
        active_audio = False
        print("Routine STOP.")
        refresh_display(idx)

# --- NETWORK SETUP ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    while not wlan.isconnected():
        led.toggle()
        time.sleep(0.5)
    led.on()
    print("WiFi Connected:", wlan.ifconfig()[0])

# --- MAIN ---
connect_wifi()
refresh_display(idx)

client = MQTTClient(CLIENT_ID, MQTT_BROKER, keepalive=3000)
client.set_callback(sub_cb)

try:
    client.connect()
    client.subscribe(TOPIC_SUB)
    print("Bridge Active.")
    
    while True:
        client.check_msg() 
        update_buzzer()    
        time.sleep(0.01)

except Exception as e:
    print("Error:", e)
    buzzer.duty_u16(0)

