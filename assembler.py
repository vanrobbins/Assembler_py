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
DIRECTIVES = {'START', 'END', 'BYTE', 'WORD', 'RESB', 'RESW', 'BASE', 'NOBASE'}

def parse_line(line):
    if line.strip() == '' or line.startswith('.'):
        return None  # ignore comments and blank lines
    if '.' in line: 
        line = line.split('.', 1)[0].rstrip()  # remove inline comments
    parts = re.split(r"\s+", line.strip(), maxsplit=2)
    if len(parts) == 2: 
        label, opcode = (None, parts[0])
        operand = parts[1]
    elif len(parts) == 3:
        label,opcode, operand = parts
    else: 
        label, opcode, operand = (None, parts[0], None)
    return {"label": label, "opcode": opcode.upper(), "operand": operand}

#turns int into 0 padded hex 
def hexstr(value, width=6):
    return f"{value:0{width}X}"

#PASS 1 - building the SYMTAB
def pass1(lines):
    locctr = 0
    symtab = {} #dictionary to hold labels and addresses
    start_address = 0 #default start at 0
    intermediate = [] #storing list of addess, line tuples

    first = parse_line(lines[0])
    if first and first['opcode'] == 'START':
        start_address = int(first['operand'])
        locctr = start_address 
        intermediate.append((locctr, first))
        lines = lines[1:]  

    for line in lines:
        parsed = parse_line(line)
        if not parsed: 
            continue
        opcode = parsed['opcode']
        label = parsed['label']
        operand = parsed['operand']

        if label: 
            if label in symtab:
                raise ValueError(f"Duplicate symbol: {label}")
            symtab[label] = locctr
        
        if opcode in OPTAB:
            format = OPTAB[opcode]['format']
            if "2" in format and not "3" in format: 
                locctr += 2
            else: 
                locctr += 3
        #DIRECTIVES
        elif opcode == "WORD":
            locctr += 3 
        elif opcode == "RESW":
            locctr += 3 * int(operand) 
        elif opcode == "RESB":
            locctr += int(operand)
        elif opcode == "BYTE":
            if operand.startswith('C\'') and operand.endswith('\''):
                locctr += len(operand) - 3
            elif operand.startswith('X\'') and operand.endswith('\''):
                locctr += (len(operand) - 3) // 2
            else:
                raise ValueError(f"Invalid BYTE operand: {operand}")
        elif opcode == "END":
            intermediate.append((locctr, parsed))
            break

        intermediate.append((locctr, parsed))
    
    program_length = locctr - start_address
    return symtab, intermediate, start_address, program_length
#PASS 2 - generating object code and object program 
def pass2(symtab, intermediate, start_address, program_length):
    object_codes = []
    text_records = []
    current_text = []
    current_start = None
    BASE_ADDR =0

    for loc, line in intermediate: 
        opcode = line["opcode"]
        operand = line["operand"]

        if opcode in OPTAB:
            if opcode == "BASE":
                BASE_ADDR = symtab[operand]
                continue

            entry = OPTAB[opcode]
            code = entry['opcode'] 
            format = entry['format']

            if "2" in format and not "3" in format:
                #Format 2, using 2 registers (8 bit op, 4 r1, 4 r2)
                #Register codes
                reg_codes = {'A': 0, 'X': 1, 'L': 2, 'B': 3, 'S': 4, 'T': 5, 'F': 6}
                r1, r2 = operand.split(',')
                obj = (code << 8) | (reg_codes[r1.strip()] << 4) | reg_codes[r2.strip()]
                obj_str = f"{obj:04X}"
            
            else: 
                #format 3 
                n, i, x, b, p, e = 1, 1, 0, 1, 0, 0
                disp = 0
                #immediate addressing
                if operand.startswith('#'):
                    n, i = 0, 1
                    sym = operand[1:]
                    if sym.isdigit():
                        disp = int(sym)
                    else: #PC relative
                        disp = symtab[sym] - (loc +3)
                #indirect addressing
                elif operand.startswith('@'):
                    n, i = 1, 0
                    sym = operand[1:]
                    disp = symtab[sym] - (loc + 3)
                else: #simple addressing
                    if ',X' in operand:
                        x = 1
                        operand = operand.replace(',X', '')
                    sym = operand.strip()
                    disp = symtab[sym] - (loc + 3)
                
                if not (-2048 <= disp <= 2047):
                    if (0 <= symtab[sym] - BASE_ADDR <= 4095):
                        #base relative
                        b = 1
                        p = 0
                        disp = symtab[sym] - BASE_ADDR
                    else: 
                        raise ValueError(f"Displacement out of range for symbol: {sym}")
                    
                obj = (code << 16) | (n << 17) | (i << 16) | (x << 15) | (b << 14) | (p << 13) | (e << 12) | (disp & 0xFFF)
                obj_str = f"{obj:06X}"
            object_codes.append((loc, obj_str))
            if current_start is None:
                current_start = loc
            current_text.append(obj_str)

            #Split text records if too long ( > 60 chars)
            if sum(len(x) for x in current_text) > 60:
                record = f"T{hexstr(current_start,6)}{hexstr(sum(len(x)//2 for x in current_text),2)}{''.join(current_text)}"
                text_records.append(record)
                current_text, current_start = [], None
        
        elif opcode == "BYTE" or opcode == "WORD":
            if opcode == "WORD":
                value = int(operand)
                obj_str = f"{value:06X}"
            else: 
                if operand.startswith('C\'') and operand.endswith('\''):
                    chars = operand[2:-1]
                    obj_str = ''.join(f"{ord(c):02X}" for c in chars)
                elif operand.startswith('X\'') and operand.endswith('\''):
                    obj_str = operand[2:-1]
                else:
                    raise ValueError(f"Invalid BYTE operand: {operand}")
            object_codes.append((loc, obj_str))
            if current_start is None:
                current_start = loc
            current_text.append(obj_str)
        
        elif opcode == "RESW" or opcode == "RESB":
            if current_text:
                record = f"T{hexstr(current_start,6)}{hexstr(sum(len(x)//2 for x in current_text),2)}{''.join(current_text)}"
                text_records.append(record)
                current_text, current_start = [], None
        
        elif opcode == "END":
            break
    
    #Flush the last text record
    if current_text:
        record = f"T{hexstr(current_start,6)}{hexstr(sum(len(x)//2 for x in current_text),2)}{''.join(current_text)}"
        text_records.append(record)
    
    header = f"H{"BASIC":<6}{hexstr(start_address,6)}{hexstr(program_length,6)}"
    endrec = f"E{hexstr(start_address,6)}"

    return object_codes, [header] + text_records + [endrec]

def assemble_file(input_file):
    lines = Path(input_file).read_text().splitlines()
    symtab, intermediate, start, length = pass1(lines)
    objcodes, objprogram = pass2(symtab, intermediate, start, length)

    Path("objectcodes.txt").write_text(
        "\n".join(f"{hexstr(addr,4)}  {code}" for addr, code in objcodes)
    )
    Path("objectprogram.txt").write_text("\n".join(objprogram))

    print("Assembly complete!")
    print("   → objectcodes.txt")
    print("   → objectprogram.txt")

if __name__ == "__main__":
    assemble_file("C:/Users/lilli/OneDrive/Desktop/c335_assembler_finalproject/Assembler_py/basic.txt")
