"""Launch each Spark job in its own Python/JVM process, outside the API process."""
import os
from pathlib import Path
import signal
import subprocess
import sys

from ..config import settings

BACKEND_DIR = Path(__file__).resolve().parents[2]


def resolve_rfm_engine(requested: str, source: str | None) -> str:
    engine = ("spark" if source == "olist" else "pandas") if requested == "auto" else requested
    if engine == "spark" and source != "olist":
        raise ValueError("Spark RFM requires the Olist PostgreSQL dataset. Select Pandas for UCI data.")
    return engine


def launch_spark_run(database_url: str, run_id: int) -> None:
    log_dir = BACKEND_DIR / "data" / "spark-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    # Credentials travel through the environment, never command-line arguments.
    env["DATABASE_URL"] = database_url
    env["PYSPARK_PYTHON"] = sys.executable
    env["PYSPARK_DRIVER_PYTHON"] = sys.executable
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    with (log_dir / f"run-{run_id}.log").open("w", encoding="utf-8") as log:
        with subprocess.Popen(
            [sys.executable, "-m", "scripts.spark_rfm", "--run-id", str(run_id)],
            cwd=BACKEND_DIR, env=env, stdout=log, stderr=subprocess.STDOUT, **flags,
        ) as process:
            try:
                process.wait(timeout=settings.spark_job_timeout_seconds)
            except subprocess.TimeoutExpired:
                # Stop the JVM as well as its Python parent on timeout.
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW, check=False)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.kill()
                process.wait()
                raise RuntimeError("Spark job timed out. See backend/data/spark-logs for this run's log.") from None
    # The worker records detailed success/failure in analytics_runs. Its caller
    # also detects abnormal exits that did not update the run.
