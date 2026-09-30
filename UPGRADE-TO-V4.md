# Upgrade to v4 (about 10 minutes, no waiting)

You do NOT need to rebuild the deep history or touch the workflow files this time.

## Before you start
- Delete any old unzipped `nfl-model` folder from Finder
- The upload resets `data/overrides.csv` and `data/props.csv` to blank. Copy any lines you want to keep first.

## 1. Unzip
Double-click `nfl-model-v4.zip`, then open the `nfl-model` folder inside.
You should see 9 items: folders `data`, `docs`, `nflmodel`, `SETUP` and files `README.md`, `requirements.txt`, `run_weekly.py`, `train_history.py`, `UPGRADE-TO-V4.md`.

## 2. Upload
1. GitHub repository, **Add file**, **Upload files**
2. Finder: **Cmd + A** inside the folder, drag the 9 items in (not the folder itself)
3. Wait for the list to finish, then **Commit changes**
4. Check the main page: `UPGRADE-TO-V4.md` is listed, and the `nflmodel` folder now contains `tracker.py`

## 3. Run the weekly model
**Actions**, **Weekly NFL model**, **Run workflow**, wait for the green check (5 to 10 minutes).

## 4. Check the dashboard (hard refresh with Cmd + Shift + R)
- **Games tab:** a "Reality check" box at the top, and "Biggest gaps vs Vegas" (no more green "Lean")
- **Props tab:** "Prop record" at the bottom says "Nothing tracked yet"
- **Track record tab:** "Line movement check" says "Collecting data", and the edge-size tables show colors plus a "Likely range" row

## 5. Weekly prop routine (optional)
1. Thursday or Saturday: open `data/props.csv`, click the pencil, delete last week's rows, add this week's
2. Commit, then **Actions, Weekly NFL model, Run workflow** BEFORE kickoff
3. After the games, the next run grades them automatically

## Never delete these (the robot creates them)
- `docs/data/line_log.json`
- `docs/data/props_log.json`
