"""Download (or read) the UCI Online Retail dataset, clean it and load it into the configured database.

  python -m scripts.import_dataset                       # download from UCI, then import
  python -m scripts.import_dataset --file "Online Retail.xlsx"
"""
import argparse
import io
import os
import urllib.request
import zipfile
from datetime import datetime

from app.database import SessionLocal
from app.models import AnalyticsRun
from app.services.runner import execute_import

URL = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="Local .xlsx/.csv. If omitted the dataset is downloaded from UCI.")
    ap.add_argument("--data-dir", default="data")
    a = ap.parse_args()
    os.makedirs(a.data_dir, exist_ok=True)
    path = a.file
    if not path:
        print(f"Downloading {URL} ...")
        with urllib.request.urlopen(URL, timeout=120) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        member = next(n for n in z.namelist() if n.lower().endswith((".xlsx", ".csv")))
        path = z.extract(member, a.data_dir)
    # execute_import deletes the file it reads, so work on a copy
    tmp = os.path.join(a.data_dir, "_import_tmp" + os.path.splitext(path)[1])
    with open(path, "rb") as s, open(tmp, "wb") as d:
        d.write(s.read())
    db = SessionLocal()
    run = AnalyticsRun(run_type="import", status="pending", params={"filename": os.path.basename(path), "via": "cli"})
    db.add(run); db.commit(); rid = run.id; db.close()
    print("Cleaning and loading (the 541k-row .xlsx can take several minutes)...")
    execute_import(SessionLocal, rid, tmp, os.path.basename(path))
    db = SessionLocal(); run = db.get(AnalyticsRun, rid)
    print(f"Run {rid}: {run.status}")
    print(run.error or run.result)


if __name__ == "__main__":
    main()
