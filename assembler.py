import re
from pathlib import Path
import os
import pandas as pd
import csv

#load the opcode table 
def load_optab(filename="optab.csv"):
    file_path = Path(filename)
    # resolve relative paths against the script directory
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
    # strip whitespace from column names
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
    symtab = {} #dictionary to hold labels and addresses
    littab = {} #dictionary to hold literals and addresses
    start_address = 0 #default start at 0
    intermediate = [] #storing list of address, line tuples
    blocktab = {} #dictionary to hold block names and addresses and size
    current_block = 'DEFAULT'
    blocktab["DEFAULT"] = {"locctr":0, "address":0, "size":0}
    locctr = blocktab["DEFAULT"]["locctr"]
    symtab_block = {} #to track which block each symbol belongs to

    first = parse_line(lines[0])
    if first and first['opcode'] == 'START':
        start_address = int(first['operand'])
        locctr = start_address 
        intermediate.append((5, locctr, first, current_block))
        lines = lines[1:]  

    for lineno, line in enumerate(lines, start=2):
        parsed = parse_line(line)
        if not parsed: 
            continue
        opcode = parsed['opcode']
        label = parsed['label']
        operand = parsed['operand']

        #handle USE directive for blocks
        if opcode == "USE":
            if operand is None:
                operand = "DEFAULT"
            #create new block if doesn't exist
            if operand not in blocktab:
                blocktab[operand] = {"locctr":0, "address":0, "size":0}
            #update current block
            blocktab[current_block]["locctr"] = locctr
            #switch to new block
            current_block = operand
            locctr = blocktab[current_block]["locctr"]

            intermediate.append(((lineno-1)*5, locctr, parsed, current_block))
            continue

        #handle literals (=)
        if operand and operand.startswith('='):
            literal_name = operand
            if literal_name not in littab:
                littab[literal_name] = {"value": operand[1:], "address": None}

        if label: 
            if label in symtab:
                raise ValueError(f"Duplicate symbol: {label}")
            symtab[label] = locctr
            symtab_block[label] = current_block

        #format 4 handling (+)
        is_extended = False
        if opcode.startswith('+'):
            is_extended = True
            opcode = opcode[1:]
        
        if opcode in OPTAB:
            format = OPTAB[opcode]['format']
            if is_extended:
                locctr += 4
            elif "2" in format and not "3" in format: 
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

        elif opcode == "LTORG" or opcode == "END":
            for literal in littab: 
                if littab[literal]["address"] is None:
                    littab[literal]["address"] = locctr
                    if littab[literal]["value"].startswith('C\'') and littab[literal]["value"].endswith('\''):
                        locctr += len(littab[literal]["value"]) - 3
                    elif littab[literal]["value"].startswith('X\'') and littab[literal]["value"].endswith('\''):
                        locctr += (len(littab[literal]["value"]) - 3) // 2
                    else:
                        locctr += 3 
            if opcode == "END":
                intermediate.append(((lineno-1)*5, locctr, parsed, current_block))
                break
        blocktab[current_block]["locctr"] = locctr
        intermediate.append(((lineno-1)*5, locctr, parsed, current_block))
    
    blocktab[current_block]["locctr"] = locctr
    #get block sizes
    for block in blocktab:
        blocktab[block]["size"] = blocktab[block]["locctr"]
    #assign block addresses in order
    caddress = start_address
    for block in blocktab:
        blocktab[block]["address"] = caddress
        caddress += blocktab[block]["size"]


    program_length = locctr - start_address
    return symtab, littab, intermediate, start_address, program_length, blocktab, symtab_block

