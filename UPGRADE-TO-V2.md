# Upgrade to v2 (about 10 minutes)

Your current model keeps running the whole time. Nothing breaks if you stop halfway.

## 1. Upload the new files
1. Unzip `nfl-model-v2.zip`
2. In your repository: **Add file**, **Upload files**
3. Open the unzipped `nfl-model` folder, **Cmd + A**, drag the items in (not the folder itself)
4. **Commit changes**. GitHub replaces the old versions automatically.

Note: this replaces `data/overrides.csv` with a blank copy. Re-add any overrides you had.

## 2. Add the training workflow
1. Open `SETUP/train.yml` in your repository, click **Copy raw file**
2. Go back to the main page, **Add file**, **Create new file**
3. Name it exactly: `.github/workflows/train.yml`
4. Paste, then **Commit changes**

## 3. Build the deep history (one time)
1. **Actions** tab, **Train model (deep history)**, **Run workflow**
2. Wait for the green check (10 to 40 minutes, it rebuilds every game since 2012)
3. Check: a new file `data/training_rows.csv` appears in your repository

## 4. Run the weekly model
1. **Actions**, **Weekly NFL model**, **Run workflow**
2. When it's green, open your dashboard

## 5. Confirm it worked
On the **Track record** tab you should see:
- **Deep backtest** with a row for each season
- **What the model learned** with factor weights
- **Engine: ensemble**

If you see "Deep history not built yet", step 3 didn't finish. Send me a screenshot of that run.
