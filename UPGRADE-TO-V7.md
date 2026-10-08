# Upgrade to v7: Model picks on every game

## What's new
- Every game card now shows a **Model picks** strip: Spread, Total, and Moneyline.
- Format matches the screenshot: `KC +3 (2.0)`.
  - Spread and total: the number in parentheses is the gap in points between the model and Vegas.
  - Moneyline: model win chance minus the book's fair win chance, like `KC +150 (3.1%)`.
    If no moneyline odds are posted yet, it shows `KC ML (64% to win)` instead.
- Every game always gets a pick. Picks that are also Plays show in gold.
- Games already saved from earlier weeks get picks added automatically.

Your saved results are safe. This zip has no docs/data or data folder.

## Part 1: Upload the files
1. Delete any old unzipped nfl-model folder in Finder.
2. Double-click nfl-model-v7.zip and open the nfl-model folder.
3. GitHub repository, Add file, Upload files. Cmd + A inside the folder, drag everything in. Commit changes.

No change to the schedule file this time.

## Part 2: Run it
1. Actions, Weekly NFL model, Run workflow. Wait for the green check.
2. Open the dashboard and hard refresh (Cmd + Shift + R).

Check: each game in "All games" has a Model picks row under the numbers.

## Setting
In nflmodel/config.py, at the bottom:
- ODDS_MONEYLINE_LIVE = False: moneylines come from the free data feed (no credits).
- Set True to pull live moneylines from your Odds API with each line refresh.
  Costs 1 extra credit per refresh, roughly 60 a month on the 2-runs-a-day schedule.
