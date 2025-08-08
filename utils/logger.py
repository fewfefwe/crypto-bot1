import csv
import os
from datetime import datetime

LOG_FILE = "signals_log.csv"

def log_signal(signal: dict):
    file_exists = os.path.isfile(LOG_FILE)

    with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        
        # Заголовки при первом создании файла
        if not file_exists:
            writer.writerow([
                "datetime", "symbol", "position", "entry", "tp", "sl",
                "leverage", "risk", "rr_ratio", "quality"
            ])
        
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            signal.get("symbol"),
            signal.get("position"),
            signal.get("entry"),
            signal.get("tp"),
            signal.get("sl"),
            signal.get("leverage", ""),
            signal.get("risk", ""),
            signal.get("rr_ratio", ""),
            signal.get("quality", "")
        ])
