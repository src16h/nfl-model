# Upgrade to v5: automatic lines (about 20 minutes, one time)

What you get: live spreads, totals, and player props load on their own, get logged, and get graded after the games. No more typing props.
Without a key the model works exactly as before, so you can stop after Part 1 and nothing breaks.

## Part 1: Upload the new files (10 minutes)
1. Delete any old unzipped `nfl-model` folder in Finder.
2. Double-click `nfl-model-v5.zip`, open the `nfl-model` folder. You should see 9 items:
   folders `data`, `docs`, `nflmodel`, `SETUP` and files `README.md`, `requirements.txt`, `run_weekly.py`, `train_history.py`, `UPGRADE-TO-V5.md`.
3. GitHub repository, Add file, Upload files. Cmd + A inside the folder, drag the 9 items in (not the folder itself). Commit changes.
4. Check: the `nflmodel` folder now contains `oddsapi.py`.

(data/props.csv resets to a blank template. Your results and logs in docs/data are NOT touched.)

## Part 2: Get a free Odds API key (3 minutes)
1. Go to the-odds-api.com and click "Get API Key".
2. Enter your email. The key is emailed to you.
3. Keep that email open for Part 3. Treat the key like a password.

## Part 3: Save the key in GitHub (3 minutes)
1. Your repository, Settings tab.
2. Left sidebar: Secrets and variables, then Actions.
3. Click New repository secret.
4. Name: ODDS_API_KEY (exactly, all capitals)
5. Secret: paste your key. Click Add secret.

## Part 4: Update the schedule file (3 minutes)
This file passes your secret to the model.
1. In your repository open SETUP, then weekly.yml. Click the Copy raw file button (two overlapping squares).
2. Go to `.github/workflows/weekly.yml` (click .github, workflows, weekly.yml).
3. Click the pencil icon. Cmd + A to select everything, Cmd + V to paste.
4. Commit changes.

## Part 5: Test it
1. Actions tab, Weekly NFL model, Run workflow. Wait for the green check.
2. Open your dashboard, hard refresh (Cmd + Shift + R), open the Props tab.
3. The box at the top should say "Automatic lines are on" and show your credits left.

What to expect:
- Live spreads and totals load right away (about 2 credits).
- Props only load for games starting within 48 hours, and sportsbooks post them around Wednesday or Thursday. On a Tuesday it is normal to see 0 prop lines. The Thursday, Saturday and Sunday runs will fill them in.
- Each full slate costs roughly 80 credits at the default settings. Check your monthly limit on your Odds API account page. The dashboard always shows what is left.

## If something is off
| Banner says | Meaning | Fix |
|---|---|---|
| Automatic lines are off | No key reached the model | Redo Part 3 and Part 4 (name must be ODDS_API_KEY) |
| API key was rejected | Key typed wrong | Re-create the secret with a fresh copy of the key |
| Out of credits or rate limited | Monthly limit used | Wait for reset, or lower ODDS_MAX_CREDITS_PER_RUN in nflmodel/config.py |
| 0 prop lines | Props not posted yet, or game is over 48 hours away | Wait for the Thursday or Saturday run |
