# Upgrade to v3 (about 10 minutes, plus waiting)

## 1. Upload the new files
1. Unzip `nfl-model-v3.zip`, open the `nfl-model` folder inside
2. GitHub repository: **Add file**, **Upload files**
3. **Cmd + A** the items inside the folder, drag them in, **Commit changes**

Your `data/training_rows.csv` is safe (it's not in the zip). `data/overrides.csv` and `data/props.csv` get reset to blank, so re-add anything you had.

## 2. Rebuild the deep history (required)
The history now includes real injury reports, so it must be rebuilt once.
1. **Actions**, **Train model (deep history)**, **Run workflow**
2. Wait for the green check (expect longer than last time, up to about an hour)

## 3. Run the weekly model
1. **Actions**, **Weekly NFL model**, **Run workflow**
2. Open the dashboard, hard refresh (**Cmd + Shift + R**)

## 4. Check the Track record tab
You should see:
- **Deep backtest: the two engines** (football-only vs market-anchored)
- **Edge size** tables (4 of them)
- Settings line saying **Injury reports in training: XX% of games (learned)**
