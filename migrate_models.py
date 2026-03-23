import os
import shutil

base_dir = "python-service/models"
styles = ["scalping", "day", "swing"]

for s in styles:
    os.makedirs(os.path.join(base_dir, s), exist_ok=True)
    print(f"✅ Created {os.path.join(base_dir, s)}")

# Move existing ensemble if they exist in python-service root
files_to_move = [
    "ensemble_xgb.json",
    "ensemble_lgb.txt",
    "ensemble_rf.joblib",
    "model_meta.json"
]

for f in files_to_move:
    src = os.path.join("python-service", f)
    dst = os.path.join("python-service/models/swing", f)
    if os.path.exists(src):
        shutil.move(src, dst)
        print(f"📦 Moved {f} to models/swing/")
