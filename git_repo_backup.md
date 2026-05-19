To take a **backup (mirror) of a GitHub repo into Azure DevOps Repos**, you basically create a **1:1 mirror push** from GitHub → Azure Repos.
---

# ✅ Option 1 (Best): Git mirror clone + mirror push

This gives you a **full backup including branches, tags, history, everything**.

## Step 1: Create empty Azure DevOps repo

In Azure DevOps:

* Repos → New repository
* Create an empty repo (no README)

Example:

```
https://dev.azure.com/<org>/<project>/_git/<repo>
```

---

## Step 2: Mirror clone GitHub repo

```bash
git clone --mirror https://github.com/<user>/<repo>.git
cd <repo>.git
```

---

## Step 3: Push mirror to Azure DevOps

```bash
git push --mirror https://dev.azure.com/<org>/<project>/_git/<repo>
```

---

## ⚠️ Important notes

* `--mirror` copies:

  * all branches
  * all tags
  * all refs
* Azure repo must be empty or you may get conflicts
* This is a **true backup clone**

---



---
# 🔄 Option 1 (Recommended): Manual sync after first mirror setup

## ✅ Initial setup (done once)

```bash
git clone --mirror https://github.com/<user>/<repo>.git
cd <repo>.git

git push --mirror https://dev.azure.com/<org>/<project>/_git/<repo>
```

---

# 🔁 Step 1: Update local mirror from GitHub

Every time you want to sync:

```bash
git fetch --prune origin
```

### What this does:

* Pulls latest commits, branches, tags
* Removes deleted branches (`--prune`)

---

# 🔁 Step 2: Push updates to Azure DevOps

```bash
git push --mirror https://dev.azure.com/<org>/<project>/_git/<repo>
```

---

# ⚡ Important behavior of `--mirror`

This is critical:

* It overwrites remote refs exactly
* Adds new branches/tags
* Deletes removed branches/tags in Azure if deleted in GitHub

So Azure becomes a **true replica**

---

# 🧠 Full sync command (recommended routine)

After initial setup, your daily sync becomes:

```bash
cd <repo>.git

git fetch --prune origin
git push --mirror https://dev.azure.com/<org>/<project>/_git/<repo>
```

---

# 🔁 Option 2: Regular clone + push (simpler but not perfect mirror)

```bash
git clone https://github.com/<user>/<repo>.git
cd <repo>

git remote add azure https://dev.azure.com/<org>/<project>/_git/<repo>

git push azure --all
git push azure --tags
```


# 🧠 Best practice recommendation

If your goal is **backup only**:
👉 Use `git clone --mirror`

If your goal is **sync + CI/CD fallback**:
👉 Use GitHub Actions pipeline