#PASS 2 - generating object code and object program 
def pass2(symtab, littab, intermediate, start_address, program_length, blocktab, symtab_block):
    object_codes = []
    text_records = []
    current_text = []
    current_start = None
    BASE_ADDR =0

    for lineno, loc, line, block in intermediate: 
        opcode = line["opcode"]
        operand = line["operand"]

        #adjust locctr for blocks
        tloc = blocktab[block]["address"] + loc 

        #fix symbtab addresses for blocks
        fixed_symtab = {}
        for sym, addr in symtab.items():
            blockname= symtab_block[sym]
            fixed_symtab[sym] = addr + blocktab[blockname]["address"]
        symtab = fixed_symtab

        is_extended = False
        if opcode.startswith('+'):
            is_extended = True
            opcode = opcode[1:]

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
                tokens = [r.strip() for r in operand.split(',')]
                r1 = tokens[0]
                r2 = tokens[1] if len(tokens) > 1 else '0' #if there's no second register, use 0
                obj = (code << 8) | (reg_codes.get(r1, 0) << 4) | reg_codes.get(r2, 0)
                obj_str = f"{obj:04X}"
            
            else: 
                #format 3 
                n, i, x, b, p, e = 1, 1, 0, 1, 0, 0
                disp = 0

                if not operand: 
                    obj = (code << 16)
                    obj_str = f"{obj:06X}"
                    object_codes.append((loc, obj_str))
                    continue

                if is_extended:
                    e = 1
                    b=0
                    target_addr = symtab.get(operand.replace(',X','').replace('#','').replace('@','').strip(), 0)
                    if ",X" in operand:
                        x = 1
                    obj = (code << 16) | (n << 17) | (i << 16) | (x << 15) | (b << 14) | (p << 13) | (e << 12) | (target_addr & 0xFFFFF)
                    obj_str = f"{obj:08X}"
                else:

                    #handle literals
                    if operand.startswith('='):
                        literal = operand.strip()
                        literal_addr = littab[literal]["address"]
                        disp = literal_addr - (tloc + 3)
                        if not (-2048 <= disp <= 2047):
                            if (0 <= (literal_addr - BASE_ADDR) <= 4095):
                                b = 1
                                p = 0
                                disp = literal_addr - BASE_ADDR
                            else:
                                raise ValueError(f"Displacement out of range for literal: {literal}")
                        sym = literal

                    #immediate addressing
                    elif operand.startswith('#'):
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
                current_start = tloc
            current_text.append(obj_str)

            #split text records if too long ( > 60 chars)
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
                current_start = tloc
            current_text.append(obj_str)
        
        elif opcode == "RESW" or opcode == "RESB":
            if current_text:
                record = f"T{hexstr(current_start,6)}{hexstr(sum(len(x)//2 for x in current_text),2)}{''.join(current_text)}"
                text_records.append(record)
                current_text, current_start = [], None
        
        elif opcode == "LTORG" or opcode == "END":
            for literal, data in littab.items(): 
                if data["address"] is not None: 
                    address = data["address"]
                    value = data["value"]
                    if value.startswith('C\'') and value.endswith('\''):
                        chars = value[2:-1]
                        obj_str = ''.join(f"{ord(c):02X}" for c in chars)
                    elif value.startswith('X\'') and value.endswith('\''):
                        obj_str = value[2:-1]
                    else:
                        obj_str = f"{int(value):06X}"
                    object_codes.append((address, obj_str))
            if opcode == "END":
                break
    
    #Flush the last text record
    if current_text:
        record = f"T{hexstr(current_start,6)}{hexstr(sum(len(x)//2 for x in current_text),2)}{''.join(current_text)}"
        text_records.append(record)
    
    header = f"H{"BASIC":<6}{hexstr(start_address,6)}{hexstr(program_length,6)}"
    endrec = f"E{hexstr(start_address,6)}"

    return object_codes, [header] + text_records + [endrec]

def assemble_file(input_file):
    #pass 1
    lines = Path(input_file).read_text().splitlines()
    symtab, littab, intermediate, start, length, blocktab, symtab_block = pass1(lines)

    #pass 2
    objcodes, objprogram = pass2(symtab, littab, intermediate, start, length, blocktab, symtab_block)

    #write object program file
    Path("objectprogram.txt").write_text("\n".join(objprogram))

    #write listing file
    list_path = Path("listing.txt")
    listing_lines = [
        "Line  Loc   Source Statement            Object Code",
        "------------------------------------------------------"
    ]

    for lineno, loc, parsed, block in intermediate:
        label = parsed["label"] or ""
        opcode = parsed["opcode"] or ""
        operand = parsed["operand"] or ""
        obj = next((code for loc_code, code in objcodes if loc_code == loc), "")
        # Safe string formatting with spacing
        source = f"{label} {opcode} {operand}".strip()
        line_str = f"{lineno:<5}  {hexstr(loc,4)}  {source:<30} {obj}"
        listing_lines.append(line_str)

    list_path.write_text("\n".join(listing_lines))

    print("Assembly complete!")

if __name__ == "__main__":
    assemble_file("C:/Users/lilli/OneDrive/Desktop/c335_assembler_finalproject/Assembler_py/txt_files/functions.txt")
