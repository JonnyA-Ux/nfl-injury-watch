# Sharing the dashboard

Three ways, easiest first.

## 1. Just send the file

`dashboard.html` is completely self-contained. No server, no internet needed to
read it. Email it, AirDrop it, drop it in a Slack DM.

Fine for a one-off. Bad as a habit, because every morning you send another file.

## 2. Netlify Drop

Go to app.netlify.com/drop and drag your NFL folder onto the page. You get a
public URL in about ten seconds with no account required.

Rename `dashboard.html` to `index.html` first, or you have to add `/dashboard.html`
to the end of the URL.

Re-drag the folder each morning to update it. The URL stays the same.

## 3. GitHub Pages, running itself

This is the one worth setting up. GitHub runs the script on their servers every
morning and publishes the result, so the dashboard stays current whether or not
your laptop is on.

### Setup

1. Make a free account at github.com if you don't have one.

2. Create a new repository. Call it `nfl-injury-watch`. Make it **public**,
   since Pages on private repos needs a paid plan. Nothing here is personal, so
   public is fine.

3. On the repo page, click "uploading an existing file" and drag in
   `injury_watch.py`, `dashboard.py`, and `README.md`. Commit.

4. Create the workflow file. Click Add file, then Create new file, and type this
   exact path as the filename:

   ```
   .github/workflows/daily.yml
   ```

   Paste in the contents of `daily.yml`, then commit.

5. Go to Settings, then Pages. Under Source pick "Deploy from a branch", set the
   branch to `main` and the folder to `/ (root)`. Save.

6. Go to the Actions tab, click "Daily injury dashboard", then "Run workflow".
   First run takes about five minutes because it builds the beneficiary map.

Your URL will be:

```
https://YOURNAME.github.io/nfl-injury-watch/dashboard.html
```

Send that to your friend. It refreshes itself every morning around 5am Pacific.

### About the lines you log

Logging happens on your laptop and writes to `lines.csv`, which GitHub doesn't
know about. To get your tracked lines onto the hosted dashboard, upload
`lines.csv` to the repo after you log something. The next run picks it up.

If that gets annoying, the fix is running the log command through GitHub instead
of locally, which is a change worth making once you know you'll keep using this.

### Changing the schedule

The cron line `10 12 * * *` means 12:10 UTC daily. To run it twice a day, add a
second line:

```yaml
    - cron: "10 12 * * *"
    - cron: "10 22 * * *"
```

GitHub's scheduler is often 5 to 15 minutes late. That doesn't matter here.

### If the workflow fails

Open the Actions tab, click the failed run, and click through to the red step.
The error text is at the bottom. Paste it to me.
