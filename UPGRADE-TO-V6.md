# Upgrade to v6: best plays, cleaner props, twice-daily updates (about 10 minutes)

What changes
- Games tab opens with "This week's plays": what the model would bet, at 1 unit each.
- Props are sorted into Play (4 to 7% gap), Watch (7 to 15%, plus Anytime TD), and Too big to trust (15%+).
- "No TD" picks only appear when the book posts a real No price. Older No TD results get repriced automatically.
- Clean prop names (Receiving yards, not rec_yds) and a new design.
- The model runs twice a day, every day. Live lines are cached so your free Odds API credits last the month.

Your saved results are safe. This zip has no docs/data or data folder, so your logs, overrides, and training file are not touched.

## Part 1: Upload the files
1. Delete any old unzipped nfl-model folder in Finder.
2. Double-click nfl-model-v6.zip and open the nfl-model folder. You should see 8 items:
   folders docs, nflmodel, SETUP and files README.md, requirements.txt, run_weekly.py, train_history.py, UPGRADE-TO-V6.md.
3. GitHub repository, Add file, Upload files. Cmd + A inside the folder, drag the 8 items in. Commit changes.

## Part 2: Update the schedule
1. Open SETUP, then weekly.yml. Click Copy raw file (two overlapping squares).
2. Open .github, workflows, weekly.yml. Click the pencil. Cmd + A, Cmd + V. Commit changes.

## Part 3: Run it
1. Actions, Weekly NFL model, Run workflow. Wait for the green check.
2. Open the dashboard and hard refresh (Cmd + Shift + R).

Check
- Games tab starts with "This week's plays" (it may say "No plays right now" until prop lines load).
- Record tab starts with "Plays record" showing Prop plays 33-28.
- Top right says "Updated ... ago".

## Schedule (Eastern time)
- Monday to Saturday: 8am and 6pm
- Sunday: 11:45am (after inactives) and 7pm (before the night game)
After Nov 1 these land an hour earlier, because GitHub schedules run on UTC. GitHub can also start a run 5 to 30 minutes late.

## Changing the rules
All in nflmodel/config.py, near the bottom:
- PROP_PLAY_MIN / PROP_PLAY_MAX: the Play band (0.04 and 0.07)
- PROP_WATCH_MAX: where Too big to trust starts (0.15)
- PROP_PLAY_STATS: prop types allowed to be a Play
- GAME_PLAY_SPREAD: spread gap for a spread Play (1.5 points)
