# The Board: NFL prediction model (v2)

**v2 adds:** a 14-season deep backtest, a machine-learning ensemble, Elo, live weather, travel and body clock, pass rush vs protection, key-number (3 and 7) odds, correlated player simulations, and a Props tab. See **UPGRADE-TO-V2.md** if you're upgrading.

A Vegas-style NFL model that updates itself 4 times a week and publishes a private-link dashboard with:

- **Projected scores**, win chances, model spread and total vs. the Vegas line
- **Leans**: games where the model disagrees with Vegas the most
- **Player projections**: passing, rushing, receiving, TD odds, PPR points, with medians and ranges for props
- **Power ratings** and an honest **track record**

You never touch code. GitHub runs it for free.

---

## One-time setup (about 15 minutes)

### 1. Create a free GitHub account
Go to github.com and sign up.

### 2. Create a repository (the project's home)
- Click **+** (top right), then **New repository**
- Name: `nfl-model`
- Choose **Public** (required for the free website; the link is not listed anywhere)
- Check **Add a README file**
- Click **Create repository**

### 3. Upload the project files
- Unzip `nfl-model.zip` on your computer
- In your repository, click **Add file**, then **Upload files**
- Open the unzipped folder, select everything inside it (`docs`, `nflmodel`, `data`, `SETUP`, `run_weekly.py`, `requirements.txt`, `README.md`) and drag it in
- Click **Commit changes**

### 4. Add the automatic schedule
This file lives in a hidden folder, so we create it by hand:
- Click **Add file**, then **Create new file**
- In the name box type exactly: `.github/workflows/weekly.yml`
- In another tab, open `SETUP/weekly.yml` in your repository, click the **Copy raw file** button (two overlapping squares), and paste into the big box
- Click **Commit changes**

### 5. Let the robot save results
- **Settings** tab, then **Actions**, then **General**
- Scroll to **Workflow permissions**, pick **Read and write permissions**, click **Save**

### 6. Turn on the website
- **Settings** tab, then **Pages**
- Source: **Deploy from a branch**
- Branch: **main**, folder: **/docs**, click **Save**

### 7. Run it the first time
- **Actions** tab (if asked, click the green button to enable workflows)
- Click **Weekly NFL model**, then **Run workflow**, then the green **Run workflow**
- Wait about 5 to 10 minutes for the green checkmark

### 8. Open your dashboard
`https://YOUR-GITHUB-USERNAME.github.io/nfl-model/`
Bookmark it. On your phone, use "Add to Home Screen".

---

## One more workflow: Train model (deep history)

The weekly model learns from a deep history file that a second workflow builds.
- Add it the same way as step 4, but name the file `.github/workflows/train.yml` and copy from `SETUP/train.yml`
- Run it once from the Actions tab (takes 10 to 40 minutes)
- It re-runs itself every March 1 and August 1

## Your weekly routine (optional, 2 minutes)

The model runs by itself:

| When (Eastern) | Why |
|---|---|
| Tuesday 8am | Full rebuild after Monday night |
| Thursday 2pm | First injury reports |
| Saturday 11am | Final injury designations |
| Sunday 10am | Last update before kickoff |

**Only thing worth doing yourself:** on Saturday, glance at QB news. If the model has the wrong starter, fix it:
1. Open `data/overrides.csv` in your repository, click the pencil icon
2. Add a line such as `NYJ,Tyrod Taylor,STARTING_QB,starter benched`
3. Commit, then run the workflow again from the Actions tab

Other override options: `OUT`, `DOUBTFUL`, `QUESTIONABLE`, `ACTIVE`. Delete old lines each week.

**Props:** edit `data/props.csv` the same way, adding lines from your sportsbook such as `Patrick Mahomes,KC,pass_yds,262.5,-115,-105`. The Props tab shows the model's chance, the book's chance (vig removed), and correlated same-game pairs.

---

## How the model works

**1. Team ratings (EPA based).** Every offensive play has an Expected Points Added value. The model fits all plays at once so each team's rating is adjusted for its schedule. It fits separate pass and run ratings, so a strong passing offense gets extra credit against a weak pass defense. Recent weeks count more, and last season fades out as this season builds up. Garbage-time plays are down-weighted.

**2. Game projection.** Ratings x expected plays (pace) = points above average for each side, added to the league scoring average.

**3. Self-calibration.** Every run, the model re-predicts every game from last season to now using only data available at the time, then fits home field advantage and a scale factor. This keeps it honest as the league changes.

**4. Adjustments.**
- **QB changes**: finds the expected starter (injury reports, recent starts, returns from injury) and adjusts by the quality gap in EPA per dropback. Worth up to 10 points.
- **Other injuries**: receivers and backs valued by their share of the offense, linemen and defenders by position if they play 60%+ of snaps.
- **Rest**: extra days off vs opponent (bye weeks, Thursday games).
- **Coverage schemes**: man vs zone matchups when that data is published (auto-off otherwise).

**5. Simulation.** 20,000 simulated games per matchup give win, cover, and over/under chances.

**6. Player projections.** Team plays and pass rate (adjusted for game script) x each player's recent share of targets, carries, and red-zone looks x efficiency (pulled toward position averages until the sample is big) x what the opponent allows. Injured players are removed and their work is redistributed. Ranges come from a skewed distribution, since yardage has more big-game upside than downside.

**Data:** all free from nflverse (play-by-play, schedules and Vegas lines, rosters, injuries, snap counts).

---

## Honest expectations

- Vegas lines are very sharp. A model that picks 53 to 55% against the spread over hundreds of games is excellent. Early-season results are noisy.
- The best sign of skill is **beating the closing line**, meaning the line moves toward your side after you'd have bet it.
- For props, compare the book's line to the **median**, not the average.
- Never bet more than you can afford to lose. This is a research tool.

## Settings you can change

Everything lives in `nflmodel/config.py` with plain-English notes. The useful ones:

| Setting | Default | What it does |
|---|---|---|
| `MARKET_WEIGHT` | 0.0 | Set 0.3 to 0.5 to blend in the Vegas line. More accurate scores and player projections, but fewer independent leans |
| `LEAN_SPREAD_EDGE` | 2.0 | Points of disagreement needed to flag a spread lean |
| `LEAN_TOTAL_EDGE` | 3.0 | Same, for totals |
| `RECENCY_DECAY` | 0.92 | Lower = recent games matter even more |

## Known limits
- Rookies and newly signed players have no usage history until they play.
- Players traded mid-season restart their role history with the new team.
- Weather and coaching changes are not modeled yet.

## Troubleshooting
- **Red X in Actions**: click the failed run to read the error. Most often, step 5 (permissions) was skipped.
- **Dashboard says "has not run yet"**: run the workflow, then wait 2 minutes for the site to refresh.
- **GitHub pauses schedules after 60 days of no activity** in a repo. The bot's commits count as activity during the season. Before next season, run it once by hand.
