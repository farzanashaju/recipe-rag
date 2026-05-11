If changes are made locally, first commit and push them to GitHub:

```bash
git add .
git commit -m "updated app"
git push
```

Then, SSH into the VM and execute:

```bash
cd /opt/recipe-rag

git pull

source venv/bin/activate

pip install -r requirements.txt

sudo systemctl restart recipe-rag

sudo systemctl restart nginx
```
