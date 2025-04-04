# Betting Monitoring System

This system automates the retrieval, tracking, and notification of sports match results through a series of interconnected scripts.

## Workflow

### 1. Daily Bets Retrieval
First, we run `send_requests.py`, which is responsible for obtaining all available bets for the current day.

```bash
python send_requests.py
```

### 2. Sports Leagues Identification
Next, we execute `leagues_ids.py` to get the identifiers of the sports leagues we want to monitor.

```bash
python leagues_ids.py
```

This script generates a file with the league IDs that will be used in the next step.

### 3. Match Processing
The main script `ps3838.py` performs the following operations:

- Makes requests to the fixtures API to verify if the match exists
- If the match exists, saves its ID in a JSON file to avoid duplicate requests
- Uses the ID to look up the match in the settled endpoint
- Monitors the match score by making periodic requests (every minute)
- Sends score updates to a Telegram group

```bash
python ps3838.py
```
