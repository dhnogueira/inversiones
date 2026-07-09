---
description: Push project changes to GitHub (triggers automatic GitHub Pages deployment)
---

// turbo-all

## Auto-deploy PicadoFino to GitHub Pages

Run these steps after any modification to the project files to commit and push changes to the `main` branch, which triggers the GitHub Actions workflow that deploys to GitHub Pages at https://dhnogueira.github.io/inversiones/.

1. Stage all changed project files (exclude the Python virtualenv and cache files):
```powershell
& "C:\Program Files\Git\cmd\git.exe" -C "C:\Users\dhn\Documents\Antigravity\PicadoFino" add --all -- ":(exclude)backend/venv/*" ":(exclude)backend/cache/*" ":(exclude)*.pyc" ":(exclude)__pycache__/*"
```

2. Commit with a descriptive message (replace MESSAGE with a short description of what changed):
```powershell
& "C:\Program Files\Git\cmd\git.exe" -C "C:\Users\dhn\Documents\Antigravity\PicadoFino" commit -m "chore: auto-deploy update from Antigravity agent"
```

3. Push to the remote main branch:
```powershell
& "C:\Program Files\Git\cmd\git.exe" -C "C:\Users\dhn\Documents\Antigravity\PicadoFino" push origin main
```

4. Confirm the push succeeded by checking git status:
```powershell
& "C:\Program Files\Git\cmd\git.exe" -C "C:\Users\dhn\Documents\Antigravity\PicadoFino" status
```

After pushing, GitHub Actions will automatically run the deployment workflow at:
https://github.com/dhnogueira/inversiones/actions

The updated site will be live at https://dhnogueira.github.io/inversiones/ within about 1-2 minutes.
