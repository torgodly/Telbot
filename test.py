from datetime import datetime, timedelta
import time

def calculate_time_to_wait(today_date, fajr_time):
    # Convert fajr time to datetime object
    fajr_datetime = datetime.combine(today_date.date(), datetime.strptime(fajr_time, '%H:%M').time())
    
    if today_date.time() > fajr_datetime.time():
        # If current time is after fajr, wait until tomorrow's fajr time
        tomorrow_date = today_date + timedelta(days=1)
        tomorrow_fajr_datetime = datetime.combine(tomorrow_date.date(), datetime.strptime(fajr_time, '%H:%M').time())
        wait_time = tomorrow_fajr_datetime - today_date
    else:
        # If current time is before fajr, wait until fajr time today
        wait_time = fajr_datetime - today_date

    return max(timedelta(seconds=0), wait_time)  # Ensure non-negative wait time

def display_time_remaining(wait_time):
    wait_seconds = max(0, wait_time.total_seconds())  # Ensure non-negative wait time
    hours, remainder = divmod(wait_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    print(f"Time remaining: {int(hours)} hours {int(minutes)} minutes {int(seconds)} seconds", end='\r')

# Example usage
today_date = datetime.now()
fajr_time = "8:10"

wait_time = calculate_time_to_wait(today_date, fajr_time)

print(f"Waiting until fajr time at {fajr_time}")

# Countdown timer
while wait_time.total_seconds() > 0:
    display_time_remaining(wait_time)
    time.sleep(1)
    wait_time -= timedelta(seconds=1)

print("\nFajr time reached! Sending messages...")
