import customtkinter as ctk
import paho.mqtt.client as mqtt
from py532lib.i2c import *
import threading
import time
import csv
from datetime import datetime
import os

# --- CONFIGURATION ---
MQTT_BROKER = "localhost"
TOPIC = "nudgeloop/routine"
TASKS = ["Make Bed", "Stretch", "Brush Teeth", "Drink Water", "Take Meds/Vitamins"]
STANDARD_POINTS = 100
REDUCED_POINTS = 70
TIME_THRESHOLD = 15
SCAN_COOLDOWN = 5
LOG_FILE = "nudgeloop_log.csv"

class NudgeLoopHub(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.configure(fg_color="#f0f7ee")

        # State Variables
        self.routine_active = False
        self.is_finished = False
        self.task_idx = 0
        self.total_points = 0
        self.last_scan_time = 0
        self.task_start_time = 0 

        # Window Setup
        self.title("NudgeLoop")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure((0, 1, 2, 3, 4, 5), weight=1)
        
        # Clock
        self.time_var = ctk.StringVar()
        self.label_clock = ctk.CTkLabel(self, textvariable=self.time_var, font=("Courier", 10, "normal"), text_color="black")
        self.label_clock.place(x=20, y=10)
        self.update_clock()

        # Header
        self.label_header = ctk.CTkLabel(self, text="NUDGELOOP: MORNING QUEST", font=("Courier", 24, "normal"), text_color="#776871")
        self.label_header.grid(row=0, column=0, pady=(10, 0))

        # Task
        self.task_text = ctk.StringVar(value="READY TO START?")
        self.label_task = ctk.CTkLabel(self, textvariable=self.task_text, font=("Courier", 45, "normal"), text_color="#91a8a4")
        self.label_task.grid(row=1, column=0)

        # Bonus Point Bar
        self.timer_label = ctk.CTkLabel(self, text="BONUS POINTS ACTIVE", font=("Courier", 14, "normal"), text_color="#91a8a4")
        self.timer_label.grid(row=2, column=0, sticky="s")
        
        self.timer_bar = ctk.CTkProgressBar(self, width=400, height=15, progress_color="#afdedc")
        self.timer_bar.set(1.0)
        self.timer_bar.grid(row=3, column=0, pady=(0, 0))

        # Progress Bar
        self.progress_label = ctk.CTkLabel(self, text="ROUTINE PROGRESS", font=("Courier", 14), text_color="#91a8a4")
        self.progress_label.grid(row=4, column=0, sticky="s")
        self.progress = ctk.CTkProgressBar(self, width=500, height=30, progress_color="#c4d7f2")
        self.progress.set(0)
        self.progress.grid(row=5, column=0, pady=(0, 0))

        # Points
        self.points_text = ctk.StringVar(value="TOTAL POINTS: 0")
        self.label_points = ctk.CTkLabel(self, textvariable=self.points_text, font=("Courier", 32, "normal"), text_color="#776871")
        self.label_points.grid(row=6, column=0, pady=20)
        
        # Status text
        self.status_text = ctk.StringVar(value="Scanner Active")
        self.status_label = ctk.CTkLabel(self, textvariable=self.status_text, font=("Courier", 14), text_color="gray")
        self.status_label.grid(row=7, column=0, pady=10)

        # Reset & Setup
        self.reset_button = ctk.CTkButton(self, text="RESTART ROUTINE", command=self.reset_routine, fg_color="#d35400")
        self.setup_csv()
        
        # MQTT & Scanner
        self.client = mqtt.Client()
        self.client.connect(MQTT_BROKER, 1883, 60)
        self.client.loop_start()
        threading.Thread(target=self.nfc_loop, daemon=True).start()
        
        self.update_timer_ui()

    def update_clock(self):
        self.time_var.set(datetime.now().strftime("%H:%M:%S"))
        self.after(1000, self.update_clock)

    def update_timer_ui(self):
        if self.routine_active and not self.is_finished:
            elapsed = time.time() - self.task_start_time
            remaining_ratio = max(0, (TIME_THRESHOLD - elapsed) / TIME_THRESHOLD)
            
            self.timer_bar.set(remaining_ratio)
            
            if remaining_ratio > 0:
                self.timer_bar.configure(progress_color="#afdedc")
                self.timer_label.configure(text="BONUS POINTS!! (100 PTS)", text_color="#4CAF50")
            else:
                self.timer_bar.configure(progress_color="#e74c3c")
                self.timer_label.configure(text="STANDARD POINTS (80 PTS)", text_color="#e74c3c")
        else:
            self.timer_bar.set(0)
            self.timer_label.configure(text="", text_color="gray")

        self.after(100, self.update_timer_ui) 

    def setup_csv(self):
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Event", "Task", "Time Taken", "Points", "Total"])

    def log_event(self, event, task, duration=0, pts=0):
        with open(LOG_FILE, mode='a', newline='') as f:
            csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), event, task, round(duration, 1), pts, self.total_points])

    def nfc_loop(self):
        """Background thread for NFC hardware."""
        pn532 = Pn532_i2c()
        pn532.SAMconfigure()
        
        while True:
            try:
                card_data = pn532.read_mifare().get_data()
                if card_data:
                    current_time = time.time()
                    
                    if current_time - self.last_scan_time >= SCAN_COOLDOWN:
                        self.last_scan_time = current_time
                        self.after(0, self.handle_interaction)
                    else:
                        remaining = int(SCAN_COOLDOWN - (current_time - self.last_scan_time))
                        print(f"Scan ignored. Wait {remaining}s.")
                        self.after(0, lambda r=remaining: self.status_text.set(f"Cooldown: {r}s remaining"))
                
                time.sleep(0.5) 
            except:
                pass
    

    def handle_interaction(self):
        if self.is_finished:
            self.status_text.set("Routine already finished. See you tomorrow!")
            return 

        self.status_text.set("")
        
        if not self.routine_active:
            self.start_routine()
        else:
            self.complete_task()
    
    def start_routine(self):
        self.routine_active = True
        self.task_idx = 0
        self.task_start_time = time.time()
        self.task_text.set(TASKS[self.task_idx])
        self.client.publish(TOPIC, "START")
        self.log_event("START", TASKS[0])

    def complete_task(self):
        duration = time.time() - self.task_start_time
        pts = STANDARD_POINTS if duration <= TIME_THRESHOLD else REDUCED_POINTS
        
        self.total_points += pts
        self.log_event("TASK_DONE", TASKS[self.task_idx], duration, pts)
        self.task_idx += 1
        
        self.progress.set(self.task_idx / len(TASKS))
        self.points_text.set(f"POINTS: {self.total_points}")

        if self.task_idx < len(TASKS):
            self.task_start_time = time.time() 
            self.task_text.set(TASKS[self.task_idx])
            self.client.publish(TOPIC, "NEXT")
        else:
            self.is_finished = True
            self.task_text.set("QUEST DONE!!!")
            self.label_task.configure(text_color="#776871")
            self.client.publish(TOPIC, "STOP")
            self.reset_button.grid(row=4, column=0, pady=10)

    def reset_routine(self):
        self.is_finished = False
        self.routine_active = False
        self.task_idx = 0
        self.progress.set(0)
        self.points_text.set(f"POINTS: {self.total_points}")
        self.task_text.set("READY TO START?")
        self.label_task.configure(text_color="#91a8a4")
        self.reset_button.grid_forget()
        self.status_text.set("System Reset. Ready to scan.")

if __name__ == "__main__":
    NudgeLoopHub().mainloop()

