#!/bin/bash
export DISPLAY=:99
export PYTHONUNBUFFERED=1
cd /u01/CareerOps
exec /home/opc/CareerOps/venv/bin/python /u01/CareerOps/scripts/run_deep_profile_optimization.py >> /u01/CareerOps/logs/profile_deep_optimization.log 2>&1
