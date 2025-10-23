import re
from pathlib import Path
import os
import pandas as pd
import csv

#load the opcode table 
def load_optab(filename="optab.csv"):
    file_path = Path(filename)
    # resolve relative paths against the script directory when possible
    if not file_path.is_absolute():
        try:
            script_dir = Path(__file__).parent
        except NameError:
            script_dir = Path.cwd()
        file_path = script_dir / file_path

    # if not found, fail immediately
    if not file_path.exists():
        raise FileNotFoundError(f"optab file not found: {file_path}")

    df = pd.read_csv(file_path)
    # strip whitespace from column names so ' opcode' -> 'opcode'
    df.columns = df.columns.str.strip()

    optab = {}
    for idx, row in df.iterrows():
        name = str(row.get('name', '')).strip().upper()
        opcode_str = str(row.get('opcode', '')).strip()
        if not opcode_str:
            raise ValueError(f"Missing opcode for instruction '{name}' (row {idx}) in optab: {file_path}")
        try:
            opcode = int(opcode_str, 16)
        except ValueError:
            raise ValueError(f"Invalid hex opcode '{opcode_str}' for instruction '{name}' (row {idx}) in optab: {file_path}")
        formats = str(row.get('format', '')).strip()
        optab[name] = {'opcode': opcode, 'format': formats}
    return optab

OPTAB = load_optab()